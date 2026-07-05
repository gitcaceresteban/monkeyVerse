"""Runs many worlds at once.

Each simulation lives in its own thread so several can run in parallel (for
sensitivity analysis: same rules, different initial parameters). The manager
handles creation, live controls (pause / speed / interventions), persistence,
periodic snapshots and — crucially for a 24/7 box — automatic resume of every
running world when the process restarts.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Optional

from .config import SimConfig
from .persistence import Persistence
from .simulation import Simulation


class SimRunner:
    def __init__(self, sim: Simulation, persistence: Persistence, cfg: SimConfig,
                 name: str, status: str = "running", created_at: Optional[float] = None):
        self.sim = sim
        self.persistence = persistence
        self.cfg = cfg
        self.name = name
        self.status = status                 # running | paused | stopped
        self.created_at = created_at or time.time()
        self.target_sps = float(cfg.target_sps)
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.real_sps = 0.0

    # ----------------------------------------------------------------- thread
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"sim-{self.sim.id}", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        last_report = time.perf_counter()
        steps_since = 0
        while not self._stop.is_set():
            if self.status != "running":
                time.sleep(0.05)
                last_report = time.perf_counter()
                continue
            t0 = time.perf_counter()
            with self.lock:
                self.sim.step()
            tick = self.sim.tick

            if tick % self.cfg.snapshot_every == 0:
                with self.lock:
                    snap = self.sim.to_snapshot()
                self.persistence.save_snapshot(tick, snap)
            elif tick % max(1, self.cfg.stats_every) == 0:
                self.persistence.flush()

            # measured speed
            steps_since += 1
            now = time.perf_counter()
            if now - last_report >= 1.0:
                self.real_sps = steps_since / (now - last_report)
                steps_since = 0
                last_report = now

            # throttle to target
            target = max(0.5, self.target_sps)
            elapsed = time.perf_counter() - t0
            delay = (1.0 / target) - elapsed
            if delay > 0:
                time.sleep(delay)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    # ----------------------------------------------------------------- control
    def pause(self) -> None:
        self.status = "paused"

    def resume(self) -> None:
        self.status = "running"

    def set_speed(self, sps: float) -> None:
        self.target_sps = max(0.5, float(sps))

    def render_state(self) -> dict[str, Any]:
        with self.lock:
            state = self.sim.render_state()
        state["runner"] = {
            "status": self.status, "target_sps": round(self.target_sps, 1),
            "real_sps": round(self.real_sps, 1), "name": self.name,
            "births_total": self.sim.births_total, "deaths_total": self.sim.deaths_total,
            "seed": self.sim.seed,
        }
        return state

    def snapshot_now(self) -> None:
        with self.lock:
            snap = self.sim.to_snapshot()
        self.persistence.save_snapshot(self.sim.tick, snap)


class Manager:
    def __init__(self, base_dir: str = "data"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self.registry_path = os.path.join(base_dir, "registry.json")
        self.runners: dict[str, SimRunner] = {}
        self._lock = threading.Lock()
        self._load_registry_and_resume()

    # ------------------------------------------------------------- registry io
    def _read_registry(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.registry_path):
            return []
        try:
            with open(self.registry_path) as f:
                return json.load(f).get("sims", [])
        except Exception:
            return []

    def _write_registry(self) -> None:
        sims = []
        for sid, r in self.runners.items():
            sims.append({
                "id": sid, "name": r.name, "status": r.status,
                "created_at": r.created_at, "config": r.cfg.to_dict(),
                "seed": r.sim.seed,
            })
        tmp = self.registry_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"sims": sims}, f, indent=2)
        os.replace(tmp, self.registry_path)

    def _db_path(self, sim_id: str) -> str:
        return os.path.join(self.base_dir, f"{sim_id}.db")

    def _load_registry_and_resume(self) -> None:
        for entry in self._read_registry():
            try:
                self._resume_entry(entry)
            except Exception as e:  # pragma: no cover
                print(f"[manager] could not resume {entry.get('id')}: {e}")

    def _resume_entry(self, entry: dict[str, Any]) -> None:
        sid = entry["id"]
        cfg = SimConfig.from_dict(entry["config"])
        persistence = Persistence(self._db_path(sid))
        snap = persistence.load_latest_snapshot()
        sim = Simulation(sid, cfg, persistence, populate=(snap is None))
        if snap is not None:
            sim.load_snapshot(snap)
        status = entry.get("status", "running")
        if status == "stopped":
            status = "paused"
        runner = SimRunner(sim, persistence, cfg, entry.get("name", "world"),
                           status=status, created_at=entry.get("created_at"))
        self.runners[sid] = runner
        runner.start()

    # ------------------------------------------------------------- lifecycle
    def create(self, cfg: SimConfig) -> str:
        with self._lock:
            sid = uuid.uuid4().hex[:10]
            persistence = Persistence(self._db_path(sid))
            sim = Simulation(sid, cfg, persistence, populate=True)
            runner = SimRunner(sim, persistence, cfg, cfg.name, status="running")
            self.runners[sid] = runner
            self._write_registry()
            runner.start()
            return sid

    def delete(self, sim_id: str) -> bool:
        with self._lock:
            r = self.runners.pop(sim_id, None)
            if not r:
                return False
            r.stop()
            r.persistence.close()
            self._write_registry()
        for suffix in ("", "-wal", "-shm"):
            p = self._db_path(sim_id) + suffix
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        return True

    def get(self, sim_id: str) -> Optional[SimRunner]:
        return self.runners.get(sim_id)

    def list(self) -> list[dict[str, Any]]:
        out = []
        for sid, r in self.runners.items():
            st = r.sim.stats_row()
            out.append({
                "id": sid, "name": r.name, "status": r.status,
                "tick": r.sim.tick, "population": st["population"],
                "births_total": r.sim.births_total, "deaths_total": r.sim.deaths_total,
                "max_generation": st["max_generation"], "seed": r.sim.seed,
                "target_sps": round(r.target_sps, 1), "real_sps": round(r.real_sps, 1),
                "created_at": r.created_at, "event": r.sim.world.event_name,
                "config": r.cfg.to_dict(),
            })
        out.sort(key=lambda d: d["created_at"])
        return out

    def control(self, sim_id: str, action: str, value: Any = None) -> bool:
        r = self.get(sim_id)
        if not r:
            return False
        if action == "pause":
            r.pause()
        elif action == "resume":
            r.resume()
        elif action == "speed":
            r.set_speed(float(value))
        elif action == "snapshot":
            r.snapshot_now()
        else:
            return False
        self._write_registry()
        return True

    def intervene(self, sim_id: str, kind: str, params: dict[str, Any]) -> bool:
        r = self.get(sim_id)
        if not r:
            return False
        with r.lock:
            world = r.sim.world
            if kind == "food":
                world.apply_food(int(params.get("x", world.w // 2)),
                                 int(params.get("y", world.h // 2)),
                                 int(params.get("radius", 6)),
                                 float(params.get("amount", 1.0)))
            elif kind == "drought":
                world.trigger_event("sequía")
            elif kind == "bloom":
                world.trigger_event("florecimiento")
            elif kind == "calm":
                world.trigger_event("estable")
            else:
                return False
        if r.persistence:
            r.persistence.log_event(r.sim.tick, "intervention", {"kind": kind, **params})
        return True

    def shutdown(self) -> None:
        for r in self.runners.values():
            try:
                r.snapshot_now()
            except Exception:
                pass
            r.stop()
            r.persistence.close()
        self._write_registry()
