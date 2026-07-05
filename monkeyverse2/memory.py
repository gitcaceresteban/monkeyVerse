"""Individual memory: where good and bad things happened, and who did them.

Memory is limited and fades (forgetting). It can also be wrong: recall is read
back with a little noise, so distorted memories are possible. None of this tells
an agent what to do — it is only extra, unreliable perception that the brain may
or may not learn to exploit.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class Memory:
    def __init__(self, slots: int, w: int, h: int):
        self.slots = max(0, slots)
        self.w, self.h = w, h
        # each landmark: [x, y, value]  (value>0 good place, value<0 danger)
        self.land = np.zeros((self.slots, 3), dtype=np.float32)
        # social valence: aid -> feeling (+ ally, - rival)
        self.social: dict[int, float] = {}

    # --------------------------------------------------------------- episodic
    def note_place(self, x: int, y: int, value: float) -> None:
        if self.slots == 0 or abs(value) < 0.05:
            return
        # reinforce an existing nearby landmark of the same sign, else replace weakest
        best_i, best_d = -1, 9.0
        for i in range(self.slots):
            if self.land[i, 2] == 0:
                continue
            if (self.land[i, 2] > 0) == (value > 0):
                d = abs(self.land[i, 0] - x) + abs(self.land[i, 1] - y)
                if d < best_d:
                    best_d, best_i = d, i
        if best_i >= 0 and best_d < 6:
            self.land[best_i, 0] = x
            self.land[best_i, 1] = y
            self.land[best_i, 2] = np.clip(self.land[best_i, 2] * 0.6 + value, -3, 3)
        else:
            j = int(np.argmin(np.abs(self.land[:, 2])))
            self.land[j] = (x, y, np.clip(value, -3, 3))

    def decay(self, rate: float = 0.002) -> None:
        if self.slots:
            self.land[:, 2] *= (1.0 - rate)
            self.land[np.abs(self.land[:, 2]) < 0.04, 2] = 0.0
        if self.social:
            drop = []
            for k in self.social:
                self.social[k] *= 0.995
                if abs(self.social[k]) < 0.05:
                    drop.append(k)
            for k in drop:
                del self.social[k]

    def recall(self, x: int, y: int, want_food: bool, noise: float, rng) -> tuple[float, float, float]:
        """Return (dx, dy, strength) toward the strongest remembered place of the
        requested kind, as a toroidal unit-ish vector. Empty => zeros."""
        if self.slots == 0:
            return 0.0, 0.0, 0.0
        vals = self.land[:, 2]
        cand = vals > 0 if want_food else vals < 0
        if not cand.any():
            return 0.0, 0.0, 0.0
        idx = int(np.argmax(np.abs(np.where(cand, vals, 0))))
        lx, ly, v = self.land[idx]
        dx = (lx - x + self.w / 2) % self.w - self.w / 2
        dy = (ly - y + self.h / 2) % self.h - self.h / 2
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        nx = dx / dist + rng.normal(0, noise)
        ny = dy / dist + rng.normal(0, noise)
        return float(nx), float(ny), float(np.clip(abs(v) / 3.0, 0, 1))

    # --------------------------------------------------------------- social
    def note_social(self, aid: int, delta: float, cap: int = 10) -> None:
        self.social[aid] = float(np.clip(self.social.get(aid, 0.0) + delta, -3, 3))
        if len(self.social) > cap:
            weakest = min(self.social, key=lambda k: abs(self.social[k]))
            del self.social[weakest]

    def feeling(self, aid: int) -> float:
        return self.social.get(aid, 0.0)

    # --------------------------------------------------------------- persistence
    def to_state(self) -> dict[str, Any]:
        return {"land": self.land, "social": self.social}

    def load_state(self, s: dict[str, Any]) -> None:
        self.land = np.asarray(s["land"], dtype=np.float32).reshape(self.slots, 3) if self.slots else self.land
        self.social = {int(k): float(v) for k, v in s.get("social", {}).items()}
