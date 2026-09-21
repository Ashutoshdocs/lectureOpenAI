"""
K8s Cartographer — scan a Kubernetes cluster and hand back a graph the
frontend draws as a handwritten, colorful architecture diagram.

It reads the cluster state (which Kubernetes stores in etcd) through the
Kubernetes API server, using a read-only ServiceAccount + RBAC. It does NOT
talk to etcd directly — that needs etcd client certs and is discouraged.

Endpoints:
  GET  /              -> the diagram web UI
  GET  /api/scan      -> full cluster graph as JSON
  GET  /api/health    -> control-plane / etcd health (best effort)
  POST /api/explain   -> (optional) plain-English summary via OpenAI
  GET  /healthz       -> liveness probe
  GET  /readyz        -> readiness probe (can we reach the API server?)
"""

import os
import socket

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from kubernetes import client, config
from kubernetes.client.rest import ApiException

POD_NAME = os.getenv("POD_NAME", socket.gethostname())
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

app = FastAPI(title="K8s Cartographer", version="1.0.0")

_loaded = False


def _load_k8s():
    """Load in-cluster config when running as a pod, else local kubeconfig."""
    global _loaded
    if _loaded:
        return
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()
    _loaded = True


def _safe(fn, default):
    """Run a list call; return default (and note the reason) on RBAC/API errors."""
    try:
        return fn(), None
    except ApiException as e:
        return default, f"{e.status} {e.reason}"
    except Exception as e:
        return default, str(e)


# ---------- scanning ----------
def scan_cluster() -> dict:
    _load_k8s()
    core = client.CoreV1Api()
    apps = client.AppsV1Api()
    net = client.NetworkingV1Api()

    warnings = {}

    # Nodes
    nodes_raw, w = _safe(lambda: core.list_node().items, [])
    if w: warnings["nodes"] = w
    nodes = []
    for n in nodes_raw:
        labels = n.metadata.labels or {}
        roles = [k.split("/", 1)[1] for k in labels if k.startswith("node-role.kubernetes.io/")]
        ready = "Unknown"
        for c in (n.status.conditions or []):
            if c.type == "Ready":
                ready = "Ready" if c.status == "True" else "NotReady"
        nodes.append({
            "name": n.metadata.name,
            "roles": roles or ["worker"],
            "status": ready,
            "kubelet": (n.status.node_info.kubelet_version if n.status and n.status.node_info else ""),
        })

    # Namespaces
    ns_raw, w = _safe(lambda: core.list_namespace().items, [])
    if w: warnings["namespaces"] = w

    # Pull the whole cluster's objects once, then bucket by namespace.
    pods_raw, w = _safe(lambda: core.list_pod_for_all_namespaces().items, [])
    if w: warnings["pods"] = w
    svcs_raw, w = _safe(lambda: core.list_service_for_all_namespaces().items, [])
    if w: warnings["services"] = w
    deps_raw, w = _safe(lambda: apps.list_deployment_for_all_namespaces().items, [])
    if w: warnings["deployments"] = w
    nps_raw, w = _safe(lambda: net.list_network_policy_for_all_namespaces().items, [])
    if w: warnings["networkpolicies"] = w

    def by_ns(items):
        d = {}
        for it in items:
            d.setdefault(it.metadata.namespace, []).append(it)
        return d

    pods_by = by_ns(pods_raw)
    svcs_by = by_ns(svcs_raw)
    deps_by = by_ns(deps_raw)
    nps_by = by_ns(nps_raw)

    namespaces = []
    for ns in ns_raw:
        name = ns.metadata.name
        pods = [{
            "name": p.metadata.name,
            "phase": (p.status.phase if p.status else "Unknown"),
            "node": (p.spec.node_name if p.spec else None),
            "labels": p.metadata.labels or {},
            "app": (p.metadata.labels or {}).get("app"),
        } for p in pods_by.get(name, [])]

        services = [{
            "name": s.metadata.name,
            "type": (s.spec.type if s.spec else "ClusterIP"),
            "clusterIP": (s.spec.cluster_ip if s.spec else None),
            "selector": (s.spec.selector or {}) if s.spec else {},
            "ports": [f"{(pt.port)}/{(pt.protocol or 'TCP')}" for pt in (s.spec.ports or [])] if s.spec else [],
        } for s in svcs_by.get(name, [])]

        deployments = [{
            "name": d.metadata.name,
            "replicas": (d.spec.replicas if d.spec else 0),
            "ready": (d.status.ready_replicas or 0) if d.status else 0,
            "selector": (d.spec.selector.match_labels or {}) if (d.spec and d.spec.selector) else {},
        } for d in deps_by.get(name, [])]

        netpols = []
        for np in nps_by.get(name, []):
            spec = np.spec
            ptypes = list(spec.policy_types or []) if spec else []
            netpols.append({
                "name": np.metadata.name,
                "podSelector": (spec.pod_selector.match_labels or {}) if (spec and spec.pod_selector) else {},
                "types": ptypes,
            })

        namespaces.append({
            "name": name,
            "system": name in {"kube-system", "kube-public", "kube-node-lease"},
            "pods": pods,
            "services": services,
            "deployments": deployments,
            "networkPolicies": netpols,
            "counts": {
                "pods": len(pods),
                "services": len(services),
                "deployments": len(deployments),
                "networkPolicies": len(netpols),
            },
        })

    return {
        "servedBy": POD_NAME,
        "nodes": nodes,
        "namespaces": namespaces,
        "totals": {
            "nodes": len(nodes),
            "namespaces": len(namespaces),
            "pods": sum(n["counts"]["pods"] for n in namespaces),
            "services": sum(n["counts"]["services"] for n in namespaces),
            "networkPolicies": sum(n["counts"]["networkPolicies"] for n in namespaces),
        },
        "warnings": warnings,
    }


