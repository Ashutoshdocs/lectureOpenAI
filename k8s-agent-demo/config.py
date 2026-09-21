"""Central configuration, loaded from environment / .env."""
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# "mock" (default) or "real"
CLUSTER_MODE = os.getenv("CLUSTER_MODE", "mock").strip().lower()

K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
K8S_DEPLOYMENT = os.getenv("K8S_DEPLOYMENT", "web-api")

MAX_STEPS = int(os.getenv("MAX_STEPS", "12"))


def validate() -> None:
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-...") is True:
        raise SystemExit(
            "OPENAI_API_KEY is missing.\n"
            "  1. cp .env.example .env\n"
            "  2. put your real key in .env\n"
        )
    if CLUSTER_MODE not in ("mock", "real"):
        raise SystemExit(f"CLUSTER_MODE must be 'mock' or 'real', got '{CLUSTER_MODE}'")
