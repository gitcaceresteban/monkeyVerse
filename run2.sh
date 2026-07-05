#!/usr/bin/env bash
# Start monkeyVerse v2 (the living planet). Creates a local virtualenv first run.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
VENV=".venv"
if [ ! -d "$VENV" ]; then
  echo "[monkeyVerse v2] creating virtualenv..."
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r requirements.txt
fi
export HOST="${HOST:-0.0.0.0}"
# 8001 by default: v1 (run.sh / monkeyverse.service) already owns port 8000.
export PORT="${PORT:-8001}"
export MONKEYVERSE_DATA="${MONKEYVERSE_DATA:-data2}"
exec "$VENV/bin/python" main2.py
