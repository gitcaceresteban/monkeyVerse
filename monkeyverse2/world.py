"""A living planet: vegetation, moisture, weather, disasters, signalling fields
and carrion. Nothing here is stable — every layer keeps moving so populations can
never stop adapting.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .terrain import Terrain


class World:
    def __init__(self, cfg, rng: np.random.Generator):
        self.cfg = cfg
        self.rng = rng
        self.terrain = Terrain(cfg, rng)
        self.h, self.w = cfg.height, cfg.width

        # smoothed distance-to-water, gives coasts their humidity
        self.water_prox = self._blur(self.terrain.water.astype(np.float32), 4)

        cap = self._effective_capacity(1.0, 1.0)
        self.veg = (cap * rng.uniform(0.2, 0.6, cap.shape)).astype(np.float32)

        self.pher = np.zeros((self.h, self.w, max(0, cfg.pheromone_channels)), dtype=np.float32)
        self.sound = np.zeros((self.h, self.w, max(0, cfg.sound_channels)), dtype=np.float32)
        self.meat = np.zeros((self.h, self.w), dtype=np.float32)
        self.materials = (rng.random((self.h, self.w)).astype(np.float32) < 0.02).astype(np.float32)
        self.materials *= (self.terrain.elevation > self.terrain.mtn_cut * 0.75)  # ore near highlands

        # hazards
        self.fire = np.zeros((self.h, self.w), dtype=np.float32)
        self.flood = np.zeros((self.h, self.w), dtype=np.float32)
        self.flood_ttl = 0

        # climate
        self.climate = 0.0          # slow permanent drift
        self.rain_state = cfg.rain_base
        self.weather_name = "templado"

    # ------------------------------------------------------------------ helpers
    def _blur(self, a: np.ndarray, iters: int = 1) -> np.ndarray:
        for _ in range(iters):
            a = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0) +
                 np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
        return a.astype(np.float32)

    def light(self, tick: int) -> float:
        if self.cfg.day_length <= 0:
            return 1.0
        phase = 2 * np.pi * (tick % self.cfg.day_length) / self.cfg.day_length
        return float(0.35 + 0.65 * (0.5 + 0.5 * np.sin(phase - np.pi / 2)))

    def season(self, tick: int) -> float:
        if self.cfg.season_length <= 0:
            return 1.0
        phase = 2 * np.pi * (tick % self.cfg.season_length) / self.cfg.season_length
        return float(1.0 + self.cfg.season_amplitude * np.sin(phase))

    def moisture(self) -> np.ndarray:
        m = self.rain_state + 0.5 * self.water_prox - 0.25 * self.climate
        return np.clip(m, 0.0, 1.5).astype(np.float32)

    def _effective_capacity(self, season: float, moist_scale: float) -> np.ndarray:
        base = self.terrain.base_fertility * self.cfg.veg_capacity
        return np.maximum(base * season * moist_scale, 1e-4).astype(np.float32)

    # ------------------------------------------------------------------ step
    def update(self, tick: int) -> list[str]:
        events: list[str] = []
        c = self.cfg

        # slow climate drift (very long-term change)
        self.climate += c.climate_drift * (1.0 if (tick // 50000) % 2 == 0 else -1.0)

        # weather random walk (rain <-> drought)
        self.rain_state += self.rng.normal(0, 0.02 * c.weather_volatility)
        self.rain_state = float(np.clip(self.rain_state, 0.05, 1.3))
        if self.rain_state > 0.95:
            self.weather_name = "lluvia"
        elif self.rain_state < 0.25:
            self.weather_name = "sequía"
        else:
            self.weather_name = "templado"

        season = self.season(tick)
        moist = self.moisture()
        moist_scale = 0.4 + 0.9 * np.clip(moist, 0, 1.3)
        eff_cap = self._effective_capacity(season, moist_scale)

        # vegetation logistic growth (no growth where it is burning)
        grow = c.veg_regen * eff_cap * (1.0 - self.veg / eff_cap)
        self.veg += grow * (self.fire <= 0.01)
        np.clip(self.veg, 0.0, self.cfg.veg_capacity * 2.0, out=self.veg)

        # fire spreads to vegetated neighbours, consumes fuel, then dies
        if self.fire.max() > 0.01:
            spread = self._blur((self.fire > 0.05).astype(np.float32), 1) > 0.12
            ignite = spread & (self.veg > 0.35) & (self.rng.random((self.h, self.w)) < 0.25)
            self.fire = np.maximum(self.fire * 0.9, ignite.astype(np.float32))
            burning = self.fire > 0.05
            self.veg[burning] *= 0.6
            self.fire[self.veg < 0.05] = 0.0
            if not burning.any():
                self.fire[:] = 0.0

        # signalling fields decay
        if self.pher.shape[2]:
            self.pher *= c.pheromone_decay
        if self.sound.shape[2]:
            self.sound *= 0.55   # calls are transient
        # carrion rots
        self.meat *= (1.0 - c.corpse_decay)

        # erosion (very slow terrain smoothing)
        if tick % 200 == 0:
            self.terrain.erode()

        # flood recedes
        if self.flood_ttl > 0:
            self.flood_ttl -= 1
            if self.flood_ttl == 0:
                self.flood[:] = 0.0

        # spontaneous disasters
        if self.rng.random() < c.p_fire and self.veg.max() > 0.4:
            self.ignite(); events.append("incendio")
        if self.rng.random() < c.p_flood:
            self.start_flood(); events.append("inundación")
        if self.rng.random() < c.p_quake:
            x, y = self.terrain.random_land_cell(self.rng)
            self.terrain.quake(self.rng, x, y); events.append("terremoto")
        return events

    # ------------------------------------------------------------------ hazards
    def ignite(self, cx: Optional[int] = None, cy: Optional[int] = None) -> None:
        if cx is None:
            ys, xs = np.where(self.veg > 0.4)
            if len(xs) == 0:
                return
            i = int(self.rng.integers(0, len(xs)))
            cx, cy = int(xs[i]), int(ys[i])
        self.fire[cy % self.h, cx % self.w] = 1.0

    def start_flood(self) -> None:
        # water rises into the lowest land near the sea
        low = (self.terrain.elevation < self.terrain.water_cut * 1.25) & self.terrain.passable
        self.flood = low.astype(np.float32)
        self.flood_ttl = int(self.rng.uniform(120, 400))

    # ------------------------------------------------------------- interventions
    def apply_rain(self, amount: float = 0.4) -> None:
        self.rain_state = float(np.clip(self.rain_state + amount, 0.05, 1.3))

    def apply_food(self, cx: int, cy: int, radius: int, amount: float) -> None:
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        dx = np.minimum(np.abs(xx - cx), self.w - np.abs(xx - cx))
        dy = np.minimum(np.abs(yy - cy), self.h - np.abs(yy - cy))
        mask = np.exp(-(dx * dx + dy * dy) / (2 * (radius or 1) ** 2))
        self.veg = np.clip(self.veg + mask.astype(np.float32) * amount * self.terrain.passable,
                           0.0, self.cfg.veg_capacity * 2.5)

    # ------------------------------------------------------------- rendering
    def render_layers(self, out_w: int, out_h: int) -> dict[str, Any]:
        ys = np.linspace(0, self.h - 1, out_h).astype(int)
        xs = np.linspace(0, self.w - 1, out_w).astype(int)
        ix = np.ix_(ys, xs)
        elev = self.terrain.elevation[ix]
        veg = np.clip(self.veg[ix] / max(1e-3, self.cfg.veg_capacity), 0, 1)
        water = self.terrain.water[ix]
        mountain = self.terrain.mountain[ix]
        fire = np.clip(self.fire[ix], 0, 1)
        flood = self.flood[ix] if self.flood.any() else np.zeros_like(elev)
        # pack a compact integer-ish payload
        return {
            "elev": elev.round(3).tolist(),
            "veg": veg.round(3).tolist(),
            "water": water.astype(int).tolist(),
            "mountain": mountain.astype(int).tolist(),
            "fire": fire.round(2).tolist(),
            "flood": (flood > 0).astype(int).tolist(),
        }

    # ------------------------------------------------------------- persistence
    def to_state(self) -> dict[str, Any]:
        return {
            "terrain": self.terrain.to_state(),
            "veg": self.veg, "pher": self.pher, "sound": self.sound,
            "meat": self.meat, "materials": self.materials,
            "fire": self.fire, "flood": self.flood, "flood_ttl": self.flood_ttl,
            "climate": self.climate, "rain_state": self.rain_state,
            "weather_name": self.weather_name,
        }

    def load_state(self, s: dict[str, Any]) -> None:
        self.terrain.load_state(s["terrain"])
        self.water_prox = self._blur(self.terrain.water.astype(np.float32), 4)
        self.veg = np.asarray(s["veg"], dtype=np.float32)
        self.pher = np.asarray(s["pher"], dtype=np.float32)
        self.sound = np.asarray(s["sound"], dtype=np.float32)
        self.meat = np.asarray(s["meat"], dtype=np.float32)
        self.materials = np.asarray(s["materials"], dtype=np.float32)
        self.fire = np.asarray(s["fire"], dtype=np.float32)
        self.flood = np.asarray(s["flood"], dtype=np.float32)
        self.flood_ttl = int(s["flood_ttl"])
        self.climate = float(s["climate"])
        self.rain_state = float(s["rain_state"])
        self.weather_name = s.get("weather_name", "templado")
