# K8s Cartographer 🗺️

Scan a live Kubernetes cluster from a web UI and draw its architecture as a
**handwritten, colorful diagram** — namespaces, pods, services, deployments,
network policies, nodes, and etcd/control-plane health.

```
Browser ──/api/scan──> Cartographer pod ──(read-only RBAC)──> Kubernetes API server ──> etcd
   ▲                                                                                    (cluster state)
   └────────────── handwritten SVG diagram drawn in the browser ◄──── JSON graph ───────┘
```

> **etcd vs the API server:** etcd is where Kubernetes *stores* everything, but
> you don't query it directly (that needs etcd client certs and is discouraged).
> The Cartographer reads the same state the safe way — through the Kubernetes API
> server — using a read-only ServiceAccount. It also surfaces etcd/control-plane
> health via `componentstatuses` when the cluster exposes it.
>
> **OpenAPI, not OpenAI:** the scan uses the Kubernetes API (an OpenAPI spec).
> OpenAI is used only for the optional "Explain (AI)" button.

## What you get

- A read-only cluster scanner (`/api/scan`) — no writes, no Secret values.
- A hand-drawn diagram (Rough.js + a handwritten font) where:
  - each **namespace** is a colored zone,
  - **pods** are cards with their phase, **services** are hexagon chips,
  - a **line** is drawn from a service to every pod its selector matches,
  - a **dashed 🔒 border** marks namespaces that have NetworkPolicies,
  - **control-plane nodes** are drawn in purple, workers in green,
  - an **etcd / control-plane health** strip runs across the top.
- **Rescan**, **show/hide system namespaces**, **download PNG**, and an optional
  **Explain (AI)** button.
- A **demo topology** (3 namespaces + services + network policies) so you have
  something rich to visualize immediately.

## Project structure

```
k8s-cartographer/
├── app/
│   ├── app.py                 # FastAPI + kubernetes client scanner
│   ├── frontend/index.html    # handwritten diagram renderer
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .dockerignore
│   └── .env.example
├── k8s/
│   ├── 00-namespace.yaml
│   ├── 01-rbac.yaml           # ServiceAccount + read-only ClusterRole + binding
│   ├── 02-deployment.yaml
│   └── 03-service.yaml        # NodePort 30090
├── demo/
│   ├── 10-namespaces-workloads.yaml   # 3-tier shop across 3 namespaces
│   └── 20-network-policies.yaml       # db<-backend<-frontend rules
├── .gitignore
└── README.md
```

---

## 1. Build the image

```bash
cd app
docker build -t k8s-cartographer:1.0 .
```

Get it onto the cluster (same as any image):
- **Registry:** `docker tag k8s-cartographer:1.0 docker.io/<you>/k8s-cartographer:1.0 && docker push …`, then set `image:` in `k8s/02-deployment.yaml`.
- **k3s:** `docker save k8s-cartographer:1.0 | sudo k3s ctr images import -`
- **kind:** `kind load docker-image k8s-cartographer:1.0`
- **minikube:** `minikube image load k8s-cartographer:1.0`
- **fromnode:** `docker save k8s-cartographer:1.0 -o k8s-cartographer.tar && ctr -n k8s.io images import k8s-cartographer.tar` then `ctr -n k8s.io images export k8s-cartographer.tar docker.io/library/k8s-cartographer:1.0`

## 2. Deploy the Cartographer (with its read-only RBAC)

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-rbac.yaml
kubectl apply -f k8s/02-deployment.yaml
kubectl apply -f k8s/03-service.yaml
kubectl -n cartographer get pods -w        # wait for READY 1/1
```

## 3. Deploy the demo topology to visualize

```bash
kubectl apply -f demo/10-namespaces-workloads.yaml
kubectl apply -f demo/20-network-policies.yaml
```

## 4. Open it and scan

```bash
kubectl -n cartographer get nodes -o wide   # get a node IP
# open  http://<node-ip>:30090
```

No node IP handy? Port-forward:

```bash
kubectl -n cartographer port-forward svc/cartographer 8000:80
# open http://localhost:8000
```

It auto-scans on load. Click **Scan cluster** to refresh, toggle **show system
namespaces** to see kube-system (etcd, coredns, etc.), and **⬇ PNG** to save the
diagram.

---

## Optional: enable the "Explain (AI)" button

This sends the *structure* (not your data) to OpenAI for a plain-English write-up.

```bash
kubectl -n cartographer create secret generic cartographer-openai \
  --from-literal=OPENAI_API_KEY="sk-your-key"
# then run kubectl delete -f 02-deployment.yaml and run the command:
kubectl apply -f k8s/new-deployment.yaml
```

## Run locally without a cluster deploy

The app can also run against your local kubeconfig:

```bash
cd app
pip install -r requirements.txt
uvicorn app:app --reload --port 8000    # uses ~/.kube/config
# open http://localhost:8000
```

---

## What the diagram shows (legend)

| Shape / cue | Meaning |
|-------------|---------|
| Colored zone | A namespace |
| White card | A pod (with its phase: Running/Pending/…) |
| Hexagon ⬡ chip | A Service (type + ports) |
| Line from ⬡ to card | The service's selector matches that pod |
| Dashed border + 🔒 | Namespace has NetworkPolicies |
| Purple node | Control-plane node · Green | worker node |
| Top strip | etcd / scheduler / controller-manager health |

## Security

- The ServiceAccount has a **read-only ClusterRole** (get/list on topology
  objects only). It cannot modify anything and cannot read Secret values.
- Nothing is written to etcd; the app only lists objects.
- The optional OpenAI key lives in a Secret, injected at runtime, never in the image.

## Notes & troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Diagram shows "Limited RBAC — couldn't read: …" | The ClusterRole/Binding wasn't applied, or your user is more restricted. Re-apply `k8s/01-rbac.yaml`. |
| `componentstatuses` empty / "not exposed" | Managed clusters (EKS/GKE/AKS) hide the control plane — normal. On kubeadm/k3s it usually shows etcd. |
| NetworkPolicies drawn but not enforced | Your CNI (e.g. Flannel) doesn't enforce them. Use Calico/Cilium to actually enforce. The diagram still shows them. |
| `unexpected keyword argument 'proxies'` | Already handled — `httpx==0.27.2` is pinned. |
| Diagram shapes look plain (not sketchy) | The Rough.js CDN was blocked; it falls back to clean SVG. Works either way. |
| `ImagePullBackOff` | Push the image to a registry and set `image:`, or load it locally (step 1). |

## Cleanup

```bash
kubectl delete -f demo/ 2>/dev/null
kubectl delete namespace shop-frontend shop-backend shop-database
kubectl delete -f k8s/03-service.yaml -f k8s/02-deployment.yaml
kubectl delete -f k8s/01-rbac.yaml -f k8s/00-namespace.yaml
```
