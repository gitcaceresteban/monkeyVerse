#!/usr/bin/env python3
"""monkeyVerse v2 entry point — the living planet.

    python main2.py
    HOST=0.0.0.0 PORT=8000 MONKEYVERSE_DATA=data2 python main2.py

Open http://<raspberry-ip>:8000 from any device on your network.
"""

from __future__ import annotations

import os

import uvicorn

from monkeyverse2.server import create_app


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    data_dir = os.environ.get("MONKEYVERSE_DATA", "data2")
    app = create_app(data_dir=data_dir)
    print(f"monkeyVerse v2 :: http://{host}:{port}  (data: {os.path.abspath(data_dir)})")
    uvicorn.run(app, host=host, port=port, log_level="warning", ws_ping_interval=None)


if __name__ == "__main__":
    main()
