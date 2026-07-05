#!/usr/bin/env python3
"""monkeyVerse entry point.

Usage:
    python main.py                      # serve on 0.0.0.0:8000
    HOST=0.0.0.0 PORT=8080 python main.py
    MONKEYVERSE_DATA=/mnt/ssd/mv python main.py

Open http://<raspberry-ip>:8000 from any device on your network.
"""

from __future__ import annotations

import os

import uvicorn

from monkeyverse.server import create_app


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    data_dir = os.environ.get("MONKEYVERSE_DATA", "data")

    app = create_app(data_dir=data_dir)
    print(f"monkeyVerse :: http://{host}:{port}  (data: {os.path.abspath(data_dir)})")
    uvicorn.run(app, host=host, port=port, log_level="warning", ws_ping_interval=None)


if __name__ == "__main__":
    main()
