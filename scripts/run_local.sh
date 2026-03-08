#!/usr/bin/env bash
# Run Nerdy Autonomous Content Generation System locally.
# Usage:
#   ./scripts/run_local.sh              # default: 50 ads, 6 max iterations
#   ./scripts/run_local.sh --num-ads 5   # quick test with 5 ads
#   ./scripts/run_local.sh --help        # show all CLI options

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

# 4. Run
echo "Running ad engine..."
exec python -m ad_engine.cli run --num-ads 50 --max-iterations 6 --seed 42 --output-dir "$ROOT/output" "$@"
