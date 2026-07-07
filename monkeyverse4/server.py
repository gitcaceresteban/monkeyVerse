"""Observer API for v4 Simple Island.

Thin FastAPI layer over the Manager: create/reset/delete islands, stream world
state over a WebSocket, inspect a single agent (with the decision trace the
"debug" view needs), read the communication / reproduction / analysis reports,
and download the structured logs (full-run JSON, events CSV, metrics CSV,
genealogy, living agents). Speed is controlled live — pause / 0.5× / 1× / 2× / 5×.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .config import Config, CONFIG_SCHEMA, SPEED_PRESETS, N_SOUNDS
from .manager import Manager
from .metrics import CONTEXTS, RESPONSES, auto_analysis

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web4")


def _json(data: Any, filename: str, media="application/json") -> Response:
    body = data if isinstance(data, str) else json.dumps(data, default=str, ensure_ascii=False)
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def create_app(data_dir: str = "data/mv4", autostart: bool = True) -> FastAPI:
    manager = Manager(data_dir=data_dir)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if autostart and not manager.runners:
            manager.create(Config(name="isla"))
        yield
        manager.stop_all()

    app = FastAPI(title="monkeyVerse v4 — Isla Simple", version="4.0.0", lifespan=lifespan)
    app.state.manager = manager

    def _need(sid: str):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "isla no encontrada")
        return r

    # ------------------------------------------------------------- config / list
    @app.get("/api/config/schema")
    def schema():
        return {"schema": CONFIG_SCHEMA, "defaults": Config().to_dict(),
                "speed_presets": SPEED_PRESETS, "n_sounds": N_SOUNDS,
                "contexts": CONTEXTS, "responses": RESPONSES}

    @app.get("/api/simulations")
    def sims():
        return manager.list()

    @app.post("/api/simulations")
    def create(payload: dict[str, Any] | None = None):
        cfg = Config.from_dict(payload or {})
        cfg.map_size = int(max(30, min(100, cfg.map_size)))
        cfg.initial_a = int(max(1, min(40, cfg.initial_a)))
        cfg.initial_b = int(max(1, min(40, cfg.initial_b)))
        cfg.initial_agents = cfg.initial_a + cfg.initial_b
        cfg.max_agents = int(max(cfg.initial_agents, min(200, cfg.max_agents)))
        r = manager.create(cfg)
        return {"id": r.sim.id}

    @app.delete("/api/simulations/{sid}")
    def delete(sid: str):
        if not manager.delete(sid):
            raise HTTPException(404, "no encontrada")
        return {"ok": True}

    @app.post("/api/simulations/{sid}/reset")
    def reset(sid: str):
        r = manager.reset(sid)
        if not r:
            raise HTTPException(404, "no encontrada")
        return {"id": r.sim.id}

    # ------------------------------------------------------------- control
    @app.post("/api/simulations/{sid}/speed")
    def speed(sid: str, payload: dict[str, Any]):
        r = _need(sid)
        r.set_speed(float(payload.get("speed", 1.0)))
        return {"ok": True, "speed": r.speed, "status": r.status}

    @app.get("/api/simulations/{sid}/state")
    def state(sid: str):
        r = _need(sid)
        with r.lock:
            return r.sim.render_state()

    @app.get("/api/simulations/{sid}/island")
    def island(sid: str):
        r = _need(sid)
        with r.lock:
            return r.sim.island_render()

    # ------------------------------------------------------------- inspection
    @app.get("/api/simulations/{sid}/agent/{aid}")
    def agent(sid: str, aid: int):
        r = _need(sid)
        with r.lock:
            d = r.sim.agent_detail(aid)
        if d is None:
            raise HTTPException(404, "agente no encontrado")
        return d

    @app.get("/api/simulations/{sid}/communication")
    def communication(sid: str):
        r = _need(sid)
        with r.lock:
            return r.sim.comm_report()

    @app.get("/api/simulations/{sid}/reproduction")
    def reproduction(sid: str):
        r = _need(sid)
        with r.lock:
            return r.sim.reproduction_report()

    @app.get("/api/simulations/{sid}/analysis")
    def analysis(sid: str):
        r = _need(sid)
        with r.lock:
            return auto_analysis(r.sim)

    @app.get("/api/simulations/{sid}/metrics")
    def metrics(sid: str, limit: int = 400):
        r = _need(sid)
        rows = r.store.all_metrics()
        return rows[-limit:]

    @app.get("/api/simulations/{sid}/events")
    def events(sid: str, limit: int = 120, type: Optional[str] = None,
               agent: Optional[int] = None):
        r = _need(sid)
        return r.store.recent_events(limit=limit, type_=type, agent=agent)

    # ------------------------------------------------------------- exports
    @app.get("/api/simulations/{sid}/export/run.json")
    def export_run(sid: str):
        r = _need(sid)
        with r.lock:
            data = {
                "id": sid, "tick": r.sim.tick, "seed": r.sim.seed,
                "config": r.cfg.to_dict(),
                "metrics_final": r.sim.metrics_row(),
                "communication": r.sim.comm_report(),
                "reproduction": r.sim.reproduction_report(),
                "analysis": auto_analysis(r.sim),
                "living_agents": [r.sim.agent_detail(a.id) for a in r.sim.agents],
                "genealogy": r.store.export_genealogy(),
            }
        return _json(data, f"{sid}-run.json")

    @app.get("/api/simulations/{sid}/export/events.csv")
    def export_events(sid: str):
        r = _need(sid)
        return _json(r.store.export_events_csv(), f"{sid}-events.csv", media="text/csv")

    @app.get("/api/simulations/{sid}/export/metrics.csv")
    def export_metrics(sid: str):
        r = _need(sid)
        return _json(r.store.export_metrics_csv(), f"{sid}-metrics.csv", media="text/csv")

    @app.get("/api/simulations/{sid}/export/genealogy.json")
    def export_genealogy(sid: str):
        r = _need(sid)
        return _json(r.store.export_genealogy(), f"{sid}-genealogy.json")

    @app.get("/api/simulations/{sid}/export/living.json")
    def export_living(sid: str):
        r = _need(sid)
        with r.lock:
            data = {"tick": r.sim.tick,
                    "agents": [r.sim.agent_detail(a.id) for a in r.sim.agents]}
        return _json(data, f"{sid}-living.json")

    # ------------------------------------------------------------- stream
    @app.websocket("/ws/{sid}")
    async def ws(websocket: WebSocket, sid: str):
        import asyncio
        await websocket.accept()
        interval = 0.15
        try:
            while True:
                r = manager.get(sid)
                if not r:
                    await websocket.send_json({"error": "not found"}); break
                with r.lock:
                    payload = r.sim.render_state()
                payload["runner"] = r.info()
                await websocket.send_json(payload)
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
