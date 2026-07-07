"""Runs many planets at once, keeps them alive 24/7, and lets the observer fork
a running world into a parallel universe to compare divergent timelines.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Optional

from .config import SimConfig
from .language import LEGEND
from .persistence import Persistence
from .simulation import Simulation


class SimRunner:
    """Runs one world at a fixed, real-time pace (cfg.tick_rate ticks/second).

    There is deliberately no "speed" dial: what plays on screen is the actual
    rate at which things happen, so interactions between individuals stay
    genuinely watchable instead of being fast-forwarded into a blur.
    """

    def __init__(self, sim, persistence, cfg, name, status="running", created_at=None):
        self.sim = sim
        self.persistence = persistence
        self.cfg = cfg
        self.name = name
        self.status = status
        self.created_at = created_at or time.time()
        self.tick_rate = float(cfg.tick_rate)
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.real_tick_rate = 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"sim2-{self.sim.id}", daemon=True)
        self._thread.start()

    def _run(self):
        last, cnt = time.perf_counter(), 0
        while not self._stop.is_set():
            if self.status != "running":
                time.sleep(0.05); last = time.perf_counter(); continue
            t0 = time.perf_counter()
            with self.lock:
                self.sim.step()
            tick = self.sim.tick
            if tick % self.cfg.snapshot_every == 0:
                with self.lock:
                    snap = self.sim.to_snapshot()
                self.persistence.save_snapshot(tick, snap)
            if tick % self.cfg.frame_every == 0:
                with self.lock:
                    fr = self.sim.frame()
                self.persistence.save_frame(tick, fr)
            elif tick % max(1, self.cfg.stats_every) == 0:
                self.persistence.flush()
            cnt += 1
            now = time.perf_counter()
            if now - last >= 1.0:
                self.real_tick_rate = cnt / (now - last); cnt = 0; last = now
            delay = 1.0 / max(0.5, self.tick_rate) - (time.perf_counter() - t0)
            if delay > 0:
                time.sleep(delay)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def render_state(self):
        with self.lock:
            st = self.sim.render_state()
        st["runner"] = {"status": self.status, "tick_rate": round(self.tick_rate, 1),
                        "real_tick_rate": round(self.real_tick_rate, 1), "name": self.name,
                        "births_total": self.sim.births_total, "deaths_total": self.sim.deaths_total,
                        "seed": self.sim.seed}
        return st

    def snapshot_now(self):
        with self.lock:
            snap = self.sim.to_snapshot()
        self.persistence.save_snapshot(self.sim.tick, snap)


class Manager:
    def __init__(self, base_dir="data2"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self.registry_path = os.path.join(base_dir, "registry.json")
        self.runners: dict[str, SimRunner] = {}
        self._lock = threading.Lock()
        self._resume_all()

    # ------------------------------------------------------------- registry
    def _read_registry(self):
        if not os.path.exists(self.registry_path):
            return []
        try:
            with open(self.registry_path) as f:
                return json.load(f).get("sims", [])
        except Exception:
            return []

    def _write_registry(self):
        sims = [{"id": sid, "name": r.name, "status": r.status, "created_at": r.created_at,
                 "config": r.cfg.to_dict(), "seed": r.sim.seed} for sid, r in self.runners.items()]
        tmp = self.registry_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"sims": sims}, f, indent=2)
        os.replace(tmp, self.registry_path)

    def _db(self, sid):
        return os.path.join(self.base_dir, f"{sid}.db")

    def _resume_all(self):
        for e in self._read_registry():
            try:
                self._resume(e)
            except Exception as ex:  # pragma: no cover
                print(f"[manager2] resume {e.get('id')} failed: {ex}")

    def _resume(self, e):
        sid = e["id"]
        cfg = SimConfig.from_dict(e["config"])
        p = Persistence(self._db(sid))
        snap = p.load_latest_snapshot()
        sim = Simulation(sid, cfg, p, populate=(snap is None))
        if snap is not None:
            sim.load_snapshot(snap)
        status = e.get("status", "running")
        if status == "stopped":
            status = "paused"
        r = SimRunner(sim, p, cfg, e.get("name", "planeta"), status, e.get("created_at"))
        self.runners[sid] = r
        r.start()

    # ------------------------------------------------------------- lifecycle
    def create(self, cfg):
        with self._lock:
            sid = uuid.uuid4().hex[:10]
            p = Persistence(self._db(sid))
            sim = Simulation(sid, cfg, p, populate=True)
            r = SimRunner(sim, p, cfg, cfg.name, "running")
            self.runners[sid] = r
            self._write_registry()
            r.start()
            return sid

    def fork(self, sim_id, new_name=None):
        """Clone a running world into a fresh parallel universe."""
        src = self.get(sim_id)
        if not src:
            return None
        with self._lock:
            with src.lock:
                snap = src.sim.to_snapshot()
            nid = uuid.uuid4().hex[:10]
            cfg = SimConfig.from_dict(src.cfg.to_dict())
            cfg.name = new_name or (src.name + "-bifurcación")
            p = Persistence(self._db(nid))
            sim = Simulation(nid, cfg, p, populate=False)
            sim.load_snapshot(snap)
            sim.id = nid
            r = SimRunner(sim, p, cfg, cfg.name, "running")
            self.runners[nid] = r
            self._write_registry()
            r.start()
            return nid

    def delete(self, sim_id):
        with self._lock:
            r = self.runners.pop(sim_id, None)
            if not r:
                return False
            r.stop(); r.persistence.close()
            self._write_registry()
        for suf in ("", "-wal", "-shm"):
            try:
                p = self._db(sim_id) + suf
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        return True

    def get(self, sim_id):
        return self.runners.get(sim_id)

    def list(self):
        out = []
        for sid, r in self.runners.items():
            st = r.sim.stats_row()
            out.append({"id": sid, "name": r.name, "status": r.status, "tick": r.sim.tick,
                        "population": st["population"], "species": st["species"],
                        "births_total": r.sim.births_total, "deaths_total": r.sim.deaths_total,
                        "max_generation": st["max_generation"], "seed": r.sim.seed,
                        "tick_rate": round(r.tick_rate, 1), "real_tick_rate": round(r.real_tick_rate, 1),
                        "created_at": r.created_at, "weather": st["weather"],
                        "cognition_mode": r.cfg.cognition_mode,
                        "config": r.cfg.to_dict()})
        out.sort(key=lambda d: d["created_at"])
        return out

    def control(self, sim_id, action, value=None):
        r = self.get(sim_id)
        if not r:
            return False
        if action == "pause":
            r.status = "paused"
        elif action == "resume":
            r.status = "running"
        elif action == "snapshot":
            r.snapshot_now()
        else:
            return False
        self._write_registry()
        return True

    def intervene(self, sim_id, kind, params):
        r = self.get(sim_id)
        if not r:
            return False
        p = params or {}
        with r.lock:
            w = r.sim.world
            if kind == "food":
                w.apply_food(int(p.get("x", w.w // 2)), int(p.get("y", w.h // 2)),
                             int(p.get("radius", 7)), float(p.get("amount", 1.5)))
            elif kind == "rain":
                w.apply_rain(0.5)
            elif kind == "drought":
                w.rain_state = 0.12
            elif kind == "fire":
                w.ignite(int(p.get("x", w.w // 2)), int(p.get("y", w.h // 2)))
            elif kind == "flood":
                w.start_flood()
            elif kind == "quake":
                w.terrain.quake(r.sim.rng, int(p.get("x", w.w // 2)), int(p.get("y", w.h // 2)))
            elif kind == "raise":
                w.terrain.raise_land(int(p.get("x", w.w // 2)), int(p.get("y", w.h // 2)),
                                     int(p.get("radius", 10)), float(p.get("delta", 0.25)))
            elif kind == "sink":
                w.terrain.raise_land(int(p.get("x", w.w // 2)), int(p.get("y", w.h // 2)),
                                     int(p.get("radius", 10)), -float(p.get("delta", 0.25)))
            elif kind == "meteor":
                self._meteor(r.sim, int(p.get("x", w.w // 2)), int(p.get("y", w.h // 2)),
                             int(p.get("radius", 12)))
            elif kind == "spawn_species":
                self._spawn_species(r.sim, int(p.get("count", 12)))
            else:
                return False
        if r.persistence:
            r.persistence.log_event(r.sim.tick, "intervención", {"kind": kind, **p})
            r.persistence.log_milestone({"tick": r.sim.tick, "kind": "intervención",
                                         "label": f"El observador provocó: {kind}", "data": {"kind": kind}})
        return True

    def _meteor(self, sim, cx, cy, radius):
        import numpy as np
        w = sim.world
        survivors = []
        for a in sim.agents:
            dx = min(abs(a.x - cx), w.w - abs(a.x - cx))
            dy = min(abs(a.y - cy), w.h - abs(a.y - cy))
            if dx * dx + dy * dy <= radius * radius:
                w.meat[a.y, a.x] = min(4.0, w.meat[a.y, a.x] + 0.5)
                sim.deaths_total += 1
                if sim.persistence:
                    sim.persistence.log_death(a.id, sim.tick, a.age, a.generation, a.x, a.y, "meteoro")
            else:
                survivors.append(a)
        sim.agents = survivors
        w.terrain.quake(sim.rng, cx, cy, radius=radius, strength=0.2)
        w.veg[max(0, cy - radius):cy + radius, max(0, cx - radius):cx + radius] *= 0.2

    def _spawn_species(self, sim, count):
        from .agent import Agent
        g = sim._new_genome()
        # a carnivore-leaning omnivore: viable via scavenging, can specialise later
        g.genes["diet"] = float(sim.rng.uniform(0.55, 0.85))
        g.genes["meat_eff"] = float(sim.rng.uniform(1.1, 1.5))
        g.genes["size"] = float(sim.rng.uniform(1.1, 1.5))
        g.genes["agg_bias"] = float(sim.rng.uniform(0.2, 0.8))
        sid = sim.species.found(g, sim.tick)
        for _ in range(count):
            x, y = sim.world.terrain.random_fertile_cell(sim.rng)
            child = g.child(sim.rng, sim.cfg.weight_mutation_scale)
            ag = Agent(sim.next_id, child, x, y, sim.cfg.initial_energy, 0, 0, sim.tick,
                       sim.cfg, species_id=sid)
            sim.next_id += 1
            sim.agents.append(ag)
            sim.births_total += 1
            if sim.persistence:
                sim.persistence.log_birth(sim._birth_row(ag))

    def export_data(self, sim_id):
        r = self.get(sim_id)
        if not r:
            return None
        data = r.persistence.export_all()
        with r.lock:
            data["species_living"] = r.sim.species.living()
            data["symbol_legend"] = {str(k): v for k, v in LEGEND.items()}
            data["config"] = r.cfg.to_dict()
            data["tick"] = r.sim.tick
        return data

    def shutdown(self):
        for r in self.runners.values():
            try:
                r.snapshot_now()
            except Exception:
                pass
            r.stop(); r.persistence.close()
        self._write_registry()
