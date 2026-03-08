#!/usr/bin/env bash
# One-time setup: venv + install deps. Run before first use.
# Usage: ./scripts/setup_local.sh

set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "Creating venv at $ROOT/venv ..."
python3 -m venv "$ROOT/venv"
# shellcheck source=/dev/null
source "$ROOT/venv/bin/activate"
echo "Installing dependencies..."
pip install -r requirements.txt
echo "Done. Activate with: source venv/bin/activate"
echo "Then set GEMINI_API_KEY and run: ./scripts/run_local.sh"
