"""The neural network itself, isolated from genetics and physiology.

A tiny two-layer network (tanh hidden layer, linear output) that is: (1)
inherited with mutation across generations (evolution), and (2) nudged during
an individual's lifetime by reward-modulated plasticity on the output layer
(learning), which fades back toward the inherited weights over time
(forgetting). Genome owns the weight arrays; this module owns the math, so the
two concerns — "what is inherited" vs. "how a network computes and learns" —
stay separable and independently testable.
"""

from __future__ import annotations

import numpy as np


def init_weights(n_in: int, n_hidden: int, n_out: int, rng: np.random.Generator):
    si = 1.0 / np.sqrt(max(1, n_in))
    sh = 1.0 / np.sqrt(max(1, n_hidden))
    w1 = (rng.standard_normal((n_in, n_hidden)) * si).astype(np.float32)
    b1 = np.zeros(n_hidden, dtype=np.float32)
    w2 = (rng.standard_normal((n_hidden, n_out)) * sh).astype(np.float32)
    b2 = np.zeros(n_out, dtype=np.float32)
    return w1, b1, w2, b2


def mutate_weights(w1, b1, w2, b2, rng: np.random.Generator, scale: float):
    def mut(a):
        return (a + rng.standard_normal(a.shape).astype(np.float32) * scale).astype(np.float32)
    return mut(w1), mut(b1), mut(w2), mut(b2)


def forward(x: np.ndarray, w1, b1, w2, b2, fast_w2=None):
    """One decision: perception in, (raw outputs, hidden activations) out. The
    caller applies softmax/sigmoid per-output as appropriate for its meaning."""
    h = np.tanh(x @ w1 + b1)
    w2_eff = w2 if fast_w2 is None else (w2 + fast_w2)
    out = h @ w2_eff + b2
    return out, h


def hebbian_update(fast_w2: np.ndarray, hidden: np.ndarray, out: np.ndarray,
                    reward: float, lr: float) -> np.ndarray:
    """Reward-modulated Hebbian nudge on the output layer: trial and error.
    A positive reward reinforces the hidden->output pathway that just fired;
    a negative one weakens it. This is the only within-lifetime learning —
    the slow genome weights (w1, b1, w2, b2) never change during a life."""
    if lr <= 0 or abs(reward) < 1e-3:
        return fast_w2
    r = float(np.clip(reward / 5.0, -1.0, 1.0))
    act = np.tanh(out)
    fast_w2 = fast_w2 + lr * r * np.outer(hidden, act).astype(np.float32)
    np.clip(fast_w2, -1.5, 1.5, out=fast_w2)
    return fast_w2


def forget(fast_w2: np.ndarray, decay: float) -> np.ndarray:
    if decay > 0:
        fast_w2 *= (1.0 - decay)
    return fast_w2


def complexity_score(w1: np.ndarray, w2: np.ndarray) -> float:
    """A rough, comparable-across-species proxy for 'how much is going on in
    this brain' — used by the Cerebros tab, since diffing raw weight matrices
    means nothing to a human observer. Higher = weights are larger/more varied,
    i.e. the network relies on more of its capacity rather than sitting near
    its random-init scale."""
    return float(np.std(w1) + np.std(w2))
