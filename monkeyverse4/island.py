"""The island: a small square grid with a circular/oval patch of walkable land
surrounded by water, and a slowly-regrowing vegetation layer on the land.

Deliberately trivial — no elevation, biomes, disasters or predators. Water is a
soft boundary: agents can't stand on it (they bounce back), it doesn't kill.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class Island:
    def __init__(self, cfg, rng: np.random.Generator):
        self.cfg = cfg
        self.rng = rng
        self.n = cfg.map_size
        cx = cy = (self.n - 1) / 2.0
        yy, xx = np.mgrid[0:self.n, 0:self.n].astype(np.float32)
        # a slightly oval island so it doesn't look like a perfect disc
        rad = (self.n / 2.0) * cfg.island_ratio
        dist = np.sqrt(((xx - cx) / 1.05) ** 2 + ((yy - cy) / 0.95) ** 2)
        self.land = (dist < rad)                      # walkable mask
        self.water = ~self.land
        # fertility: richer toward the centre, tapering at the shore
        fert = np.clip(1.0 - dist / rad, 0.0, 1.0) ** 0.6
        self.fertility = (fert * self.land).astype(np.float32)

        # initial vegetation: a fraction of land cells start vegetated
        seed_mask = (rng.random((self.n, self.n)) < cfg.vegetation_density) & self.land
        self.veg = (seed_mask * self.fertility * cfg.veg_capacity).astype(np.float32)

    # ------------------------------------------------------------------ step
    def regrow(self) -> None:
        cap = self.fertility * self.cfg.veg_capacity
        grow = self.cfg.vegetation_regrowth_rate * cap * (1.0 - self.veg / np.maximum(cap, 1e-4))
        self.veg = np.clip(self.veg + grow * self.land, 0.0, self.cfg.veg_capacity)

    def is_land(self, x: float, y: float) -> bool:
        ix, iy = int(round(x)), int(round(y))
        if 0 <= ix < self.n and 0 <= iy < self.n:
            return bool(self.land[iy, ix])
        return False

    def veg_at(self, x: float, y: float) -> float:
        ix, iy = int(round(x)), int(round(y))
        if 0 <= ix < self.n and 0 <= iy < self.n:
            return float(self.veg[iy, ix])
        return 0.0

    def eat_at(self, x: float, y: float, amount: float) -> float:
        ix, iy = int(round(x)), int(round(y))
        if 0 <= ix < self.n and 0 <= iy < self.n:
            got = min(self.veg[iy, ix], amount)
            self.veg[iy, ix] -= got
            return float(got)
        return 0.0

    def graze(self, x: float, y: float, amount: float, radius: int = 2) -> float:
        """Eat from the richest cell within `radius` of the agent — it can reach
        for nearby food. Keeps slow foragers from starving on top of abundant
        vegetation without hardcoding any movement toward food."""
        ix, iy = int(round(x)), int(round(y))
        best_v, bx, by = 0.0, ix, iy
        for gy in range(iy - radius, iy + radius + 1):
            for gx in range(ix - radius, ix + radius + 1):
                if 0 <= gx < self.n and 0 <= gy < self.n and self.veg[gy, gx] > best_v:
                    best_v, bx, by = self.veg[gy, gx], gx, gy
        if best_v <= 0.0:
            return 0.0
        got = min(best_v, amount)
        self.veg[by, bx] -= got
        return float(got)

    def random_land_cell(self) -> tuple[float, float]:
        ys, xs = np.where(self.land)
        i = int(self.rng.integers(0, len(xs)))
        return float(xs[i]), float(ys[i])

    def nearest_food(self, x: float, y: float, radius: int = 10):
        """Return (dx, dy, dist) to the nearest vegetated cell within radius, or
        None. Small map => a bounded local scan is cheap."""
        ix, iy = int(round(x)), int(round(y))
        best = None
        best_d2 = None
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                gx, gy = ix + dx, iy + dy
                if 0 <= gx < self.n and 0 <= gy < self.n and self.veg[gy, gx] > 0.15:
                    d2 = dx * dx + dy * dy
                    if best_d2 is None or d2 < best_d2:
                        best_d2, best = d2, (dx, dy)
        if best is None:
            return None
        d = max(1.0, best_d2 ** 0.5)
        return best[0] / d, best[1] / d, d

    def veg_total(self) -> float:
        return float(self.veg.sum())

    # ------------------------------------------------------------------ render
    def render(self) -> dict[str, Any]:
        return {
            "size": self.n,
            "land": self.land.astype(int).tolist(),
            "veg": self.veg.round(3).tolist(),
        }

    # ------------------------------------------------------------------ state
    def to_state(self) -> dict[str, Any]:
        return {"veg": self.veg}

    def load_state(self, s: dict[str, Any]) -> None:
        self.veg = np.asarray(s["veg"], dtype=np.float32)
