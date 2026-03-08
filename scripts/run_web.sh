#!/usr/bin/env bash
# Start the web interface for the Nerdy Ad Engine.
# Usage: ./scripts/run_web.sh
# Then open http://localhost:8080

set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [ ! -d "$ROOT/venv" ]; then
  echo "Creating venv..."
  python3 -m venv "$ROOT/venv"
fi
# shellcheck source=/dev/null
source "$ROOT/venv/bin/activate"
pip install -q -r requirements.txt

if [ -z "${GEMINI_API_KEY:-}" ] && [ -z "${GOOGLE_API_KEY:-}" ] && [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
fi

echo "Starting web interface at http://127.0.0.1:8080"
echo "Set GEMINI_API_KEY in .env or environment to run the pipeline."
exec python -m web.app
