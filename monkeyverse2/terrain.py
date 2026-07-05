"""The planet's crust: a fractal elevation map with oceans and mountains.

Elevation shapes everything downstream — where water and mountains block
movement, which lowlands are fertile, how costly it is to climb a slope. The
crust also erodes slowly and can be reshaped by earthquakes or by the observer.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _upsample(coarse: np.ndarray, H: int, W: int) -> np.ndarray:
    gh, gw = coarse.shape
    ys = np.linspace(0, gh, H, endpoint=False)
    xs = np.linspace(0, gw, W, endpoint=False)
    y0 = np.floor(ys).astype(int) % gh
    x0 = np.floor(xs).astype(int) % gw
    y1 = (y0 + 1) % gh
    x1 = (x0 + 1) % gw
    fy = (ys - np.floor(ys)).reshape(-1, 1)
    fx = (xs - np.floor(xs)).reshape(1, -1)
    top = coarse[np.ix_(y0, x0)] * (1 - fx) + coarse[np.ix_(y0, x1)] * fx
    bot = coarse[np.ix_(y1, x0)] * (1 - fx) + coarse[np.ix_(y1, x1)] * fx
    return top * (1 - fy) + bot * fy


def _fractal_noise(H: int, W: int, octaves: int, rng: np.random.Generator) -> np.ndarray:
    total = np.zeros((H, W), dtype=np.float32)
    amp, norm = 1.0, 0.0
    for o in range(max(1, octaves)):
        gh = max(2, 2 ** (o + 1))
        gw = max(2, int(gh * W / H))
        coarse = rng.standard_normal((gh, gw)).astype(np.float32)
        total += amp * _upsample(coarse, H, W)
        norm += amp
        amp *= 0.55
    n = total / norm
    n = (n - n.min()) / (n.max() - n.min() + 1e-9)
    return n.astype(np.float32)


class Terrain:
    def __init__(self, cfg, rng: np.random.Generator):
        self.cfg = cfg
        self.h, self.w = cfg.height, cfg.width
        self.elevation = _fractal_noise(self.h, self.w, cfg.terrain_octaves, rng)
        # a radial bias so continents tend to sit away from the wrap seams
        self.water_cut = float(np.quantile(self.elevation, cfg.water_level))
        self.mtn_cut = float(np.quantile(self.elevation, cfg.mountain_level))
        self.recompute()

    # ------------------------------------------------------------------ masks
    def recompute(self) -> None:
        e = self.elevation
        self.water = e < self.water_cut
        self.mountain = e > self.mtn_cut
        self.passable = ~self.water & ~self.mountain
        # slope from toroidal gradient
        gy = np.roll(e, -1, 0) - np.roll(e, 1, 0)
        gx = np.roll(e, -1, 1) - np.roll(e, 1, 1)
        self.slope = np.sqrt(gx * gx + gy * gy).astype(np.float32)
        # base fertility: lowlands near the coast are richest
        span = max(1e-3, self.mtn_cut - self.water_cut)
        upland = np.clip((e - self.water_cut) / span, 0, 1)
        fert = (1.0 - upland) ** 1.5
        self.base_fertility = (fert * self.passable).astype(np.float32)

    # ------------------------------------------------------------- dynamics
    def erode(self) -> None:
        e = self.elevation
        blur = (e + np.roll(e, 1, 0) + np.roll(e, -1, 0) +
                np.roll(e, 1, 1) + np.roll(e, -1, 1)) / 5.0
        r = self.cfg.erosion_rate
        self.elevation = (e * (1 - r) + blur * r).astype(np.float32)

    def quake(self, rng: np.random.Generator, cx: int, cy: int, radius: int = 14,
              strength: float = 0.12) -> None:
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        dx = np.minimum(np.abs(xx - cx), self.w - np.abs(xx - cx))
        dy = np.minimum(np.abs(yy - cy), self.h - np.abs(yy - cy))
        mask = np.exp(-(dx * dx + dy * dy) / (2 * radius ** 2))
        ridge = rng.standard_normal((self.h, self.w)).astype(np.float32)
        self.elevation = np.clip(self.elevation + mask * ridge * strength, 0, 1).astype(np.float32)
        self.recompute()

    def raise_land(self, cx: int, cy: int, radius: int, delta: float) -> None:
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        dx = np.minimum(np.abs(xx - cx), self.w - np.abs(xx - cx))
        dy = np.minimum(np.abs(yy - cy), self.h - np.abs(yy - cy))
        mask = np.exp(-(dx * dx + dy * dy) / (2 * (radius or 1) ** 2))
        self.elevation = np.clip(self.elevation + mask * delta, 0, 1).astype(np.float32)
        self.recompute()

    def random_land_cell(self, rng: np.random.Generator) -> tuple[int, int]:
        ys, xs = np.where(self.passable)
        if len(xs) == 0:
            return self.w // 2, self.h // 2
        i = int(rng.integers(0, len(xs)))
        return int(xs[i]), int(ys[i])

    def random_fertile_cell(self, rng: np.random.Generator) -> tuple[int, int]:
        f = (self.base_fertility * self.passable).ravel()
        total = f.sum()
        if total <= 0:
            return self.random_land_cell(rng)
        idx = int(rng.choice(f.size, p=f / total))
        return int(idx % self.w), int(idx // self.w)

    # ------------------------------------------------------------- persistence
    def to_state(self) -> dict[str, Any]:
        return {"elevation": self.elevation, "water_cut": self.water_cut, "mtn_cut": self.mtn_cut}

    def load_state(self, s: dict[str, Any]) -> None:
        self.elevation = np.asarray(s["elevation"], dtype=np.float32)
        self.water_cut = float(s["water_cut"])
        self.mtn_cut = float(s["mtn_cut"])
        self.recompute()
