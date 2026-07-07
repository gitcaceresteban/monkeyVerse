"""A shared discrete channel: ten symbols, 0 through 9.

The legend below is only a hypothesis shown to the observer — a naming
convention borrowed from what these kinds of signals *often* end up meaning in
nature. The engine attaches no effect to any symbol: emitting "1" does not make
food appear, and no agent is told what a symbol should mean. What agents do with
the channel — including whether they use it at all — is entirely down to
evolution and lifetime learning.

To find out whether meaning actually emerged, `SymbolStats` tracks, per species,
what context co-occurred with each symbol (danger nearby? food nearby? another
agent adjacent?). If a species' use of symbol "2" correlates strongly with
danger, that correlation was discovered, not built in.
"""

from __future__ import annotations

from typing import Any

import numpy as np

N_SYMBOLS = 10

LEGEND = {
    0: "neutral", 1: "comida", 2: "peligro", 3: "pareja/reproducción", 4: "seguir",
    5: "alejarse", 6: "territorio", 7: "ayuda", 8: "amenaza", 9: "exploración",
}

# context flags tracked per emission, for empirical meaning discovery
CONTEXTS = ["food_near", "danger_near", "agent_near", "low_energy", "resting", "attacking"]


class SymbolStats:
    """Rolling co-occurrence counts: symbol x context, per species."""

    def __init__(self):
        # species_id -> (10 x len(CONTEXTS)) counts, plus a total-emissions row
        self.counts: dict[int, np.ndarray] = {}
        self.totals: dict[int, np.ndarray] = {}   # per-species emissions of each symbol
        self.global_totals = np.zeros(N_SYMBOLS, dtype=np.int64)

    def record(self, species_id: int, symbol: int, context: dict[str, bool]) -> None:
        if species_id not in self.counts:
            self.counts[species_id] = np.zeros((N_SYMBOLS, len(CONTEXTS)), dtype=np.int64)
            self.totals[species_id] = np.zeros(N_SYMBOLS, dtype=np.int64)
        self.totals[species_id][symbol] += 1
        self.global_totals[symbol] += 1
        row = self.counts[species_id][symbol]
        for i, c in enumerate(CONTEXTS):
            if context.get(c):
                row[i] += 1

    def species_profile(self, species_id: int) -> dict[str, Any]:
        tot = self.totals.get(species_id)
        cnt = self.counts.get(species_id)
        if tot is None or tot.sum() == 0:
            return {"symbol_usage": [0] * N_SYMBOLS, "associations": {}}
        assoc = {}
        for s in range(N_SYMBOLS):
            n = tot[s]
            if n < 5:
                continue
            fracs = (cnt[s] / n).round(3)
            best_i = int(np.argmax(fracs))
            if fracs[best_i] > 0.55:
                assoc[s] = {"context": CONTEXTS[best_i], "strength": float(fracs[best_i]), "n": int(n)}
        return {"symbol_usage": tot.tolist(), "associations": assoc}

    def diversity(self, species_id: int | None = None) -> float:
        """Shannon entropy of symbol usage, normalised to [0,1]. 0 = one symbol
        dominates everything, 1 = all symbols used equally often."""
        tot = self.global_totals if species_id is None else self.totals.get(species_id)
        if tot is None:
            return 0.0
        s = tot.sum()
        if s <= 0:
            return 0.0
        p = tot / s
        p = p[p > 0]
        h = float(-(p * np.log(p)).sum())
        return round(h / np.log(N_SYMBOLS), 4)

    def most_used(self, n: int = 3) -> list[dict[str, Any]]:
        idx = np.argsort(-self.global_totals)[:n]
        return [{"symbol": int(i), "label": LEGEND[int(i)], "count": int(self.global_totals[i])}
                for i in idx if self.global_totals[i] > 0]

    def most_communicative_species(self, n: int = 5) -> list[tuple[int, int]]:
        pairs = [(sid, int(t.sum())) for sid, t in self.totals.items()]
        pairs.sort(key=lambda p: -p[1])
        return pairs[:n]

    # -------------------------------------------------------------- persistence
    def to_state(self) -> dict[str, Any]:
        return {
            "counts": {k: v for k, v in self.counts.items()},
            "totals": {k: v for k, v in self.totals.items()},
            "global_totals": self.global_totals,
        }

    def load_state(self, s: dict[str, Any]) -> None:
        self.counts = {int(k): np.asarray(v, dtype=np.int64) for k, v in s.get("counts", {}).items()}
        self.totals = {int(k): np.asarray(v, dtype=np.int64) for k, v in s.get("totals", {}).items()}
        self.global_totals = np.asarray(s.get("global_totals", np.zeros(N_SYMBOLS)), dtype=np.int64)
