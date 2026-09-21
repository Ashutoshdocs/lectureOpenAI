# OpenAI + Docker Demo

A tiny AI chat API that runs inside a Docker container and calls the OpenAI API.

```
Browser / curl  ->  Docker container (FastAPI + OpenAI SDK)  ->  OpenAI API  ->  answer
```

## Project structure

```
openai-docker-demo/
├── app.py                # FastAPI app: serves the page + /ask API
├── frontend/
│   └── index.html        # The chat web page (type a question, see the answer)
├── requirements.txt      # Python dependencies
├── Dockerfile            # How to build the image
├── .dockerignore         # Files kept out of the image
├── .env.example          # Template for your API key
└── README.md
```

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed and running
- An OpenAI API key from https://platform.openai.com/api-keys

> **Note on "free" keys:** OpenAI no longer has a permanently free tier. New
> accounts sometimes get limited trial credits. If your key returns a
> `quota` / `insufficient_quota` error, the key is valid but has no credit —
> you'll need to add a small amount of billing to use it. The demo uses
> `gpt-4o-mini`, the cheapest model, so a few test calls cost a fraction of a cent.

## 1. Get your API key ready

Copy the template and paste your real key into `.env`:

```bash
cp .env.example .env
# then edit .env and replace sk-your-key-here with your real key
```

The key is only used at run time. It is **never** written into the code or the
Docker image — that's the whole point of passing it as an environment variable.

## 2. (Optional) Run locally without Docker first

Good for confirming the code works before containerizing.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export OPENAI_API_KEY="sk-your-key-here"   # Windows PowerShell: $env:OPENAI_API_KEY="sk-..."
uvicorn app:app --reload --port 8000
```

Visit http://localhost:8000 — you should see the chat page.

## 3. Build the Docker image

```bash
docker build -t openai-demo .
```

## 4. Run the container

Pass the key in securely at run time. Two ways:

**Using the `.env` file (recommended):**

```bash
docker run -p 8000:8000 --env-file .env openai-demo
```

**Passing the key inline:**

```bash
docker run -p 8000:8000 \
  -e OPENAI_API_KEY="sk-your-key-here" \
  openai-demo
```

The app is now on http://localhost:8000.

## 5. Use it

Open **http://localhost:8000** in your browser. Type a question in the box,
click **Ask** (or press Ctrl/Cmd + Enter), and the answer appears below.

Prefer the command line? The JSON API is still there:

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain Docker in simple terms"}'
```

Expected response:

```json
{ "answer": "Docker is a platform that packages an application..." }
```

Interactive API docs are also auto-generated at **http://localhost:8000/docs**.

## Why the key is passed at run time (not in the Dockerfile)

- Anyone who has the image could read a key baked into it with `docker history`.
- Images often get pushed to registries — the key would leak.
- The same image should run in dev, test, and prod with **different** keys.

So: the image stays secret-free, and the secret is injected only when the
container runs.

## Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `OPENAI_API_KEY is not set` | No key passed to the container | Add `--env-file .env` or `-e OPENAI_API_KEY=...` |
| `insufficient_quota` | Key valid but no credit | Add billing credit to your OpenAI account |
| `invalid_api_key` | Wrong/typo'd key | Recheck the key in `.env` |
| Port already in use | 8000 taken | Use another host port: `-p 8080:8000` |

## Stopping the container

```bash
docker ps            # find the container id
docker stop <id>
```
