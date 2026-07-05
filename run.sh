#!/usr/bin/env bash
# Start monkeyVerse. Creates a local virtualenv on first run.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV=".venv"

if [ ! -d "$VENV" ]; then
  echo "[monkeyVerse] creating virtualenv..."
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r requirements.txt
fi

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export MONKEYVERSE_DATA="${MONKEYVERSE_DATA:-data}"

exec "$VENV/bin/python" main.py