def control_plane_health() -> dict:
    """Best-effort etcd / control-plane health via componentstatuses."""
    _load_k8s()
    core = client.CoreV1Api()
    comps, w = _safe(lambda: core.list_component_status().items, [])
    out = []
    for c in comps:
        healthy = "Unknown"
        msg = ""
        for cond in (c.conditions or []):
            if cond.type == "Healthy":
                healthy = "Healthy" if cond.status == "True" else "Unhealthy"
                msg = cond.message or ""
        out.append({"name": c.metadata.name, "health": healthy, "message": msg})
    return {"components": out, "note": w or "componentstatuses (etcd, scheduler, controller-manager)"}


# ---------- routes ----------
@app.get("/")
def home():
    return FileResponse("frontend/index.html")


@app.get("/api/scan")
def api_scan():
    try:
        return scan_cluster()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")


@app.get("/api/health")
def api_health():
    try:
        return control_plane_health()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")


class ExplainIn(BaseModel):
    summary: str


@app.post("/api/explain")
def api_explain(payload: ExplainIn):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="OpenAI is not configured. Set OPENAI_API_KEY to enable this.")
    try:
        from openai import OpenAI, OpenAIError
        oai = OpenAI(api_key=OPENAI_API_KEY)
        resp = oai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a Kubernetes architect. Given a JSON-ish summary of a cluster, explain its architecture in clear plain English: namespaces, workloads, how traffic flows, and what the network policies restrict. Be concise (a few short paragraphs)."},
                {"role": "user", "content": payload.summary},
            ],
        )
        return {"explanation": resp.choices[0].message.content, "model": OPENAI_MODEL}
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")


@app.get("/healthz")
def healthz():
    return {"status": "alive", "pod": POD_NAME}


@app.get("/readyz")
def readyz():
    try:
        _load_k8s()
        client.CoreV1Api().get_api_resources()
        return {"status": "ready", "pod": POD_NAME}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach API server: {e}")
