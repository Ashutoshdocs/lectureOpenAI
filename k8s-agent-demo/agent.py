"""
The autonomous SRE agent.

It runs a classic tool-use loop:
    LLM decides an action -> we execute the kubectl tool -> feed result back
    -> LLM decides the next action ... until the pod is healthy.

This is the difference between a chatbot and an agent: the chatbot would
*tell* you to run kubectl; this actually runs it, reads the result, and
decides what to do next.
"""
from __future__ import annotations
import json

from openai import OpenAI

import config
from tools import TOOLS_SCHEMA, execute_tool

SYSTEM_PROMPT = """You are an autonomous Site Reliability Engineer (SRE) agent.

Your goal: find any unhealthy pod in the cluster, diagnose the root cause, fix
it, and confirm the pod is Running again.

Work in small steps using ONLY the provided tools. A good approach:
  1. kubectl_get_pods            - find the failing pod
  2. kubectl_logs                - read WHY it is crashing
  3. kubectl_describe_pod        - confirm the failure (optional)
  4. kubectl_get_deployment      - inspect the current configuration
  5. kubectl_set_env             - apply the minimal correct fix
  6. kubectl_get_pods            - verify the pod is now Running

Rules:
- Never guess the fix. Read the logs first and use the exact allowed value they mention.
- Change only what is necessary.
- When the pod shows STATUS Running with READY 1/1, STOP and give a short
  final report: what was wrong, what you changed, and the result.
"""

# ---- pretty console output ------------------------------------------------
C = {"dim": "\033[2m", "cyan": "\033[36m", "green": "\033[32m",
     "yellow": "\033[33m", "bold": "\033[1m", "reset": "\033[0m"}


def banner(text: str) -> None:
    print(f"\n{C['bold']}{C['cyan']}{'=' * 68}{C['reset']}")
    print(f"{C['bold']}{C['cyan']}  {text}{C['reset']}")
    print(f"{C['bold']}{C['cyan']}{'=' * 68}{C['reset']}")


def run() -> None:
    config.validate()
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    banner("AUTONOMOUS K8S DEBUGGING AGENT")
    print(f"  mode   : {C['yellow']}{config.CLUSTER_MODE}{C['reset']}")
    print(f"  model  : {C['yellow']}{config.OPENAI_MODEL}{C['reset']}")
    print(f"  task   : find and fix any CrashLoopBackOff pod\n")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "A pod appears to be failing. Investigate and fix it."},
    ]

    for step in range(1, config.MAX_STEPS + 1):
        resp = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
            temperature=0,
        )
        msg = resp.choices[0].message

        # The model gave a final answer (no more tools) -> we're done.
        if not msg.tool_calls:
            banner("AGENT FINAL REPORT")
            print(msg.content or "(no content)")
            print()
            return

        # Record the assistant's tool-call turn.
        messages.append(msg)

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            arg_str = ", ".join(f"{k}={v}" for k, v in args.items())

            print(f"{C['bold']}[step {step}] "
                  f"{C['green']}$ {tc.function.name}{C['reset']}"
                  f"{C['dim']}({arg_str}){C['reset']}")

            result = execute_tool(tc.function.name, args)

            # indent the tool output so the loop is easy to read
            for line in result.splitlines():
                print(f"    {C['dim']}{line}{C['reset']}")
            print()

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    banner("STOPPED")
    print(f"Reached MAX_STEPS ({config.MAX_STEPS}) without a final report.")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
