"""Cognitive metrics that emerge from how the brain actually behaves.

The old "brain complexity = distance from the random init" told us almost
nothing. These metrics instead read the network *in action*, from the rolling
buffers of hidden activations and chosen actions that the simulation records for
spotlighted agents:

  - activation entropy: how spread-out neural activity is on a typical decision
    (low = a few neurons dominate; high = distributed representation);
  - active neurons per decision: how much of the network actually participates;
  - activation diversity: how different successive internal states are;
  - decision stability: how often the agent repeats its last action;
  - behavioural variability / complexity: entropy and count of distinct actions;
  - learning index: how far lifetime plasticity has moved the output weights;
  - reward trend: whether recent decisions are paying off better over time
    (a coarse "is it getting the hang of things" signal).

All of it is computed on demand from at most ~64 recent steps of a handful of
focused agents, so it never touches the per-tick cost of the whole population.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

ACTION_NAMES = {0: "descansar", 1: "atacar", 2: "reproducirse", 3: "emitir señal",
                4: "moverse"}


def _entropy(p: np.ndarray) -> float:
    p = p[p > 0]
    if p.size == 0:
        return 0.0
    h = -(p * np.log(p)).sum()
    return float(h / math.log(len(p))) if len(p) > 1 else 0.0


def compute(a) -> dict[str, Any]:
    buf = a.act_buffer
    hist = a.act_history
    n_samples = len(buf)
    out: dict[str, Any] = {
        "samples": n_samples,
        "learning_index": a.learning_index(),
    }
    if n_samples == 0:
        out.update({"activation_entropy": None, "active_neurons": None,
                    "activation_diversity": None})
    else:
        acts = np.array(buf)                      # (samples, hidden)
        # activation entropy: mean over decisions of the normalised entropy of |h|
        ents = []
        thr = 0.3
        active = []
        for h in acts:
            s = h.sum()
            if s > 1e-6:
                ents.append(_entropy(h / s))
            active.append(int((h > thr).sum()))
        out["activation_entropy"] = round(float(np.mean(ents)), 3) if ents else 0.0
        out["active_neurons"] = round(float(np.mean(active)), 2)
        out["hidden_size"] = int(acts.shape[1])
        # diversity: mean pairwise distance between successive activation vectors
        if n_samples > 1:
            diffs = np.linalg.norm(np.diff(acts, axis=0), axis=1)
            out["activation_diversity"] = round(float(np.mean(diffs)), 3)
        else:
            out["activation_diversity"] = 0.0

    if hist:
        arr = np.array(hist)
        distinct = len(set(hist))
        out["behavioral_complexity"] = distinct
        counts = np.bincount(arr, minlength=5).astype(float)
        p = counts / counts.sum()
        out["behavioral_variability"] = round(_entropy(p), 3)
        if len(hist) > 1:
            repeats = sum(1 for i in range(1, len(hist)) if hist[i] == hist[i - 1])
            out["decision_stability"] = round(repeats / (len(hist) - 1), 3)
        else:
            out["decision_stability"] = 0.0
        out["action_mix"] = {ACTION_NAMES.get(i, str(i)): int(counts[i])
                             for i in range(len(counts)) if counts[i] > 0}
    else:
        out.update({"behavioral_complexity": None, "behavioral_variability": None,
                    "decision_stability": None, "action_mix": {}})

    rh = a.reward_history
    if len(rh) >= 6:
        half = len(rh) // 2
        early, late = np.mean(rh[:half]), np.mean(rh[half:])
        out["reward_trend"] = round(float(late - early), 3)
    else:
        out["reward_trend"] = None
    return out
