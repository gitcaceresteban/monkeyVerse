"""Observer API for v2: control, analytics, the species tree, the milestone
chronicle, god-mode interventions and the time machine (frame scrubbing).
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .config import SimConfig, CONFIG_SCHEMA
from .manager import Manager

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web2")


def create_app(data_dir: str = "data2") -> FastAPI:
    manager = Manager(base_dir=data_dir)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        manager.shutdown()

    app = FastAPI(title="monkeyVerse v2", version="2.0.0", lifespan=lifespan)
    app.state.manager = manager

    @app.get("/api/config/schema")
    def schema():
        return {"schema": CONFIG_SCHEMA, "defaults": SimConfig().to_dict()}

    @app.get("/api/simulations")
    def sims():
        return manager.list()

    @app.post("/api/simulations")
    def create(payload: dict[str, Any]):
        cfg = SimConfig.from_dict(payload or {})
        cfg.width = int(max(32, min(320, cfg.width)))
        cfg.height = int(max(32, min(320, cfg.height)))
        cfg.max_population = int(max(2, min(6000, cfg.max_population)))
        cfg.initial_population = int(max(1, min(cfg.max_population, cfg.initial_population)))
        return {"id": manager.create(cfg)}

    @app.post("/api/simulations/{sid}/fork")
    def fork(sid: str, payload: dict[str, Any] | None = None):
        nid = manager.fork(sid, (payload or {}).get("name"))
        if not nid:
            raise HTTPException(404, "not found")
        return {"id": nid}

    @app.delete("/api/simulations/{sid}")
    def delete(sid: str):
        if not manager.delete(sid):
            raise HTTPException(404, "not found")
        return {"ok": True}

    @app.get("/api/simulations/{sid}/state")
    def state(sid: str):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        return r.render_state()

    @app.post("/api/simulations/{sid}/control")
    def control(sid: str, payload: dict[str, Any]):
        if not manager.control(sid, payload.get("action"), payload.get("value")):
            raise HTTPException(400, "invalid")
        return {"ok": True}

    @app.post("/api/simulations/{sid}/intervene")
    def intervene(sid: str, payload: dict[str, Any]):
        if not manager.intervene(sid, payload.get("kind"), payload.get("params", {})):
            raise HTTPException(400, "invalid")
        return {"ok": True}

    @app.get("/api/simulations/{sid}/stats")
    def stats(sid: str, since: int = 0, limit: int = 4000):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        return r.persistence.stats_series(since, limit)

    @app.get("/api/simulations/{sid}/milestones")
    def milestones(sid: str, limit: int = 200):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        return r.persistence.milestones_list(limit)

    @app.get("/api/simulations/{sid}/events")
    def events(sid: str, limit: int = 80):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        return r.persistence.recent_events(limit)

    @app.get("/api/simulations/{sid}/species")
    def species(sid: str):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        with r.lock:
            living = r.sim.species.living()
        return {"living": living, "tree": r.persistence.species_tree()}

    @app.get("/api/simulations/{sid}/summary")
    def summary(sid: str):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        return r.persistence.summary()

    @app.get("/api/simulations/{sid}/agent/{aid}")
    def agent(sid: str, aid: int):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        with r.lock:
            live = r.sim.agent_detail(aid)
        return {"live": live, "genealogy": r.persistence.agent_genealogy(aid)}

    # ------------------------------------------------------------- time machine
    @app.get("/api/simulations/{sid}/frames")
    def frames(sid: str):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        return {"ticks": r.persistence.frame_ticks()}

    @app.get("/api/simulations/{sid}/frame")
    def frame(sid: str, tick: int = 0):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        f = r.persistence.get_frame(tick)
        if f is None:
            raise HTTPException(404, "no frames yet")
        return f

    @app.websocket("/ws/{sid}")
    async def ws(websocket: WebSocket, sid: str):
        import asyncio
        await websocket.accept()
        interval = 0.13
        try:
            while True:
                r = manager.get(sid)
                if not r:
                    await websocket.send_json({"error": "not found"}); break
                await websocket.send_json(r.render_state())
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

    if os.path.isdir(WEB_DIR):
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
