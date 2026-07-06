#!/usr/bin/env python3
"""monkeyVerse v3 entry point — the observable living planet.

    python main3.py
    HOST=0.0.0.0 PORT=8002 MONKEYVERSE_DATA=data3 python main3.py

Open http://<raspberry-ip>:8002 from any device on your network. Runs
alongside v1 (port 8000) and v2 (port 8001) without conflict.
"""

from __future__ import annotations

import os

import uvicorn

from monkeyverse3.server import create_app


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8002"))
    data_dir = os.environ.get("MONKEYVERSE_DATA", "data3")
    app = create_app(data_dir=data_dir)
    print(f"monkeyVerse v3 :: http://{host}:{port}  (data: {os.path.abspath(data_dir)})")
    uvicorn.run(app, host=host, port=port, log_level="warning", ws_ping_interval=None)


if __name__ == "__main__":
    main()
