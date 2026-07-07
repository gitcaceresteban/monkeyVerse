"""A small recurrent brain (a simplified GRU) with within-life learning.

Recurrence gives each agent short-term memory, so it can, in principle, learn
associations across time — e.g. "hearing tone 3 tends to be followed by finding
food". The recurrent core (Wxh/Whh/Wxz/Whz/biases) is *heritable* and comes from
crossing both parents. Learning during life happens only on the output layer, as
reward-modulated plasticity (fast weights that strengthen whatever the agent just
did when it paid off, and fade otherwise). No target signal, no backprop — just
trial and error shaped by reward.

Nothing here knows what a sound "means". The network is free to wire sounds to
actions or ignore them entirely; only selection and reward decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


@dataclass
class Brain:
    wxh: np.ndarray; whh: np.ndarray; bh: np.ndarray      # candidate state
    wxz: np.ndarray; whz: np.ndarray; bz: np.ndarray      # update gate
    wo: np.ndarray;  bo: np.ndarray                        # outputs

    # ------------------------------------------------------------ construction
    @classmethod
    def random(cls, n_in: int, hidden: int, n_out: int, rng: np.random.Generator) -> "Brain":
        si = 1.0 / np.sqrt(n_in + hidden)
        so = 1.0 / np.sqrt(hidden)
        r = lambda a, b, s: (rng.standard_normal((a, b)) * s).astype(np.float32)
        return cls(
            wxh=r(n_in, hidden, si), whh=r(hidden, hidden, si), bh=np.zeros(hidden, np.float32),
            wxz=r(n_in, hidden, si), whz=r(hidden, hidden, si), bz=np.zeros(hidden, np.float32),
            wo=r(hidden, n_out, so), bo=np.zeros(n_out, np.float32),
        )

    # ------------------------------------------------------------ inference
    def step(self, x: np.ndarray, h: np.ndarray, fast_wo=None):
        z = _sigmoid(x @ self.wxz + h @ self.whz + self.bz)
        cand = np.tanh(x @ self.wxh + h @ self.whh + self.bh)
        h_new = (z * h + (1.0 - z) * cand).astype(np.float32)
        wo = self.wo if fast_wo is None else (self.wo + fast_wo)
        out = h_new @ wo + self.bo
        return out, h_new

    # ------------------------------------------------------------ reproduction
    def crossover(self, other: "Brain", rng: np.random.Generator,
                  mutation_rate: float, scale: float) -> "Brain":
        """Child brain from two parents: uniform (per-weight) crossover plus small
        Gaussian mutations. This is the neural half of sexual inheritance."""
        def mix(a, b):
            mask = rng.random(a.shape) < 0.5
            child = np.where(mask, a, b)
            child = child + rng.standard_normal(a.shape) * (scale * mutation_rate)
            return child.astype(np.float32)
        return Brain(
            mix(self.wxh, other.wxh), mix(self.whh, other.whh), mix(self.bh, other.bh),
            mix(self.wxz, other.wxz), mix(self.whz, other.whz), mix(self.bz, other.bz),
            mix(self.wo, other.wo), mix(self.bo, other.bo),
        )

    def divergence(self, other: "Brain") -> float:
        """RMS weight difference — a cheap 'how different are these two brains'."""
        d = np.mean((self.wxh - other.wxh) ** 2) + np.mean((self.wo - other.wo) ** 2)
        return round(float(np.sqrt(d / 2)), 4)

    # ------------------------------------------------------------ serialization
    def to_state(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in
                ("wxh", "whh", "bh", "wxz", "whz", "bz", "wo", "bo")}

    @classmethod
    def from_state(cls, s: dict[str, Any]) -> "Brain":
        return cls(**{k: np.asarray(v, np.float32) for k, v in s.items()})


def reward_learn(fast_wo: np.ndarray, hidden: np.ndarray, out: np.ndarray,
                 reward: float, lr: float, decay: float) -> np.ndarray:
    """Reward-modulated Hebbian update on the output weights (lifetime learning)
    plus forgetting. Positive reward reinforces the hidden->output pathway that
    just fired; the fast weights fade back toward the inherited brain over time."""
    if lr > 0 and abs(reward) > 1e-3:
        r = float(np.clip(reward / 8.0, -1.0, 1.0))
        act = np.tanh(out)
        fast_wo = fast_wo + lr * r * np.outer(hidden, act).astype(np.float32)
        np.clip(fast_wo, -1.5, 1.5, out=fast_wo)
    if decay > 0:
        fast_wo *= (1.0 - decay)
    return fast_wo
