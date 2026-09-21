"""
AI Studio — a small FastAPI app that does more than chat.

Tools (all powered by the OpenAI API):
  POST /api/summarize   -> summarize long text
  POST /api/translate   -> translate to a target language
  POST /api/sentiment   -> sentiment + short reasoning (JSON)
  POST /api/rewrite     -> rewrite text in a chosen tone
  POST /api/explain     -> explain a topic simply ("like I'm 5")

Operational endpoints (useful for Kubernetes):
  GET  /            -> the web UI
  GET  /api/info    -> which pod/model served you (great for showing load-balancing)
  GET  /healthz     -> liveness probe
  GET  /readyz      -> readiness probe (checks the API key is present)

The OpenAI API key comes from the OPENAI_API_KEY environment variable, which in
Kubernetes is injected from a Secret. It is never baked into the image.
"""

import os
import socket
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI, OpenAIError

API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# Kubernetes injects the pod name via the downward API (see deployment.yaml).
# Falls back to the container hostname, which is also the pod name by default.
POD_NAME = os.getenv("POD_NAME", socket.gethostname())

app = FastAPI(title="AI Studio", version="1.0.0")

client = OpenAI(api_key=API_KEY) if API_KEY else None


# ---------- request models ----------
class TextIn(BaseModel):
    text: str


class TranslateIn(BaseModel):
    text: str
    target_language: str = "French"


class RewriteIn(BaseModel):
    text: str
    tone: str = "professional"


class ExplainIn(BaseModel):
    text: str
    level: str = "a 5-year-old"


# ---------- helpers ----------
def _require_client():
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not set. In Kubernetes this comes from the Secret.",
        )


def _chat(system: str, user: str, json_mode: bool = False) -> str:
    _require_client()
    if not user.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    try:
        kwargs = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")


def _wrap(result: str, extra: dict | None = None) -> dict:
    # Every response carries the pod name so the UI can show who served it.
    out = {"result": result, "pod": POD_NAME, "model": MODEL}
    if extra:
        out.update(extra)
    return out


# ---------- pages / ops ----------
@app.get("/")
def home():
    return FileResponse("frontend/index.html")


@app.get("/api/info")
def info():
    return {"pod": POD_NAME, "model": MODEL, "key_loaded": bool(API_KEY)}


@app.get("/healthz")
def healthz():
    # Liveness: the process is up.
    return {"status": "alive", "pod": POD_NAME}


@app.get("/readyz")
def readyz():
    # Readiness: don't send traffic until the key is configured.
    if not API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    return {"status": "ready", "pod": POD_NAME}


# ---------- AI tools ----------
@app.post("/api/summarize")
def summarize(payload: TextIn):
    system = "You summarize text into 3-5 clear bullet points. Be concise and factual."
    return _wrap(_chat(system, payload.text))


@app.post("/api/translate")
def translate(payload: TranslateIn):
    system = (
        f"You are a translator. Translate the user's text into {payload.target_language}. "
        "Return only the translation, no explanations."
    )
    return _wrap(_chat(system, payload.text), {"target_language": payload.target_language})


@app.post("/api/sentiment")
def sentiment(payload: TextIn):
    system = (
        "Analyze the sentiment of the text. Respond as JSON with keys: "
        '"sentiment" (positive, neutral, or negative), '
        '"score" (a number from -1 to 1), and "reason" (one short sentence).'
    )
    raw = _chat(system, payload.text, json_mode=True)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"sentiment": "unknown", "score": 0, "reason": raw}
    return _wrap("", parsed)


@app.post("/api/rewrite")
def rewrite(payload: RewriteIn):
    system = (
        f"Rewrite the user's text in a {payload.tone} tone. "
        "Keep the meaning the same. Return only the rewritten text."
    )
    return _wrap(_chat(system, payload.text), {"tone": payload.tone})


@app.post("/api/explain")
def explain(payload: ExplainIn):
    system = (
        f"Explain the following so that {payload.level} could understand it. "
        "Use simple words and a friendly tone."
    )
    return _wrap(_chat(system, payload.text), {"level": payload.level})
