#!/usr/bin/env bash
# One-shot installer for monkeyVerse v4 (Isla Simple) on a Raspberry Pi
# (Raspberry Pi OS / Debian based). Run it from inside the cloned repository,
# on the feature/v4-simple-island branch.
#
# Safe to run even if v1/v2/v3 are already installed and running: this script
# only touches the shared .venv (reused, not recreated) and installs its own
# systemd unit (monkeyverse4.service) on its own port (8003), so it won't
# disturb monkeyverse.service (8000), monkeyverse2.service (8001) or
# monkeyverse3.service (8002).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

echo "==> monkeyVerse v4 install (dir: $HERE)"

# 1. system deps
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip
fi

# 2. virtualenv + python deps (shared with v1/v2/v3 — reused if it exists)
if [ ! -d ".venv" ]; then
  echo "==> creating virtualenv..."
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
else
  echo "==> reusing existing .venv"
fi
./.venv/bin/pip install -r requirements.txt

# 3. sanity check: make sure this checkout actually has v4
if [ ! -f "main4.py" ] || [ ! -d "monkeyverse4" ]; then
  echo "ERROR: main4.py / monkeyverse4/ not found. Are you on the v4 branch?" >&2
  echo "        git checkout feature/v4-simple-island" >&2
  exit 1
fi

# 4. systemd service (optional, for 24/7 operation)
read -r -p "Install systemd service so monkeyVerse v4 runs 24/7 and on boot? [y/N] " ans
if [[ "${ans,,}" == "y" ]]; then
  USER_NAME="$(whoami)"
  TMP="$(mktemp)"
  sed -e "s#User=pi#User=${USER_NAME}#g" \
      -e "s#/home/pi/monkeyVerse#${HERE}#g" \
      deploy/monkeyverse4.service > "$TMP"
  sudo cp "$TMP" /etc/systemd/system/monkeyverse4.service
  rm -f "$TMP"
  sudo systemctl daemon-reload
  sudo systemctl enable monkeyverse4
  sudo systemctl restart monkeyverse4
  echo "==> Service installed. Status: sudo systemctl status monkeyverse4"
  IP="$(hostname -I | awk '{print $1}')"
  echo "==> Open http://${IP}:8003 from any device on your network."
else
  echo "==> Done. Start manually with: ./run4.sh   (defaults to port 8003)"
fi
