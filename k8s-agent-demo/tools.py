"""
Defines the tools (functions) the LLM is allowed to call, and executes them
against either the mock cluster or a real one via `kubectl`.

Each tool maps to a real kubectl operation so the same agent logic works in
both modes:
  kubectl_get_pods        -> kubectl get pods
  kubectl_logs            -> kubectl logs <pod>
  kubectl_describe_pod    -> kubectl describe pod <pod>
  kubectl_get_deployment  -> kubectl get deployment <name> -o yaml
  kubectl_set_env         -> kubectl set env deployment/<name> KEY=VALUE  (the fix + apply)
"""
from __future__ import annotations
import subprocess

import config
from k8s_mock import cluster

# ---- JSON schema advertised to the OpenAI API -----------------------------
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "kubectl_get_pods",
            "description": "List pods and their status (READY, STATUS, RESTARTS). "
            "Use this first to find unhealthy pods, and again at the end to verify a fix.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kubectl_logs",
            "description": "Fetch the container logs of a pod. Use this to find WHY a pod is crashing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod": {"type": "string", "description": "Exact pod name from kubectl_get_pods."}
                },
                "required": ["pod"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kubectl_describe_pod",
            "description": "Show detailed pod state: waiting reason, last terminated reason, exit code, env.",
            "parameters": {
                "type": "object",
                "properties": {"pod": {"type": "string"}},
                "required": ["pod"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kubectl_get_deployment",
            "description": "Get the Deployment manifest (YAML) so you can inspect its current configuration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Deployment name, e.g. web-api."}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kubectl_set_env",
            "description": "Fix configuration by setting an environment variable on a Deployment. "
            "This modifies the config AND triggers a rolling update (equivalent to edit + apply). "
            "Only call this once you know the correct value from the logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Deployment name, e.g. web-api."},
                    "key": {"type": "string", "description": "Env var name, e.g. LOG_LEVEL."},
                    "value": {"type": "string", "description": "New, valid value, e.g. INFO."},
                },
                "required": ["name", "key", "value"],
            },
        },
    },
]


# ---- execution ------------------------------------------------------------
def _sh(cmd: list[str]) -> str:
    """Run a real command and return combined stdout/stderr."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (out.stdout + out.stderr).strip() or "(no output)"
    except FileNotFoundError:
        return "ERROR: `kubectl` not found on PATH."
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out."


def execute_tool(name: str, args: dict) -> str:
    """Route a tool call to the mock or the real cluster."""
    ns = config.K8S_NAMESPACE

    if config.CLUSTER_MODE == "mock":
        if name == "kubectl_get_pods":
            return cluster.get_pods()
        if name == "kubectl_logs":
            return cluster.logs(args["pod"])
        if name == "kubectl_describe_pod":
            return cluster.describe_pod(args["pod"])
        if name == "kubectl_get_deployment":
            return cluster.get_deployment_yaml(args["name"])
        if name == "kubectl_set_env":
            return cluster.set_env(args["name"], args["key"], args["value"])
        return f"ERROR: unknown tool {name}"

    # real mode
    if name == "kubectl_get_pods":
        return _sh(["kubectl", "get", "pods", "-n", ns])
    if name == "kubectl_logs":
        return _sh(["kubectl", "logs", args["pod"], "-n", ns])
    if name == "kubectl_describe_pod":
        return _sh(["kubectl", "describe", "pod", args["pod"], "-n", ns])
    if name == "kubectl_get_deployment":
        return _sh(["kubectl", "get", "deployment", args["name"], "-n", ns, "-o", "yaml"])
    if name == "kubectl_set_env":
        return _sh(
            ["kubectl", "set", "env", f"deployment/{args['name']}",
             f"{args['key']}={args['value']}", "-n", ns]
        )
    return f"ERROR: unknown tool {name}"
