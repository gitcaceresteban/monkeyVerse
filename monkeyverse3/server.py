"""Observer API for v3: control, species/milestone chronicle, god-mode
interventions, the time machine, and the new observability surface —
per-agent detail, filterable interactions, language statistics, global
analytics, and data export.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import analytics as analytics_mod
from .config import SimConfig, CONFIG_SCHEMA
from .language import CONTEXTS, LEGEND, N_SYMBOLS
from .manager import Manager

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web3")


def create_app(data_dir: str = "data3") -> FastAPI:
    manager = Manager(base_dir=data_dir)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        manager.shutdown()

    app = FastAPI(title="monkeyVerse v3", version="3.0.0", lifespan=lifespan)
    app.state.manager = manager

    def _need(sid: str):
        r = manager.get(sid)
        if not r:
            raise HTTPException(404, "not found")
        return r

    @app.get("/api/config/schema")
    def schema():
        return {"schema": CONFIG_SCHEMA, "defaults": SimConfig().to_dict(),
                "language_legend": LEGEND, "n_symbols": N_SYMBOLS}

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
        return _need(sid).render_state()

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
        return _need(sid).persistence.stats_series(since, limit)

    @app.get("/api/simulations/{sid}/milestones")
    def milestones(sid: str, limit: int = 200):
        return _need(sid).persistence.milestones_list(limit)

    @app.get("/api/simulations/{sid}/events")
    def events(sid: str, limit: int = 80):
        return _need(sid).persistence.recent_events(limit)

    @app.get("/api/simulations/{sid}/species")
    def species(sid: str):
        r = _need(sid)
        with r.lock:
            living = r.sim.species.living()
        return {"living": living, "tree": r.persistence.species_tree()}

    @app.get("/api/simulations/{sid}/summary")
    def summary(sid: str):
        return _need(sid).persistence.summary()

    @app.get("/api/simulations/{sid}/agent/{aid}")
    def agent(sid: str, aid: int):
        r = _need(sid)
        with r.lock:
            live = r.sim.agent_detail(aid, full=True)
        total_desc = r.persistence.descendants_count(aid)
        if live and "reproduction" in live:
            live["reproduction"]["total_descendants"] = total_desc
        return {"live": live, "genealogy": r.persistence.agent_genealogy(aid)}

    @app.get("/api/simulations/{sid}/compare")
    def compare(sid: str, a: int, b: int):
        r = _need(sid)
        with r.lock:
            res = r.sim.compare(a, b)
        if res is None:
            raise HTTPException(404, "agent not found")
        return res

    @app.get("/api/simulations/{sid}/discoveries")
    def discoveries(sid: str, limit: int = 200):
        return _need(sid).persistence.discoveries_list(limit)

    @app.get("/api/simulations/{sid}/agent/{aid}/export.json")
    def agent_export(sid: str, aid: int):
        r = _need(sid)
        with r.lock:
            data = r.sim.agent_export(aid)
        if data is None:
            raise HTTPException(404, "agent not found")
        data["total_descendants"] = r.persistence.descendants_count(aid)
        data["genealogy"] = r.persistence.agent_genealogy(aid)
        headers = {"Content-Disposition": f'attachment; filename="{sid}-agent-{aid}.json"'}
        return Response(content=json.dumps(data, default=str), media_type="application/json",
                        headers=headers)

    @app.get("/api/simulations/{sid}/species/{spid}/export.json")
    def species_export(sid: str, spid: int):
        r = _need(sid)
        data = r.persistence.species_export(spid)
        with r.lock:
            data["language_profile"] = r.sim.symbol_stats.species_profile(spid)
            data["current"] = [r.sim.agent_detail(a.id, full=False)
                               for a in r.sim.agents if a.species_id == spid][:200]
        headers = {"Content-Disposition": f'attachment; filename="{sid}-species-{spid}.json"'}
        return Response(content=json.dumps(data, default=str), media_type="application/json",
                        headers=headers)

    # ------------------------------------------------------------- interactions
    @app.get("/api/simulations/{sid}/interactions")
    def interactions(sid: str, agent_id: int | None = None, type: str | None = None,
                     signal: int | None = None, limit: int = 150):
        r = _need(sid)
        return r.persistence.interactions_query(agent_id=agent_id, itype=type,
                                                signal=signal, limit=limit)

    # ------------------------------------------------------------- language
    @app.get("/api/simulations/{sid}/language")
    def language(sid: str):
        r = _need(sid)
        with r.lock:
            stats_obj = r.sim.symbol_stats
            profiles = {str(sid_): stats_obj.species_profile(sid_) for sid_ in stats_obj.totals}
            most_used = stats_obj.most_used(10)
            diversity = stats_obj.diversity()
        return {"legend": LEGEND, "contexts": CONTEXTS, "diversity": diversity,
                "most_used": most_used, "species_profiles": profiles}

    # ------------------------------------------------------------- analytics
    @app.get("/api/simulations/{sid}/analytics")
    def analytics(sid: str):
        r = _need(sid)
        with r.lock:
            return analytics_mod.compute(r.sim)

    # ------------------------------------------------------------- export
    @app.get("/api/simulations/{sid}/export.json")
    def export_json(sid: str):
        data = manager.export_data(sid)
        if data is None:
            raise HTTPException(404, "not found")
        headers = {"Content-Disposition": f'attachment; filename="{sid}.json"'}
        return Response(content=json.dumps(data, default=str), media_type="application/json",
                        headers=headers)

    @app.get("/api/simulations/{sid}/export.csv")
    def export_csv(sid: str, table: str = "interactions"):
        data = manager.export_data(sid)
        if data is None:
            raise HTTPException(404, "not found")
        rows = data.get(table, [])
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                                 for k, v in row.items()})
        headers = {"Content-Disposition": f'attachment; filename="{sid}-{table}.csv"'}
        return Response(content=buf.getvalue(), media_type="text/csv", headers=headers)

    # ------------------------------------------------------------- time machine
    @app.get("/api/simulations/{sid}/frames")
    def frames(sid: str):
        return {"ticks": _need(sid).persistence.frame_ticks()}

    @app.get("/api/simulations/{sid}/frame")
    def frame(sid: str, tick: int = 0):
        f = _need(sid).persistence.get_frame(tick)
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
