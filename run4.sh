#!/usr/bin/env bash
# Start monkeyVerse v4 (Isla Simple). Creates a local virtualenv on first run.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
VENV=".venv"
if [ ! -d "$VENV" ]; then
  echo "[monkeyVerse v4] creating virtualenv..."
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r requirements.txt
fi
export HOST="${HOST:-0.0.0.0}"
# 8003: v1 owns 8000, v2 owns 8001, v3 owns 8002.
export PORT="${PORT:-8003}"
export MONKEYVERSE_DATA="${MONKEYVERSE_DATA:-data4}"
exec "$VENV/bin/python" main4.py
