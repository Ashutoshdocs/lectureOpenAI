#!/usr/bin/env bash
# Convenience launcher: sets up a venv, installs deps, runs the agent.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "› creating virtualenv (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "› installing dependencies"
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "› no .env found — copying from _env.example"
  cp _env.example .env
  echo "  !! edit .env and set OPENAI_API_KEY before running again"
  exit 1
fi

echo "› starting agent"
python agent.py
