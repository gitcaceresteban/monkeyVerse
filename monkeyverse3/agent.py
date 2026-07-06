"""An organism. Just state + the machinery for within-life learning and the
observability trail (trajectory, recent interactions, recent symbols, current
state label). What it *does* each step is decided by its brain inside the
simulation loop — this class only carries what happened.
"""

from __future__ import annotations

import numpy as np

from . import brain as brainmod
from .genome import Genome
from .memory import Memory

STATES = ("explorando", "buscando_comida", "huyendo", "reproduciéndose",
          "descansando", "siguiendo_señal", "interactuando", "cazando")


class Agent:
    __slots__ = ("id", "genome", "x", "y", "energy", "age", "generation",
                 "parent_id", "birth_tick", "birth_x", "birth_y", "species_id",
                 "mem_vec", "fast_w2", "last_h", "last_out", "memory",
                 "inv_food", "inv_mat", "prev_energy", "moved", "resting",
                 "n_attacks", "n_children", "n_sound", "state",
                 "trajectory", "last_interactions", "last_symbols", "traj_cap",
                 "interact_cap", "symbol_cap", "follow_target", "follow_streak")

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
        self.state = "explorando"
        self.traj_cap = max(2, cfg.trajectory_length)
        self.interact_cap = max(1, cfg.interaction_log_size)
        self.symbol_cap = 12
        self.trajectory: list[tuple[int, int]] = [(x, y)]
        self.last_interactions: list[dict] = []
        self.last_symbols: list[tuple[int, int]] = []   # (tick, symbol)
        self.follow_target: int = 0                      # 0 = none (agent ids start at 1)
        self.follow_streak: int = 0

    def think(self, x_in):
        out, h = self.genome.forward(x_in, self.fast_w2)
        self.last_h = h
        self.last_out = out
        return out

    def learn(self, reward: float, lr: float, decay: float) -> None:
        """Reward-modulated plasticity (trial-and-error) plus forgetting,
        delegated to the standalone brain module."""
        if self.last_h is not None:
            self.fast_w2 = brainmod.hebbian_update(self.fast_w2, self.last_h,
                                                    self.last_out, reward, lr)
        self.fast_w2 = brainmod.forget(self.fast_w2, decay)

    # --------------------------------------------------------------- trail
    def push_position(self, x: int, y: int) -> None:
        self.trajectory.append((x, y))
        if len(self.trajectory) > self.traj_cap:
            self.trajectory = self.trajectory[-self.traj_cap:]

    def push_interaction(self, event: dict) -> None:
        self.last_interactions.append(event)
        if len(self.last_interactions) > self.interact_cap:
            self.last_interactions = self.last_interactions[-self.interact_cap:]

    def push_symbol(self, tick: int, symbol: int) -> None:
        self.last_symbols.append((tick, symbol))
        if len(self.last_symbols) > self.symbol_cap:
            self.last_symbols = self.last_symbols[-self.symbol_cap:]

    # --------------------------------------------------------------- persistence
    def to_state(self):
        return {
            "id": self.id, "x": self.x, "y": self.y, "energy": self.energy,
            "age": self.age, "generation": self.generation, "parent_id": self.parent_id,
            "birth_tick": self.birth_tick, "birth_x": self.birth_x, "birth_y": self.birth_y,
            "species_id": self.species_id, "mem_vec": self.mem_vec, "fast_w2": self.fast_w2,
            "inv_food": self.inv_food, "inv_mat": self.inv_mat,
            "n_attacks": self.n_attacks, "n_children": self.n_children, "n_sound": self.n_sound,
            "state": self.state, "trajectory": self.trajectory,
            "last_interactions": self.last_interactions, "last_symbols": self.last_symbols,
            "follow_target": self.follow_target, "follow_streak": self.follow_streak,
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
        a.state = d.get("state", "explorando")
        a.trajectory = [tuple(p) for p in d.get("trajectory", [(a.x, a.y)])]
        a.last_interactions = d.get("last_interactions", [])
        a.last_symbols = [tuple(s) for s in d.get("last_symbols", [])]
        a.follow_target = d.get("follow_target", 0)
        a.follow_streak = d.get("follow_streak", 0)
        a.memory.load_state(d["memory"])
        a.prev_energy = a.energy
        return a
