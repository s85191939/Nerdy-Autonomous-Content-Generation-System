#!/usr/bin/env bash
# Run Nerdy Autonomous Content Generation System locally (web UI).
# Usage:
#   ./scripts/run_local.sh              # launches web UI at http://127.0.0.1:8080

set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# 1. Venv
if [ ! -d "$ROOT/venv" ]; then
  echo "Creating venv..."
  python3 -m venv "$ROOT/venv"
fi
echo "Activating venv..."
# shellcheck source=/dev/null
source "$ROOT/venv/bin/activate"

# 2. Dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# 3. API key
if [ -z "${GEMINI_API_KEY:-}" ] && [ -z "${GOOGLE_API_KEY:-}" ]; then
  if [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ROOT/.env"
    set +a
  fi
fi
if [ -z "${GEMINI_API_KEY:-}" ] && [ -z "${GOOGLE_API_KEY:-}" ]; then
  echo "Error: Set GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment or in .env"
  exit 1
fi

# 4. Launch web UI
echo "Starting web UI at http://127.0.0.1:8080 ..."
exec python -c "from web.app import app; app.run(host='0.0.0.0', port=8080, debug=False)"
