"""The heritable material: a tiny recurrent brain plus a few scalar genes.

Nothing here encodes a behaviour. The brain is a randomly-initialised network;
the genes are physiological parameters. Selection + mutation over generations is
the only thing that can turn this into anything interesting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


# Scalar genes: name -> (low, high). These are physiology, not strategy.
GENE_BOUNDS: dict[str, tuple[float, float]] = {
    "metabolism": (0.4, 1.8),        # multiplies base metabolism cost
    "diet_efficiency": (0.5, 1.6),   # energy actually gained per unit of food
    "repro_threshold": (35.0, 220.0),  # energy needed before reproduction is possible
    "repro_investment": (0.2, 0.7),  # fraction of energy handed to the offspring
    "max_age": (400.0, 5000.0),      # lifespan ceiling in steps
    "mutation_rate": (0.0, 0.5),     # self-adapting: mutation mutates itself
    "hue": (0.0, 1.0),               # lineage colour (purely for the observer)
}


def _rand_gene(name: str, rng: np.random.Generator) -> float:
    lo, hi = GENE_BOUNDS[name]
    return float(rng.uniform(lo, hi))


@dataclass
class Genome:
    # brain weights (single hidden layer, tanh) — dims fixed by SimConfig
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    genes: dict[str, float]

    # ---- construction ------------------------------------------------------
    @classmethod
    def random(cls, n_in: int, n_hidden: int, n_out: int, rng: np.random.Generator,
               mutation_rate: float) -> "Genome":
        scale_in = 1.0 / np.sqrt(max(1, n_in))
        scale_h = 1.0 / np.sqrt(max(1, n_hidden))
        genes = {name: _rand_gene(name, rng) for name in GENE_BOUNDS}
        genes["mutation_rate"] = float(mutation_rate)
        return cls(
            w1=(rng.standard_normal((n_in, n_hidden)) * scale_in).astype(np.float32),
            b1=np.zeros(n_hidden, dtype=np.float32),
            w2=(rng.standard_normal((n_hidden, n_out)) * scale_h).astype(np.float32),
            b2=np.zeros(n_out, dtype=np.float32),
            genes=genes,
        )

    # ---- reproduction ------------------------------------------------------
    def child(self, rng: np.random.Generator, weight_scale: float) -> "Genome":
        """Asexual reproduction with mutation. The child's mutation_rate gene
        governs how strongly everything (including that gene) drifts."""
        mr = float(np.clip(self.genes.get("mutation_rate", 0.1), *GENE_BOUNDS["mutation_rate"]))

        def mutate(a: np.ndarray) -> np.ndarray:
            noise = rng.standard_normal(a.shape).astype(np.float32) * (weight_scale * mr)
            return (a + noise).astype(np.float32)

        genes: dict[str, float] = {}
        for name, (lo, hi) in GENE_BOUNDS.items():
            span = hi - lo
            val = self.genes.get(name, (lo + hi) / 2)
            val = val + rng.normal(0.0, 0.15 * mr * span)
            genes[name] = float(np.clip(val, lo, hi))

        return Genome(
            w1=mutate(self.w1), b1=mutate(self.b1),
            w2=mutate(self.w2), b2=mutate(self.b2),
            genes=genes,
        )

    # ---- inference ---------------------------------------------------------
    def forward(self, x: np.ndarray) -> np.ndarray:
        h = np.tanh(x @ self.w1 + self.b1)
        return h @ self.w2 + self.b2

    # ---- similarity (used only for analysis, never fed to the brain) -------
    def distance(self, other: "Genome") -> float:
        d = 0.0
        for name in GENE_BOUNDS:
            lo, hi = GENE_BOUNDS[name]
            span = hi - lo or 1.0
            d += ((self.genes.get(name, 0) - other.genes.get(name, 0)) / span) ** 2
        return float(np.sqrt(d / len(GENE_BOUNDS)))

    # ---- serialization -----------------------------------------------------
    def to_state(self) -> dict[str, Any]:
        return {
            "w1": self.w1, "b1": self.b1, "w2": self.w2, "b2": self.b2,
            "genes": dict(self.genes),
        }

    @classmethod
    def from_state(cls, s: dict[str, Any]) -> "Genome":
        return cls(
            w1=np.asarray(s["w1"], dtype=np.float32),
            b1=np.asarray(s["b1"], dtype=np.float32),
            w2=np.asarray(s["w2"], dtype=np.float32),
            b2=np.asarray(s["b2"], dtype=np.float32),
            genes=dict(s["genes"]),
        )
