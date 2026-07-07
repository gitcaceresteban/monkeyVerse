#!/usr/bin/env bash
# Start monkeyVerse v3 (the observable living planet). Creates a local
# virtualenv on first run.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
VENV=".venv"
if [ ! -d "$VENV" ]; then
  echo "[monkeyVerse v3] creating virtualenv..."
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r requirements.txt
fi
export HOST="${HOST:-0.0.0.0}"
# 8002: v1 owns 8000, v2 owns 8001.
export PORT="${PORT:-8002}"
export MONKEYVERSE_DATA="${MONKEYVERSE_DATA:-data3}"
exec "$VENV/bin/python" main3.py
