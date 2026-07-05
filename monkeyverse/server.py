"""The observer's window into every world.

A small FastAPI app: REST for control/history and a WebSocket that streams the
live state of a world at a few frames per second. Static files (the UI) are
served from ../web. Designed to be reachable from another machine on your LAN so
you can watch your Raspberry Pi like an omnipresent entity.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import SimConfig, CONFIG_SCHEMA
from .manager import Manager

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def create_app(data_dir: str = "data") -> FastAPI:
    manager = Manager(base_dir=data_dir)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        manager.shutdown()

    app = FastAPI(title="monkeyVerse", version="1.0.0", lifespan=lifespan)
    app.state.manager = manager

    # ------------------------------------------------------------------ config
    @app.get("/api/config/schema")
    def config_schema():
        return {"schema": CONFIG_SCHEMA, "defaults": SimConfig().to_dict()}

    # ------------------------------------------------------------- simulations
    @app.get("/api/simulations")
    def list_sims():
        return manager.list()

    @app.post("/api/simulations")
    async def create_sim(payload: dict[str, Any]):
        cfg = SimConfig.from_dict(payload or {})
        # sanity clamps to protect the host
        cfg.width = int(max(16, min(512, cfg.width)))
        cfg.height = int(max(16, min(512, cfg.height)))
        cfg.max_population = int(max(2, min(8000, cfg.max_population)))
        cfg.initial_population = int(max(1, min(cfg.max_population, cfg.initial_population)))
        sid = manager.create(cfg)
        return {"id": sid}

    @app.delete("/api/simulations/{sim_id}")
    def delete_sim(sim_id: str):
        if not manager.delete(sim_id):
            raise HTTPException(404, "simulation not found")
        return {"ok": True}

    @app.get("/api/simulations/{sim_id}/state")
    def sim_state(sim_id: str):
        r = manager.get(sim_id)
        if not r:
            raise HTTPException(404, "simulation not found")
        return r.render_state()

    @app.post("/api/simulations/{sim_id}/control")
    def sim_control(sim_id: str, payload: dict[str, Any]):
        ok = manager.control(sim_id, payload.get("action"), payload.get("value"))
        if not ok:
            raise HTTPException(400, "invalid control")
        return {"ok": True}

    @app.post("/api/simulations/{sim_id}/intervene")
    def sim_intervene(sim_id: str, payload: dict[str, Any]):
        ok = manager.intervene(sim_id, payload.get("kind"), payload.get("params", {}))
        if not ok:
            raise HTTPException(400, "invalid intervention")
        return {"ok": True}

    @app.get("/api/simulations/{sim_id}/stats")
    def sim_stats(sim_id: str, since: int = 0, limit: int = 4000):
        r = manager.get(sim_id)
        if not r:
            raise HTTPException(404, "simulation not found")
        return r.persistence.stats_series(since=since, limit=limit)

    @app.get("/api/simulations/{sim_id}/events")
    def sim_events(sim_id: str, limit: int = 60):
        r = manager.get(sim_id)
        if not r:
            raise HTTPException(404, "simulation not found")
        return r.persistence.recent_events(limit=limit)

    @app.get("/api/simulations/{sim_id}/summary")
    def sim_summary(sim_id: str):
        r = manager.get(sim_id)
        if not r:
            raise HTTPException(404, "simulation not found")
        return r.persistence.summary()

    @app.get("/api/simulations/{sim_id}/agent/{agent_id}")
    def sim_agent(sim_id: str, agent_id: int):
        r = manager.get(sim_id)
        if not r:
            raise HTTPException(404, "simulation not found")
        live = r.sim.agent_detail(agent_id)
        genealogy = r.persistence.agent_genealogy(agent_id)
        return {"live": live, "genealogy": genealogy}

    # --------------------------------------------------------------- websocket
    @app.websocket("/ws/{sim_id}")
    async def ws_stream(websocket: WebSocket, sim_id: str):
        await websocket.accept()
        interval = 0.12
        try:
            while True:
                r = manager.get(sim_id)
                if not r:
                    await websocket.send_json({"error": "not found"})
                    break
                await websocket.send_json(r.render_state())
                # allow the client to request a different rate
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=interval)
                    if msg.startswith("rate:"):
                        interval = max(0.05, min(2.0, float(msg.split(":", 1)[1])))
                except asyncio.TimeoutError:
                    pass
        except WebSocketDisconnect:
            pass
        except Exception:
            with contextlib.suppress(Exception):
                await websocket.close()

    @app.get("/api/health")
    def health():
        return {"ok": True, "simulations": len(manager.runners)}

    # ------------------------------------------------------------------ static
    if os.path.isdir(WEB_DIR):
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    return app
