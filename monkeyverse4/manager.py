"""Runs Simple Island worlds at a real, watchable pace — and lets the observer
change that pace on the fly.

Unlike v3 (which deliberately had *no* speed dial), v4's whole point is close
observation, so the UI can pause or slow things right down as well as fast-forward
to make a long-run study bearable. A "speed" here is a multiplier on the base tick
rate: 0 = paused, 0.5× = half real-time, up to 5×. The base rate is slow on
purpose so decisions are visible one at a time.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from .config import Config
from .logging_store import LoggingStore
from .simulation import Simulation


class SimRunner:
    def __init__(self, sim: Simulation, store: LoggingStore, cfg: Config,
                 status: str = "running", created_at: Optional[float] = None):
        self.sim = sim
        self.store = store
        self.cfg = cfg
        self.status = status                     # "running" | "paused"
        self.created_at = created_at or time.time()
        self.base_tick_rate = float(cfg.base_tick_rate)
        self.speed = float(cfg.realtime_speed)   # multiplier; 0 => paused
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.real_tick_rate = 0.0

    # ------------------------------------------------------------------ control
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"mv4-{self.sim.id}", daemon=True)
        self._thread.start()

    def set_speed(self, speed: float):
        with self.lock:
            self.speed = max(0.0, float(speed))
            self.status = "paused" if self.speed <= 0.0 else "running"

    def pause(self):
        self.set_speed(0.0)

    def resume(self, speed: float = 1.0):
        self.set_speed(speed if speed > 0 else 1.0)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.store.flush()

    # ------------------------------------------------------------------ loop
    def _run(self):
        last, cnt = time.perf_counter(), 0
        while not self._stop.is_set():
            with self.lock:
                spd = self.speed
            if spd <= 0.0:
                time.sleep(0.05)
                last = time.perf_counter(); cnt = 0
                continue
            t0 = time.perf_counter()
            with self.lock:
                self.sim.step()
            cnt += 1
            now = time.perf_counter()
            if now - last >= 1.0:
                self.real_tick_rate = cnt / (now - last); cnt = 0; last = now
            target_dt = 1.0 / max(1e-3, self.base_tick_rate * spd)
            delay = target_dt - (time.perf_counter() - t0)
            if delay > 0:
                time.sleep(delay)

    # ------------------------------------------------------------------ views
    def info(self) -> dict[str, Any]:
        return {
            "id": self.sim.id, "name": self.cfg.name, "status": self.status,
            "speed": self.speed, "tick": self.sim.tick,
            "population": len(self.sim.agents),
            "base_tick_rate": self.base_tick_rate,
            "real_tick_rate": round(self.real_tick_rate, 2),
            "created_at": self.created_at,
        }


class Manager:
    """Owns every running world and its database, so the server stays thin."""

    def __init__(self, data_dir: str = "data/mv4"):
        self.data_dir = data_dir
        self.runners: dict[str, SimRunner] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        return f"isla{self._counter:03d}-{int(time.time()) % 100000}"

    def create(self, cfg: Config) -> SimRunner:
        with self._lock:
            sim_id = self._new_id()
            import os
            db_path = os.path.join(self.data_dir, f"{sim_id}.db")
            store = LoggingStore(db_path)
            store.set_meta("config", cfg.to_dict())
            store.set_meta("seed", cfg.resolved_seed())
            sim = Simulation(sim_id, cfg, store=store)
            store.set_meta("seed", sim.seed)
            runner = SimRunner(sim, store, cfg)
            self.runners[sim_id] = runner
            runner.start()
            return runner

    def get(self, sim_id: str) -> Optional[SimRunner]:
        return self.runners.get(sim_id)

    def list(self) -> list[dict[str, Any]]:
        return [r.info() for r in self.runners.values()]

    def delete(self, sim_id: str) -> bool:
        with self._lock:
            r = self.runners.pop(sim_id, None)
        if r:
            r.stop()
            r.store.close()
            return True
        return False

    def reset(self, sim_id: str) -> Optional[SimRunner]:
        """Restart a world from tick 0 with the same config (fresh island)."""
        with self._lock:
            old = self.runners.get(sim_id)
            if not old:
                return None
            old.stop()
            cfg = old.cfg
            import os
            old.store.close()
            db_path = os.path.join(self.data_dir, f"{sim_id}.db")
            try:
                os.remove(db_path)
                for ext in ("-wal", "-shm"):
                    if os.path.exists(db_path + ext):
                        os.remove(db_path + ext)
            except OSError:
                pass
            store = LoggingStore(db_path)
            store.set_meta("config", cfg.to_dict())
            sim = Simulation(sim_id, cfg, store=store)
            store.set_meta("seed", sim.seed)
            runner = SimRunner(sim, store, cfg)
            self.runners[sim_id] = runner
            runner.start()
            return runner

    def stop_all(self):
        for r in list(self.runners.values()):
            r.stop()
            r.store.close()
