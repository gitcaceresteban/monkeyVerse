"""Heritable material: a small neural brain, a set of physiological genes, and a
visible colour. Behaviour is not encoded — only biology and a couple of weak
innate dispositions that evolution can tune. Real strategy comes from the brain
(shaped by lifetime learning) and from selection across generations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from . import brain as brainmod

# scalar genes: name -> (low, high). Physiology + two weak innate dispositions.
GENE_BOUNDS: dict[str, tuple[float, float]] = {
    "metabolism":       (0.4, 1.8),
    "plant_eff":        (0.3, 1.6),   # digestion of vegetation (herbivory)
    "meat_eff":         (0.3, 1.6),   # digestion of meat (predation / scavenging)
    "diet":             (0.0, 1.0),   # 0 = herbivore, 1 = carnivore (which food nourishes)
    "size":             (0.6, 1.6),   # bigger = stronger attack but costlier
    "vision":           (0.6, 1.6),   # perception clarity (noise reduction)
    "speed":            (0.0, 1.0),   # chance of taking a second step
    "max_age":          (500.0, 8000.0),
    "repro_threshold":  (25.0, 170.0),
    "repro_investment": (0.2, 0.7),
    "mutation_rate":    (0.0, 0.5),
    "agg_bias":         (-1.0, 1.0),  # innate lean toward/against attacking
    "explore_bias":     (0.0, 1.0),   # innate curiosity (movement stochasticity)
}


def _rand(name, rng):
    lo, hi = GENE_BOUNDS[name]
    return float(rng.uniform(lo, hi))


@dataclass
class Genome:
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    genes: dict[str, float]
    color: np.ndarray          # visible display trait

    # ------------------------------------------------------------ construction
    @classmethod
    def random(cls, n_in, n_hidden, n_out, color_channels, rng, mutation_rate):
        w1, b1, w2, b2 = brainmod.init_weights(n_in, n_hidden, n_out, rng)
        genes = {k: _rand(k, rng) for k in GENE_BOUNDS}
        genes["mutation_rate"] = float(mutation_rate)
        return cls(w1=w1, b1=b1, w2=w2, b2=b2, genes=genes,
                   color=rng.random(max(0, color_channels)).astype(np.float32))

    # ------------------------------------------------------------ reproduction
    def child(self, rng, weight_scale) -> "Genome":
        mr = float(np.clip(self.genes.get("mutation_rate", 0.1), *GENE_BOUNDS["mutation_rate"]))
        w1, b1, w2, b2 = brainmod.mutate_weights(self.w1, self.b1, self.w2, self.b2,
                                                 rng, weight_scale * mr)
        genes = {}
        for k, (lo, hi) in GENE_BOUNDS.items():
            span = hi - lo
            v = self.genes.get(k, (lo + hi) / 2) + rng.normal(0, 0.15 * mr * span)
            genes[k] = float(np.clip(v, lo, hi))
        color = np.clip(self.color + rng.normal(0, 0.06 * mr, self.color.shape), 0, 1).astype(np.float32)
        return Genome(w1, b1, w2, b2, genes, color)

    # ------------------------------------------------------------ inference
    def forward(self, x, fast_w2=None):
        return brainmod.forward(x, self.w1, self.b1, self.w2, self.b2, fast_w2)

    def complexity(self) -> float:
        return brainmod.complexity_score(self.w1, self.w2)

    # ------------------------------------------------------------ species dist
    _KEYS = ("metabolism", "plant_eff", "meat_eff", "diet", "size", "vision",
             "speed", "agg_bias", "explore_bias")

    def gene_vector(self) -> np.ndarray:
        out = []
        for k in self._KEYS:
            lo, hi = GENE_BOUNDS[k]
            out.append((self.genes.get(k, 0) - lo) / (hi - lo))
        out.extend(self.color.tolist())
        return np.asarray(out, dtype=np.float32)

    def distance(self, vec: np.ndarray) -> float:
        v = self.gene_vector()
        n = min(len(v), len(vec))
        return float(np.sqrt(np.mean((v[:n] - vec[:n]) ** 2)))

    # ------------------------------------------------------------ serialization
    def to_state(self) -> dict[str, Any]:
        return {"w1": self.w1, "b1": self.b1, "w2": self.w2, "b2": self.b2,
                "genes": dict(self.genes), "color": self.color}

    @classmethod
    def from_state(cls, s) -> "Genome":
        return cls(
            np.asarray(s["w1"], np.float32), np.asarray(s["b1"], np.float32),
            np.asarray(s["w2"], np.float32), np.asarray(s["b2"], np.float32),
            dict(s["genes"]), np.asarray(s["color"], np.float32))
