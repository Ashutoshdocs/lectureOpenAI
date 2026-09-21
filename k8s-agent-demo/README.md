# Autonomous Kubernetes Debugging Agent — Demo

A minimal, runnable demo of the difference between a **chatbot** and an **agent**.

A normal LLM *tells* you what to run:

> Run `kubectl get pods`.

This agent actually **runs the loop** — detect the failure, read the logs,
find the root cause, fix the config, and verify — the same loop a human SRE
would do:

```
kubectl get pods
      ↓  Pod is CrashLoopBackOff
kubectl logs
      ↓  Find configuration error
kubectl describe / get deployment
      ↓  Inspect the Deployment
kubectl set env   (modify config + apply)
      ↓
kubectl get pods
      ↓  Running ✅
```

It uses **OpenAI function calling** to let the model decide the next `kubectl`
action, executes that action, feeds the result back, and repeats until the pod
is healthy — with a hard step cap so it can never loop forever.

The demo ships with a **built-in mock cluster**, so it runs anywhere with just
an API key — no Kubernetes required. Flip one env var to run it against a
**real cluster** through your own `kubectl`.

---

## The scenario

The `web-api` Deployment is configured with `LOG_LEVEL=verbose`. The app only
accepts `DEBUG | INFO | WARN | ERROR`, so at startup it fails config
validation, exits with code 1, and Kubernetes restarts it over and over →
**`CrashLoopBackOff`**.

The agent has to discover this *from the logs* (not from a hint) and apply the
minimal fix:

```
kubectl set env deployment/web-api LOG_LEVEL=INFO
```

Then re-check and confirm the pod is `Running`.

---

## Files

| File | What it is |
|------|------------|
| `agent.py` | The agent loop: calls the model, runs the chosen tool, feeds results back, prints each step. **Run this.** |
| `tools.py` | The 5 `kubectl` tools exposed to the model + their JSON schemas; routes each to the mock or real cluster. |
| `k8s_mock.py` | A tiny simulated cluster with one broken Deployment. No infra needed. |
| `config.py` | Loads settings from `.env` (key, model, mode, step cap). |
| `_env.example` | Template for your `.env`. Copy it to `.env` and add your key. |
| `requirements.txt` | Python dependencies (`openai`, `python-dotenv`). |
| `run.sh` | One-command launcher (venv + install + run). |
| `manifests/` | Optional: app + Dockerfile + broken Deployment YAML to reproduce this on a **real** cluster. |

---

## Quick start (mock mode — no Kubernetes)

Requires Python 3.9+.

```bash
cd k8s-agent-demo

# 1. configure your key
cp _env.example .env
#   then edit .env and set OPENAI_API_KEY=sk-...

# 2. run it
./run.sh
```

…or do it manually:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp _env.example .env          # edit in your OPENAI_API_KEY
python agent.py
```

### What you'll see

```
====================================================================
  AUTONOMOUS K8S DEBUGGING AGENT
====================================================================
  mode   : mock
  model  : gpt-4o-mini
  task   : find and fix any CrashLoopBackOff pod

[step 1] $ kubectl_get_pods()
    NAME                          READY   STATUS             RESTARTS      AGE
    web-api-8f3k2j9a1-x7c2d       0/1     CrashLoopBackOff   5 (20s ago)   4m17s

[step 2] $ kubectl_logs(pod=web-api-8f3k2j9a1-x7c2d)
    FATAL invalid LOG_LEVEL "verbose" (allowed: DEBUG, INFO, WARN, ERROR)
    FATAL configuration validation failed, exiting (code 1)

[step 3] $ kubectl_get_deployment(name=web-api)
    ... env: LOG_LEVEL: "verbose" ...

[step 4] $ kubectl_set_env(name=web-api, key=LOG_LEVEL, value=INFO)
    deployment.apps/web-api env updated: LOG_LEVEL 'verbose' -> 'INFO'
    deployment.apps/web-api restarted (rolling update)

[step 5] $ kubectl_get_pods()
    web-api-2p9d4b7c0-a1b2c       1/1     Running   0          12s

====================================================================
  AGENT FINAL REPORT
====================================================================
Root cause: LOG_LEVEL was "verbose", which the app rejects...
Fix: set LOG_LEVEL=INFO. Pod is now Running (1/1). ✅
```

(The exact wording and pod hashes vary from run to run — that's the model reasoning.)

---

## Configuration (`.env`)

| Variable | Default | Meaning |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | **Required.** Your OpenAI key. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Any model that supports function calling (`gpt-4o`, `gpt-4o-mini`, …). |
| `CLUSTER_MODE` | `mock` | `mock` = simulated cluster; `real` = shell out to your `kubectl`. |
| `K8S_NAMESPACE` | `default` | Namespace used in `real` mode. |
| `K8S_DEPLOYMENT` | `web-api` | Deployment name used in `real` mode. |
| `MAX_STEPS` | `12` | Safety cap on agent iterations. |

---

## Running against a REAL cluster (optional)

You need a working `kubectl` context (minikube, kind, Docker Desktop, or a real
cluster). This reproduces the same broken Deployment for the agent to fix.

```bash
# from k8s-agent-demo/manifests

# If using minikube, build the image inside its docker so no registry is needed:
eval $(minikube docker-env)          # skip on Docker Desktop / kind w/ local images
docker build -t web-api:1.4.2 .

# deploy the intentionally-broken app
kubectl apply -f deployment-broken.yaml

# watch it fail
kubectl get pods -w                  # -> CrashLoopBackOff

# now let the agent fix it
cd ..
#   in .env set:  CLUSTER_MODE=real
python agent.py

# verify
kubectl get pods                     # -> Running
```

To reset and try again:

```bash
kubectl delete -f manifests/deployment-broken.yaml
kubectl apply  -f manifests/deployment-broken.yaml
```

> **Safety note:** in `real` mode the agent can run `kubectl set env` against
> your cluster. Point it at a throwaway/dev cluster, not production. The tool
> layer only ever runs the five read/patch commands defined in `tools.py` — it
> never has shell access.

---

## How it works (the important part)

1. **Tools are declared as JSON schemas** (`tools.py → TOOLS_SCHEMA`) and passed
   to the model. Each maps to a real `kubectl` operation.
2. **The loop** (`agent.py`): send the conversation + tools to the model.
   - If the model returns **tool calls**, we execute them, print the output, and
     append the results to the conversation as `role: "tool"` messages.
   - If the model returns **plain text** (no tool calls), it's done — that's the
     final report.
3. **Grounding, not guessing.** The system prompt forbids inventing a fix: the
   agent must read the logs and use the exact allowed value they name. This is
   what keeps the fix correct instead of hallucinated.
4. **Bounded autonomy.** `MAX_STEPS` guarantees termination even if the model
   misbehaves.

Swapping the mock for real Kubernetes changes **nothing** in the agent logic —
only the `execute_tool` routing in `tools.py`. That separation (reasoning vs.
execution) is the whole point.

---

## Extending the demo

- **Add a tool:** append a schema to `TOOLS_SCHEMA` and a branch in
  `execute_tool` (e.g. `kubectl_rollout_restart`, `kubectl_top_pods`).
- **Add a new failure mode:** change `k8s_mock.py` (e.g. a bad image →
  `ImagePullBackOff`, or a missing Secret) and watch the agent diagnose it.
- **Require approval:** gate `kubectl_set_env` behind a `input("apply? [y/N] ")`
  prompt for a human-in-the-loop version.
