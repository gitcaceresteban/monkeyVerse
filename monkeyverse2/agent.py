"""An organism. Just state + the machinery for within-life learning. What it
*does* each step is decided by its brain inside the simulation loop.
"""

from __future__ import annotations

import numpy as np

from .genome import Genome
from .memory import Memory


class Agent:
    __slots__ = ("id", "genome", "x", "y", "energy", "age", "generation",
                 "parent_id", "birth_tick", "birth_x", "birth_y", "species_id",
                 "mem_vec", "fast_w2", "last_h", "last_out", "memory",
                 "inv_food", "inv_mat", "prev_energy", "moved", "resting",
                 "n_attacks", "n_children", "n_sound")

    def __init__(self, aid, genome: Genome, x, y, energy, generation, parent_id,
                 birth_tick, cfg, species_id=0):
        self.id = aid
        self.genome = genome
        self.x = x
        self.y = y
        self.energy = float(energy)
        self.age = 0
        self.generation = generation
        self.parent_id = parent_id
        self.birth_tick = birth_tick
        self.birth_x = x
        self.birth_y = y
        self.species_id = species_id
        self.mem_vec = np.zeros(max(0, cfg.memory_size), dtype=np.float32)
        self.fast_w2 = np.zeros_like(genome.w2)
        self.last_h = None
        self.last_out = None
        self.memory = Memory(cfg.episodic_slots, cfg.width, cfg.height)
        self.inv_food = 0.0
        self.inv_mat = 0.0
        self.prev_energy = float(energy)
        self.moved = False
        self.resting = False
        self.n_attacks = 0
        self.n_children = 0
        self.n_sound = 0

    def think(self, x_in):
        out, h = self.genome.forward(x_in, self.fast_w2)
        self.last_h = h
        self.last_out = out
        return out

    def learn(self, reward: float, lr: float, decay: float) -> None:
        """Reward-modulated plasticity on the output layer (trial-and-error).
        Positive reward reinforces whatever the brain just did; forgetting pulls
        the fast weights slowly back toward the inherited genome."""
        if lr > 0 and self.last_h is not None and abs(reward) > 1e-3:
            r = float(np.clip(reward / 5.0, -1.0, 1.0))
            act = np.tanh(self.last_out)
            self.fast_w2 += lr * r * np.outer(self.last_h, act).astype(np.float32)
            np.clip(self.fast_w2, -1.5, 1.5, out=self.fast_w2)
        if decay > 0:
            self.fast_w2 *= (1.0 - decay)

    # --------------------------------------------------------------- persistence
    def to_state(self):
        return {
            "id": self.id, "x": self.x, "y": self.y, "energy": self.energy,
            "age": self.age, "generation": self.generation, "parent_id": self.parent_id,
            "birth_tick": self.birth_tick, "birth_x": self.birth_x, "birth_y": self.birth_y,
            "species_id": self.species_id, "mem_vec": self.mem_vec, "fast_w2": self.fast_w2,
            "inv_food": self.inv_food, "inv_mat": self.inv_mat,
            "n_attacks": self.n_attacks, "n_children": self.n_children, "n_sound": self.n_sound,
            "memory": self.memory.to_state(), "genome": self.genome.to_state(),
        }

    @classmethod
    def from_state(cls, d, cfg):
        a = cls(d["id"], Genome.from_state(d["genome"]), d["x"], d["y"], d["energy"],
                d["generation"], d["parent_id"], d["birth_tick"], cfg, d.get("species_id", 0))
        a.age = d["age"]
        a.birth_x = d.get("birth_x", d["x"])
        a.birth_y = d.get("birth_y", d["y"])
        a.mem_vec = np.asarray(d["mem_vec"], np.float32)
        a.fast_w2 = np.asarray(d["fast_w2"], np.float32)
        a.inv_food = d.get("inv_food", 0.0)
        a.inv_mat = d.get("inv_mat", 0.0)
        a.n_attacks = d.get("n_attacks", 0)
        a.n_children = d.get("n_children", 0)
        a.n_sound = d.get("n_sound", 0)
        a.memory.load_state(d["memory"])
        a.prev_energy = a.energy
        return a
