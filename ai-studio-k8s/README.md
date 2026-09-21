# AI Studio — OpenAI on Docker + Kubernetes

More than a chatbot. **AI Studio** is a small FastAPI app with five AI tools —
**Summarize, Translate, Sentiment, Rewrite, Explain** — packaged as a Docker
image and deployed to Kubernetes with a Deployment, Service, Secret, ConfigMap,
health probes, and an autoscaler.

The fun part for a k8s demo: every response shows **which pod served it**, so
when you scale up and refresh, you can watch Kubernetes load-balance across pods.

```
Browser ──> Service (load balances) ──> one of N Pods (FastAPI + OpenAI SDK) ──> OpenAI API
                                          each pod shows its own name in the UI
```

## Project structure

```
ai-studio-k8s/
├── app/
│   ├── app.py              # FastAPI: 5 AI tools + /api/info + health probes
│   ├── frontend/
│   │   └── index.html      # Tabbed UI, shows the serving pod
│   ├── requirements.txt    # httpx pinned to avoid the OpenAI 'proxies' error
│   ├── Dockerfile
│   ├── .dockerignore
│   └── .env.example
├── k8s/
│   ├── 00-namespace.yaml
│   ├── 01-configmap.yaml   # model name
│   ├── 02-secret.example.yaml   # template — real key made via kubectl
│   ├── 03-deployment.yaml  # 2 replicas, probes, env from Secret/ConfigMap
│   ├── 04-service.yaml     # NodePort on 30080
│   ├── 05-hpa.yaml         # autoscale 2–8 pods on CPU
│   └── 06-ingress.yaml     # optional pretty URL
├── .gitignore
└── README.md
```

---

## Part A — Run locally with Docker (quick check)

```bash
cd app
cp .env.example .env          # paste your real key into .env
docker build -t ai-studio:1.0 .
docker run -p 8000:8000 --env-file .env ai-studio:1.0
```

Open **http://localhost:8000**, pick a tab, paste text, hit Run.

> **Note on the OpenAI key:** OpenAI has no permanent free tier. If you get an
> `insufficient_quota` error the key is valid but has no credit. The app uses
> `gpt-4o-mini` (cheapest), so testing costs a fraction of a cent.

---

## Part B — Deploy to Kubernetes

Assumes you have `kubectl` pointing at your cluster.

### 1. Get the image onto the cluster

**Option 1 — push to a registry (works on any cluster):**

```bash
# tag with your registry username, then push
docker tag ai-studio:1.0 docker.io/<your-user>/ai-studio:1.0
docker push docker.io/<your-user>/ai-studio:1.0
```

Then edit `k8s/03-deployment.yaml` and set `image:` to that same name.

**Option 2 — single-node / self-built cluster:** if you built the image on the
same node the pods run on, the Deployment already uses
`imagePullPolicy: IfNotPresent`, so it will use the local `ai-studio:1.0`.
(For k3s: `docker save ai-studio:1.0 | sudo k3s ctr images import -`.
For kind: `kind load docker-image ai-studio:1.0`.
For minikube: `minikube image load ai-studio:1.0`.)

### 2. Create the namespace and config

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-configmap.yaml
```

### 3. Create the Secret with your real key (not committed to git)

```bash
kubectl -n ai-studio create secret generic ai-studio-secret \
  --from-literal=OPENAI_API_KEY="sk-your-real-key"
```

### 4. Deploy the app

```bash
kubectl apply -f k8s/03-deployment.yaml
kubectl apply -f k8s/04-service.yaml
```

Watch the pods come up:

```bash
kubectl -n ai-studio get pods -w
```

Wait until both show `READY 1/1`.

### 5. Open it

NodePort exposes it on every node at port **30080**:

```bash
kubectl -n ai-studio get nodes -o wide     # find a node's INTERNAL/EXTERNAL IP
# then open  http://<node-ip>:30080
```

No external node IP? Port-forward instead:

```bash
kubectl -n ai-studio port-forward svc/ai-studio 8000:80
# open http://localhost:8000
```

---

## Part C — The cool k8s bits to demo

### See load-balancing across pods

Each answer shows `served by pod <name>`. Hit **Run** a few times and refresh —
you'll see different pod names as the Service spreads traffic. Or watch from the
CLI:

```bash
watch -n1 'curl -s http://<node-ip>:30080/api/info'
```

### Scale up and down by hand

```bash
kubectl -n ai-studio scale deployment ai-studio --replicas=5
kubectl -n ai-studio get pods         # five pods now share the traffic
kubectl -n ai-studio scale deployment ai-studio --replicas=2
```

### Autoscaling (HPA)

Needs metrics-server (`kubectl top pods -n ai-studio` should return numbers).

```bash
kubectl apply -f k8s/05-hpa.yaml
kubectl -n ai-studio get hpa -w        # watch replicas rise under load
```

### Self-healing

Delete a pod and Kubernetes recreates it:

```bash
kubectl -n ai-studio delete pod <one-pod-name>
kubectl -n ai-studio get pods          # a new one is already coming up
```

### Optional: nice URL via Ingress

Only if you have an ingress controller (e.g. ingress-nginx):

```bash
kubectl apply -f k8s/06-ingress.yaml
# add "<node-ip> ai-studio.local" to /etc/hosts, then open http://ai-studio.local
```

---

## API reference

| Method | Path | Body | Purpose |
|--------|------|------|---------|
| GET  | `/` | — | Web UI |
| GET  | `/api/info` | — | `{pod, model, key_loaded}` |
| GET  | `/healthz` | — | Liveness probe |
| GET  | `/readyz` | — | Readiness probe (needs key) |
| POST | `/api/summarize` | `{text}` | Bullet-point summary |
| POST | `/api/translate` | `{text, target_language}` | Translation |
| POST | `/api/sentiment` | `{text}` | `{sentiment, score, reason}` |
| POST | `/api/rewrite` | `{text, tone}` | Tone rewrite |
| POST | `/api/explain` | `{text, level}` | Simple explanation |

Example:

```bash
curl -X POST http://<node-ip>:30080/api/summarize \
  -H "Content-Type: application/json" \
  -d '{"text": "Kubernetes is an open-source system for automating deployment, scaling, and management of containerized applications..."}'
```

Interactive docs are auto-generated at `/docs`.

---

## Security notes

- The API key lives only in a Kubernetes **Secret**, injected as an env var at
  run time — never baked into the image or committed to git.
- `.dockerignore` keeps `.env` out of the image; `.gitignore` keeps real keys
  and `k8s/secret.yaml` out of the repo.
- `02-secret.example.yaml` is a template only — create the real Secret with
  `kubectl create secret`.

## Cleanup

```bash
kubectl delete namespace ai-studio     # removes everything in one go
```

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `unexpected keyword argument 'proxies'` | httpx too new for the OpenAI SDK | Already fixed — `httpx==0.27.2` is pinned |
| Pod stuck `0/1` / readiness failing | No key in the Secret | Recreate `ai-studio-secret` with a real key |
| `ImagePullBackOff` | Cluster can't find the image | Push to a registry and set `image:`, or load it locally (Part B step 1) |
| HPA shows `<unknown>` targets | No metrics-server | Install metrics-server |
| `insufficient_quota` from OpenAI | Key has no credit | Add billing credit |
