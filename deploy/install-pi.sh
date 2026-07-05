#!/usr/bin/env bash
# One-shot installer for a Raspberry Pi (Raspberry Pi OS / Debian based).
# Clones nothing — run it from inside the cloned repository.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

echo "==> monkeyVerse install (dir: $HERE)"

# 1. system deps (numpy wheels usually need nothing extra on 64-bit Pi OS)
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip
fi

# 2. virtualenv + python deps
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# 3. systemd service (optional, for 24/7 operation)
read -r -p "Install systemd service so it runs 24/7 and on boot? [y/N] " ans
if [[ "${ans,,}" == "y" ]]; then
  USER_NAME="$(whoami)"
  TMP="$(mktemp)"
  sed -e "s#User=pi#User=${USER_NAME}#g" \
      -e "s#/home/pi/monkeyVerse#${HERE}#g" \
      deploy/monkeyverse.service > "$TMP"
  sudo cp "$TMP" /etc/systemd/system/monkeyverse.service
  rm -f "$TMP"
  sudo systemctl daemon-reload
  sudo systemctl enable monkeyverse
  sudo systemctl restart monkeyverse
  echo "==> Service installed. Status: sudo systemctl status monkeyverse"
  IP="$(hostname -I | awk '{print $1}')"
  echo "==> Open http://${IP}:8000 from any device on your network."
else
  echo "==> Done. Start manually with: ./run.sh"
fi
