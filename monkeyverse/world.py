"""The physical environment: food that grows, seasons, climate events, and a
decaying field of signals. The world is dynamic on its own, independent of the
agents — it keeps changing so that populations must keep adapting.

The grid is toroidal (wraps around) so there are no artificial edges.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .config import SimConfig


class World:
    def __init__(self, cfg: SimConfig, rng: np.random.Generator):
        self.cfg = cfg
        self.w = cfg.width
        self.h = cfg.height
        self.rng = rng

        # Static fertility map: a few Gaussian patches => heterogeneous terrain.
        self.capacity = self._build_capacity(rng)
        # Food currently available in each cell.
        self.food = (self.capacity * rng.uniform(0.2, 0.6, size=self.capacity.shape)).astype(np.float32)

        # Signalling substrate: (H, W, channels). Empty and meaningless at birth.
        self.signal = np.zeros((self.h, self.w, max(0, cfg.signal_channels)), dtype=np.float32)

        # Transient climate multiplier from random events (drought<1, bloom>1).
        self.event_factor = 1.0
        self.event_ttl = 0
        self.event_name = "estable"

    # ------------------------------------------------------------------ setup
    def _build_capacity(self, rng: np.random.Generator) -> np.ndarray:
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        cap = np.full((self.h, self.w), max(0.0, self.cfg.resource_floor), dtype=np.float32)
        for _ in range(max(1, self.cfg.resource_patches)):
            cx = rng.uniform(0, self.w)
            cy = rng.uniform(0, self.h)
            sigma = rng.uniform(min(self.w, self.h) * 0.06, min(self.w, self.h) * 0.18)
            # toroidal distance
            dx = np.minimum(np.abs(xx - cx), self.w - np.abs(xx - cx))
            dy = np.minimum(np.abs(yy - cy), self.h - np.abs(yy - cy))
            cap += np.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma))
        floor = max(0.0, self.cfg.resource_floor)
        peak = cap.max()
        if peak > floor:
            cap = floor + (cap - floor) / (peak - floor) * (self.cfg.resource_capacity - floor)
        return cap.astype(np.float32)

    # ------------------------------------------------------------------ step
    def season_factor(self, tick: int) -> float:
        if self.cfg.season_length <= 0:
            return 1.0
        phase = 2 * np.pi * (tick % self.cfg.season_length) / self.cfg.season_length
        return float(1.0 + self.cfg.season_amplitude * np.sin(phase))

    def maybe_event(self, tick: int) -> str | None:
        if self.event_ttl > 0:
            self.event_ttl -= 1
            if self.event_ttl == 0:
                self.event_factor = 1.0
                self.event_name = "estable"
            return None
        if self.rng.random() < self.cfg.event_probability:
            if self.rng.random() < 0.5:
                self.event_factor = self.rng.uniform(0.15, 0.5)
                self.event_name = "sequía"
            else:
                self.event_factor = self.rng.uniform(1.6, 2.6)
                self.event_name = "florecimiento"
            self.event_ttl = int(self.rng.uniform(300, 1200))
            return self.event_name
        return None

    def update(self, tick: int) -> str | None:
        event = self.maybe_event(tick)
        eff_cap = self.capacity * self.season_factor(tick) * self.event_factor
        eff_cap = np.maximum(eff_cap, 1e-4)
        # logistic regrowth toward the (currently effective) capacity
        self.food += self.cfg.resource_regen * eff_cap * (1.0 - self.food / eff_cap)
        np.clip(self.food, 0.0, self.capacity * 2.5, out=self.food)
        # signals fade
        if self.signal.shape[2] > 0:
            self.signal *= self.cfg.signal_decay
        return event

    # ------------------------------------------------------------ interventions
    def apply_food(self, cx: int, cy: int, radius: int, amount: float) -> None:
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        dx = np.minimum(np.abs(xx - cx), self.w - np.abs(xx - cx))
        dy = np.minimum(np.abs(yy - cy), self.h - np.abs(yy - cy))
        mask = np.exp(-(dx * dx + dy * dy) / (2 * (radius or 1) ** 2))
        self.food = np.clip(self.food + mask.astype(np.float32) * amount, 0.0, self.capacity * 3.0)

    def trigger_event(self, name: str) -> None:
        if name == "sequía":
            self.event_factor = 0.2
        elif name == "florecimiento":
            self.event_factor = 2.4
        else:
            self.event_factor = 1.0
            self.event_name = "estable"
            self.event_ttl = 0
            return
        self.event_name = name
        self.event_ttl = int(self.rng.uniform(600, 1500))

    # --------------------------------------------------------------- rendering
    def food_downsampled(self, out_w: int, out_h: int) -> list[list[float]]:
        ys = np.linspace(0, self.h - 1, out_h).astype(int)
        xs = np.linspace(0, self.w - 1, out_w).astype(int)
        sub = self.food[np.ix_(ys, xs)]
        denom = float(self.capacity.max()) or 1.0
        return (np.clip(sub / denom, 0, 1)).round(3).tolist()

    # --------------------------------------------------------------- persistence
    def to_state(self) -> dict[str, Any]:
        return {
            "capacity": self.capacity,
            "food": self.food,
            "signal": self.signal,
            "event_factor": self.event_factor,
            "event_ttl": self.event_ttl,
            "event_name": self.event_name,
        }

    def load_state(self, s: dict[str, Any]) -> None:
        self.capacity = np.asarray(s["capacity"], dtype=np.float32)
        self.food = np.asarray(s["food"], dtype=np.float32)
        self.signal = np.asarray(s["signal"], dtype=np.float32)
        self.event_factor = float(s.get("event_factor", 1.0))
        self.event_ttl = int(s.get("event_ttl", 0))
        self.event_name = s.get("event_name", "estable")
