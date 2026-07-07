"""Explaining a single decision.

Generic helpers (no knowledge of the exact perception layout — the caller passes
that in) that turn one forward pass into something a human can read: which
*kinds* of input mattered most, which hidden neurons fired, what action came
out, how decisively, and what the agent seems to be *trying* to do. The
simulation, which owns the input/output index layout, wires these together with
a few plain-language perception readings in `_decision_trace`.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def salient_inputs(x_in: np.ndarray, w1: np.ndarray, bucket_map: list[str],
                   top_k: int = 5) -> list[dict[str, Any]]:
    """Rank input *categories* by how much they drove the hidden layer this
    step: contribution_i = |x_i| * ||W1[i, :]||, summed per category."""
    contrib = np.abs(x_in) * np.linalg.norm(w1, axis=1)
    buckets: dict[str, float] = {}
    for i, b in enumerate(bucket_map):
        if i < len(contrib):
            buckets[b] = buckets.get(b, 0.0) + float(contrib[i])
    total = sum(buckets.values()) or 1.0
    ranked = sorted(buckets.items(), key=lambda kv: -kv[1])[:top_k]
    return [{"input": name, "weight": round(v / total, 3)} for name, v in ranked if v > 0]


def top_neurons(h: np.ndarray, k: int = 5) -> list[dict[str, Any]]:
    if h is None:
        return []
    order = np.argsort(-np.abs(h))[:k]
    return [{"neuron": int(i), "activation": round(float(h[i]), 3)} for i in order]


def move_confidence(out: np.ndarray) -> float:
    logits = out[0:9]
    p = np.exp(logits - logits.max())
    p /= p.sum()
    return round(float(p.max()) * 100, 1)


def inferred_goals(out: np.ndarray, genes: dict, idx: dict, n_symbols: int) -> list[dict[str, Any]]:
    """Read the network's *intent* off its raw outputs — never programmed, just
    interpreted. Each goal gets 0-5 stars from the relevant output activations."""
    logits = out[0:9]
    p = np.exp(logits - logits.max()); p /= p.sum()
    move_drive = float(1.0 - p[0])            # probability mass on *not* staying put
    rest = float(_sigmoid(out[idx["REST"]]))
    attack = float(_sigmoid(out[idx["ATTACK"]] + genes.get("agg_bias", 0.0)))
    repro = float(_sigmoid(out[idx["REPRO"]]))
    speak = float(_sigmoid(out[idx["SPEAK"]]))

    goals = [
        ("Buscar comida / explorar", move_drive),
        ("Atacar / defender territorio", attack),
        ("Reproducirse / buscar pareja", repro),
        ("Comunicar / coordinar", speak),
        ("Descansar", rest),
    ]
    goals.sort(key=lambda g: -g[1])
    return [{"goal": name, "stars": int(round(max(0.0, min(1.0, score)) * 5)),
             "score": round(score, 3)} for name, score in goals]
