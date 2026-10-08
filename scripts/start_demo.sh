#!/usr/bin/env bash
# Memoria demo launcher (Unix). Run from anywhere; uses the repo that contains this script.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "BLOCKED: '$1' is not on PATH. Install it, then re-run this script."
    exit 1
  fi
}

need ollama
need docker

echo "Checking Ollama..."
if ! ollama list >/dev/null 2>&1; then
  echo "BLOCKED: Ollama did not respond. Start the Ollama service, then re-run."
  exit 1
fi

LIST="$(ollama list || true)"
MISSING=()
echo "$LIST" | grep -q "phi3:mini" || MISSING+=("phi3:mini")
echo "$LIST" | grep -q "nomic-embed-text" || MISSING+=("nomic-embed-text")
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "Required Ollama models are missing. Pull them, then re-run:"
  for model in "${MISSING[@]}"; do
    echo "  ollama pull $model"
  done
  exit 1
fi

export LLM_MODEL="${LLM_MODEL:-phi3:mini}"
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-nomic-embed-text}"
echo "Starting Docker Compose (build if needed). LLM_MODEL=$LLM_MODEL EMBEDDING_MODEL=$EMBEDDING_MODEL"
if ! docker compose up --build -d; then
  echo "BLOCKED: docker compose up failed. Install Docker, start it, then retry from the repo root."
  exit 1
fi

port_open() {
  python -c 'import socket, sys
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    s.close()' "$1"
}

echo "Waiting for MCP :8765 and Streamlit :8501..."
for _ in $(seq 1 90); do
  if port_open 8765 && port_open 8501; then
    echo "Memoria is running at http://localhost:8501"
    exit 0
  fi
  sleep 2
done

echo "BLOCKED: compose started but ports 8765/8501 did not open within 3 minutes."
echo "Manual check: docker compose ps ; docker compose logs"
exit 1
