"""An island dweller.

Carries everything the observer wants to see about one individual: sex (A or B),
energy/age/state/position, its recurrent brain + hidden state + fast (learned)
weights, a small set of heritable physiological genes, a social relationship
matrix keyed by the other agent's id, its genealogy, and short rolling histories
of the sounds it emitted and heard and the interactions it had. It also keeps a
one-step debug snapshot (inputs, outputs, chosen action, reward) so the UI can
explain *why* it just did what it did.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .brain import Brain

# heritable genes are physiology only — behaviour must emerge from the brain,
# not be shortcut by a "sociability" or "aggression" gene.
GENE_BOUNDS = {
    "metabolism": (0.6, 1.5),   # scales energy decay
    "speed": (0.6, 1.5),        # scales movement step
    "learn_mul": (0.3, 1.7),    # scales lifetime learning rate
    "longevity": (0.7, 1.4),    # scales max age
    "hue": (0.0, 1.0),          # display only
}


def random_genes(rng):
    return {k: float(rng.uniform(lo, hi)) for k, (lo, hi) in GENE_BOUNDS.items()}


def crossover_genes(ga, gb, rng, mutation_rate):
    out = {}
    for k, (lo, hi) in GENE_BOUNDS.items():
        base = ga[k] if rng.random() < 0.5 else gb[k]
        base += rng.normal(0, 0.1 * mutation_rate * (hi - lo))
        out[k] = float(np.clip(base, lo, hi))
    return out


class Relationship:
    __slots__ = ("familiarity", "affinity", "trust", "pos", "neg", "last",
                 "sounds_heard", "responses")

    def __init__(self):
        self.familiarity = 0.0    # grows with any contact
        self.affinity = 0.0       # grows with positive interactions, decays with negative
        self.trust = 0.5
        self.pos = 0
        self.neg = 0
        self.last = 0
        self.sounds_heard = 0
        self.responses = 0

    def to_dict(self, tick, other_id):
        return {
            "agent_id": int(other_id),
            "familiarity": round(self.familiarity, 3),
            "affinity": round(self.affinity, 3),
            "trust": round(self.trust, 3),
            "positive": self.pos, "negative": self.neg,
            "sounds_heard": self.sounds_heard, "responses": self.responses,
            "last_seen_ago": int(tick - self.last),
        }


class Agent:
    __slots__ = ("id", "sex", "x", "y", "energy", "age", "state", "generation",
                 "parent_a", "parent_b", "brain", "h", "fast_wo", "genes",
                 "rel", "heard_vec", "emitted", "heard", "interactions",
                 "last_sound", "reward_total", "last_reward", "repro_cd",
                 "n_children", "fail_streak", "birth_tick", "repro_desire_tick",
                 "dbg_in", "dbg_out", "dbg_action", "n_sounds", "n_interactions")

    def __init__(self, aid, sex, x, y, brain: Brain, genes, cfg, generation=0,
                 parent_a=0, parent_b=0, birth_tick=0):
        self.id = aid
        self.sex = sex                 # "A" or "B"
        self.x = float(x)
        self.y = float(y)
        self.energy = cfg.initial_energy
        self.age = 0
        self.state = "explorando"
        self.generation = generation
        self.parent_a = parent_a
        self.parent_b = parent_b
        self.birth_tick = birth_tick
        self.brain = brain
        self.h = np.zeros(cfg.hidden_size, np.float32)
        self.fast_wo = np.zeros_like(brain.wo)
        self.genes = genes
        self.rel: dict[int, Relationship] = {}
        self.heard_vec = np.zeros(10, np.float32)     # decaying recent-sound perception
        self.emitted: list = []        # (tick, sound)
        self.heard: list = []          # (tick, sound, from_id)
        self.interactions: list = []   # recent interaction events
        self.last_sound = -1
        self.reward_total = 0.0
        self.last_reward = 0.0
        self.repro_cd = 0
        self.n_children = 0
        self.fail_streak = 0
        self.repro_desire_tick = -999   # last tick this agent actively sought to mate
        self.n_sounds = 0
        self.n_interactions = 0
        self.dbg_in = None
        self.dbg_out = None
        self.dbg_action = ""

    # ---------------------------------------------------------------- helpers
    @property
    def hunger(self) -> float:
        return float(np.clip(1.0 - self.energy / 120.0, 0.0, 1.0))

    def mature(self, cfg) -> bool:
        return self.age >= cfg.reproduction_min_age

    def relationship(self, other_id: int) -> Relationship:
        r = self.rel.get(other_id)
        if r is None:
            r = Relationship()
            self.rel[other_id] = r
            if len(self.rel) > 24:      # bounded social memory
                weakest = min(self.rel, key=lambda k: self.rel[k].familiarity)
                if weakest != other_id:
                    del self.rel[weakest]
        return r

    def push_emitted(self, tick, sound):
        self.emitted.append((tick, sound))
        if len(self.emitted) > 30:
            self.emitted = self.emitted[-30:]
        self.last_sound = sound
        self.n_sounds += 1

    def push_heard(self, tick, sound, from_id):
        self.heard.append((tick, sound, from_id))
        if len(self.heard) > 30:
            self.heard = self.heard[-30:]

    def push_interaction(self, ev):
        self.interactions.append(ev)
        if len(self.interactions) > 20:
            self.interactions = self.interactions[-20:]
        self.n_interactions += 1

    # ---------------------------------------------------------------- persistence
    def to_state(self):
        return {
            "id": self.id, "sex": self.sex, "x": self.x, "y": self.y, "energy": self.energy,
            "age": self.age, "state": self.state, "generation": self.generation,
            "parent_a": self.parent_a, "parent_b": self.parent_b, "birth_tick": self.birth_tick,
            "brain": self.brain.to_state(), "h": self.h, "fast_wo": self.fast_wo, "genes": self.genes,
            "rel": {k: [r.familiarity, r.affinity, r.trust, r.pos, r.neg, r.last, r.sounds_heard, r.responses]
                    for k, r in self.rel.items()},
            "heard_vec": self.heard_vec, "emitted": self.emitted, "heard": self.heard,
            "last_sound": self.last_sound, "reward_total": self.reward_total,
            "repro_cd": self.repro_cd, "n_children": self.n_children,
            "n_sounds": self.n_sounds, "n_interactions": self.n_interactions,
        }

    @classmethod
    def from_state(cls, d, cfg):
        a = cls(d["id"], d["sex"], d["x"], d["y"], Brain.from_state(d["brain"]),
                d["genes"], cfg, d["generation"], d["parent_a"], d["parent_b"], d["birth_tick"])
        a.energy = d["energy"]; a.age = d["age"]; a.state = d["state"]
        a.h = np.asarray(d["h"], np.float32); a.fast_wo = np.asarray(d["fast_wo"], np.float32)
        a.heard_vec = np.asarray(d["heard_vec"], np.float32)
        a.emitted = [tuple(e) for e in d.get("emitted", [])]
        a.heard = [tuple(e) for e in d.get("heard", [])]
        a.last_sound = d.get("last_sound", -1)
        a.reward_total = d.get("reward_total", 0.0)
        a.repro_cd = d.get("repro_cd", 0); a.n_children = d.get("n_children", 0)
        a.n_sounds = d.get("n_sounds", 0); a.n_interactions = d.get("n_interactions", 0)
        for k, v in d.get("rel", {}).items():
            r = a.relationship(int(k))
            (r.familiarity, r.affinity, r.trust, r.pos, r.neg, r.last, r.sounds_heard, r.responses) = v
        return a
