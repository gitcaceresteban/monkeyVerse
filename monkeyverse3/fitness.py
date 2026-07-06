"""Composite evolutionary fitness — more than a child count.

Reproductive success is the backbone (natural selection ultimately counts
descendants), but a single number that also folds in survival, energy economy,
territory, cooperation, combat success and longevity is far more useful for
*studying* what "doing well" looks like in a given world. The weights below are
a deliberate, documented editorial choice by the observer — they don't affect
the simulation, only how we rank and read it.
"""

from __future__ import annotations

from typing import Any

WEIGHTS = {
    "descendants": 0.34,   # children + a fraction of grandchildren
    "survival": 0.16,      # age vs. this individual's own lifespan gene
    "energy": 0.12,        # peak energy reached (thriving, not just surviving)
    "territory": 0.10,     # fraction of world ever explored
    "cooperation": 0.10,   # peaceful social contact
    "combat": 0.10,        # share of fights won (only counts if it fought)
    "longevity": 0.08,     # raw age, capped
}


def compute(a, descendants: int = 0, grandchildren: int = 0) -> dict[str, Any]:
    max_age = max(1.0, a.genome.genes.get("max_age", 3000))
    survival = min(1.0, a.age / max_age)
    energy = min(1.0, a.peak_energy / 240.0)
    territory = a.territory_fraction()
    social_events = a.n_coop + a.n_follow + a.n_followed + a.n_attacks
    cooperation = min(1.0, (a.n_coop + a.n_follow) / max(1, social_events))
    fought = a.atk_won + a.atk_lost
    combat = (a.atk_won / fought) if fought else 0.0
    longevity = min(1.0, a.age / 6000.0)
    desc_score = min(1.0, (a.n_children + descendants * 0.15 + grandchildren * 0.05) / 12.0)

    parts = {
        "descendants": desc_score, "survival": survival, "energy": energy,
        "territory": territory, "cooperation": cooperation, "combat": combat,
        "longevity": longevity,
    }
    total = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)
    return {
        "score": round(total * 100, 1),
        "breakdown": {k: round(parts[k] * 100, 1) for k in parts},
        "weights": WEIGHTS,
    }
