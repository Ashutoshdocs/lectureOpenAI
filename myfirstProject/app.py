"""
Simple AI Chat app using FastAPI + OpenAI.

Serves:
  GET  /            -> the chat web page (frontend/index.html)
  GET  /health      -> JSON status/info
  POST /ask         -> { "question": "..." } returns { "answer": "..." }

The OpenAI API key is read from the OPENAI_API_KEY environment variable.
It is NEVER hard-coded in this file or baked into the Docker image.
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI, OpenAIError

# Read config from environment.
API_KEY = os.getenv("OPENAI_API_KEY")
# gpt-4o-mini is cheap and works well for a demo. Override with OPENAI_MODEL env var.
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

app = FastAPI(title="OpenAI + Docker Demo", version="2.0.0")

# Create the client once. If the key is missing we still start up so that
# the error is clear at request time instead of crashing the container.
client = OpenAI(api_key=API_KEY) if API_KEY else None


class Question(BaseModel):
    question: str


@app.get("/")
def home():
    # Serve the chat page.
    return FileResponse("frontend/index.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL,
        "key_loaded": bool(API_KEY),
    }


@app.post("/ask")
def ask(payload: Question):
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not set. Pass it to the container with --env-file .env",
        )

    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Answer clearly and concisely."},
                {"role": "user", "content": payload.question},
            ],
        )
        answer = response.choices[0].message.content
        return {"answer": answer}
    except OpenAIError as e:
        # Common causes: invalid key, no credit/quota, rate limit.
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")
