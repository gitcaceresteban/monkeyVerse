#!/usr/bin/env bash
# One-shot installer for monkeyVerse v3 on a Raspberry Pi (Raspberry Pi OS /
# Debian based). Run it from inside the cloned repository, on the
# claude/digital-ecosystem-sim-v3-7zzf9w branch.
#
# Safe to run even if v1 and/or v2 are already installed and running: this
# script only touches the shared .venv (reused, not recreated) and installs
# its own systemd unit (monkeyverse3.service) on its own port (8002), so it
# won't disturb monkeyverse.service (8000) or monkeyverse2.service (8001).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

echo "==> monkeyVerse v3 install (dir: $HERE)"

# 1. system deps (numpy wheels usually need nothing extra on 64-bit Pi OS)
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip
fi

# 2. virtualenv + python deps (shared with v1/v2 — reused if it already exists)
if [ ! -d ".venv" ]; then
  echo "==> creating virtualenv..."
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
else
  echo "==> reusing existing .venv"
fi
./.venv/bin/pip install -r requirements.txt

# 3. sanity check: make sure this checkout actually has v3
if [ ! -f "main3.py" ] || [ ! -d "monkeyverse3" ]; then
  echo "ERROR: main3.py / monkeyverse3/ not found. Are you on the v3 branch?" >&2
  echo "        git checkout claude/digital-ecosystem-sim-v3-7zzf9w" >&2
  exit 1
fi

# 4. systemd service (optional, for 24/7 operation)
read -r -p "Install systemd service so monkeyVerse v3 runs 24/7 and on boot? [y/N] " ans
if [[ "${ans,,}" == "y" ]]; then
  USER_NAME="$(whoami)"
  TMP="$(mktemp)"
  sed -e "s#User=pi#User=${USER_NAME}#g" \
      -e "s#/home/pi/monkeyVerse#${HERE}#g" \
      deploy/monkeyverse3.service > "$TMP"
  sudo cp "$TMP" /etc/systemd/system/monkeyverse3.service
  rm -f "$TMP"
  sudo systemctl daemon-reload
  sudo systemctl enable monkeyverse3
  sudo systemctl restart monkeyverse3
  echo "==> Service installed. Status: sudo systemctl status monkeyverse3"
  IP="$(hostname -I | awk '{print $1}')"
  echo "==> Open http://${IP}:8002 from any device on your network."
else
  echo "==> Done. Start manually with: ./run3.sh   (defaults to port 8002)"
fi
