"""Individual memory: where good and bad things happened, and who did them.

Memory is limited and fades (forgetting). It can also be wrong: recall is read
back with a little noise, so distorted memories are possible. None of this tells
an agent what to do — it is only extra, unreliable perception that the brain may
or may not learn to exploit.

v3.1 makes the *social* half of memory rich enough to study relationships:
instead of a single valence per known individual, each remembered agent carries
how many positive and negative encounters happened, and when. From those raw,
behaviour-derived counts we can read off a relation (aliada / hostil / neutral)
and a trust score — the substrate for alliances, rivalries and recognition to
show up on their own. It also keeps lightweight forgetting/retention counters so
the evolution of memory itself becomes measurable.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class Memory:
    def __init__(self, slots: int, w: int, h: int):
        self.slots = max(0, slots)
        self.w, self.h = w, h
        # each landmark: [x, y, value, born_tick]  (value>0 good place, <0 danger)
        self.land = np.zeros((self.slots, 4), dtype=np.float32)
        # social memory: aid -> {"pos", "neg", "last", "first"} (encounter counts + ticks)
        self.social: dict[int, dict[str, float]] = {}
        # lifetime memory-dynamics counters (for the "memory statistics" panel)
        self.total_stored = 0
        self.total_forgotten = 0

    # --------------------------------------------------------------- episodic
    def note_place(self, x: int, y: int, value: float, tick: int = 0) -> None:
        if self.slots == 0 or abs(value) < 0.05:
            return
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
            if self.land[j, 2] != 0:
                self.total_forgotten += 1   # evicted an existing memory
            self.land[j] = (x, y, float(np.clip(value, -3, 3)), tick)
            self.total_stored += 1

    def decay(self, rate: float = 0.002) -> None:
        if self.slots:
            before = np.count_nonzero(self.land[:, 2])
            self.land[:, 2] *= (1.0 - rate)
            faded = np.abs(self.land[:, 2]) < 0.04
            self.land[faded, 2] = 0.0
            after = np.count_nonzero(self.land[:, 2])
            if after < before:
                self.total_forgotten += (before - after)
        if self.social:
            drop = []
            for k, r in self.social.items():
                r["pos"] *= 0.999
                r["neg"] *= 0.999
                if r["pos"] < 0.05 and r["neg"] < 0.05:
                    drop.append(k)
            for k in drop:
                del self.social[k]
                self.total_forgotten += 1

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
        lx, ly, v = self.land[idx, 0], self.land[idx, 1], self.land[idx, 2]
        dx = (lx - x + self.w / 2) % self.w - self.w / 2
        dy = (ly - y + self.h / 2) % self.h - self.h / 2
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        nx = dx / dist + rng.normal(0, noise)
        ny = dy / dist + rng.normal(0, noise)
        return float(nx), float(ny), float(np.clip(abs(v) / 3.0, 0, 1))

    # --------------------------------------------------------------- social
    def note_social(self, aid: int, kind: str, tick: int, cap: int = 12) -> None:
        r = self.social.get(aid)
        if r is None:
            r = {"pos": 0.0, "neg": 0.0, "last": tick, "first": tick}
            self.social[aid] = r
        if kind == "pos":
            r["pos"] += 1.0
        else:
            r["neg"] += 1.0
        r["last"] = tick
        if len(self.social) > cap:
            # forget the individual with the least emotional weight
            weakest = min(self.social, key=lambda k: self.social[k]["pos"] + self.social[k]["neg"])
            if weakest != aid:
                del self.social[weakest]
                self.total_forgotten += 1

    def feeling(self, aid: int) -> float:
        """Signed valence for perception (kept for backward compatibility)."""
        r = self.social.get(aid)
        if not r:
            return 0.0
        return float(np.clip(r["pos"] - r["neg"], -3, 3))

    def trust(self, aid: int) -> float:
        r = self.social.get(aid)
        if not r:
            return 0.0
        tot = r["pos"] + r["neg"]
        return round(r["pos"] / tot, 3) if tot > 0 else 0.0

    @staticmethod
    def _relation(r: dict[str, float]) -> str:
        tot = r["pos"] + r["neg"]
        if tot == 0:
            return "neutral"
        t = r["pos"] / tot
        if t >= 0.65:
            return "aliada"
        if t <= 0.35:
            return "hostil"
        return "neutral"

    def relations(self, tick: int, limit: int = 12) -> list[dict[str, Any]]:
        out = []
        for aid, r in self.social.items():
            out.append({
                "agent_id": int(aid),
                "relation": self._relation(r),
                "helped": int(round(r["pos"])),
                "attacked": int(round(r["neg"])),
                "trust": round(r["pos"] / (r["pos"] + r["neg"]), 3) if (r["pos"] + r["neg"]) else 0.0,
                "last_seen_ago": int(tick - r["last"]),
            })
        out.sort(key=lambda d: -(d["helped"] + d["attacked"]))
        return out[:limit]

    # --------------------------------------------------------------- stats
    def stats(self, tick: int) -> dict[str, Any]:
        active = self.land[np.abs(self.land[:, 2]) > 0] if self.slots else np.zeros((0, 4))
        avg_age = float(np.mean(tick - active[:, 3])) if len(active) else 0.0
        return {
            "stored_now": int(len(active)),
            "capacity": int(self.slots),
            "total_stored": int(self.total_stored),
            "total_forgotten": int(self.total_forgotten),
            "avg_memory_age": round(avg_age, 1),
            "individuals_known": int(len(self.social)),
        }

    # --------------------------------------------------------------- persistence
    def to_state(self) -> dict[str, Any]:
        return {"land": self.land, "social": self.social,
                "total_stored": self.total_stored, "total_forgotten": self.total_forgotten}

    def load_state(self, s: dict[str, Any]) -> None:
        if self.slots:
            land = np.asarray(s["land"], dtype=np.float32)
            if land.shape[1] == 3:  # migrate old 3-column landmarks
                land = np.concatenate([land, np.zeros((land.shape[0], 1), np.float32)], axis=1)
            self.land = land.reshape(self.slots, 4)
        soc = s.get("social", {})
        self.social = {}
        for k, v in soc.items():
            if isinstance(v, dict):
                self.social[int(k)] = {"pos": float(v.get("pos", 0)), "neg": float(v.get("neg", 0)),
                                       "last": float(v.get("last", 0)), "first": float(v.get("first", 0))}
            else:  # migrate old scalar valence
                val = float(v)
                self.social[int(k)] = {"pos": max(0.0, val), "neg": max(0.0, -val), "last": 0, "first": 0}
        self.total_stored = int(s.get("total_stored", 0))
        self.total_forgotten = int(s.get("total_forgotten", 0))
