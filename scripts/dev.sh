#!/usr/bin/env bash
# Convenience script: runs the backend API and the frontend dev server
# together. Stop with Ctrl+C.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT

cd "$ROOT_DIR/backend"
if [ ! -d .venv ]; then
  echo "Creating backend virtualenv..."
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
python -m analyzer server --reload &

cd "$ROOT_DIR/frontend"
if [ ! -d node_modules ]; then
  echo "Installing frontend dependencies..."
  npm install
fi
npm run dev &

wait
