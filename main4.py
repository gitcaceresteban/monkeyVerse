#!/usr/bin/env python3
"""monkeyVerse v4 entry point — Isla Simple (Simple Island).

    python main4.py
    HOST=0.0.0.0 PORT=8003 MONKEYVERSE_DATA=data4 python main4.py

Open http://<raspberry-ip>:8003 from any device on your network. Runs alongside
v1 (8000), v2 (8001) and v3 (8002) without conflict. This version is deliberately
small, slow and observable: 20 agents (10 A + 10 B) on a little island, learning,
making sounds and forming bonds in real time.
"""

from __future__ import annotations

import os

import uvicorn

from monkeyverse4.server import create_app


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8003"))
    data_dir = os.environ.get("MONKEYVERSE_DATA", "data4")
    app = create_app(data_dir=data_dir)
    print(f"monkeyVerse v4 (Isla Simple) :: http://{host}:{port}  (data: {os.path.abspath(data_dir)})")
    uvicorn.run(app, host=host, port=port, log_level="warning", ws_ping_interval=None)


if __name__ == "__main__":
    main()
