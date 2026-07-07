"""An organism. State + within-life learning + the observability trail.

v3.1 turns each agent into an analysable subject. On top of the trajectory /
recent-interactions / recent-symbols trail it already had, it now keeps, *cheaply
for every agent*:

  - a chronological episodic event log (found food, ate, heard/emitted a signal,
    followed / was followed, attacked / was attacked, reproduced, discovered
    territory, a neighbour died);
  - detailed combat counters (attacks made/won/lost, damage dealt/received,
    energy gained, kills);
  - behaviour counters used to *derive* an emergent personality (moves, rests,
    cooperations, follows, signals, times attacked) and a coarse territory
    bitset (which regions of the world it has ever visited);
  - "life firsts" ticks (first food/attack/reproduction/signal) for its timeline.

And *only while it is in the observer's spotlight* (selected / followed /
compared — at most a handful of agents), it additionally records the expensive
introspection data (the exact perception input, a rolling buffer of hidden
activations and chosen actions, recent rewards) needed for decision traces and
cognitive metrics. Everything else stays off, so the cost is bounded no matter
how many hundreds of agents are alive.
"""

from __future__ import annotations

import numpy as np

from . import brain as brainmod
from .genome import Genome
from .memory import Memory

STATES = ("explorando", "buscando_comida", "huyendo", "reproduciéndose",
          "descansando", "siguiendo_señal", "interactuando", "cazando")

# coarse territory grid (a Python int is used as a bitset over these blocks)
TERR_COLS, TERR_ROWS = 12, 8
TERR_BLOCKS = TERR_COLS * TERR_ROWS


class Agent:
    __slots__ = ("id", "genome", "x", "y", "energy", "age", "generation",
                 "parent_id", "birth_tick", "birth_x", "birth_y", "species_id",
                 "mem_vec", "fast_w2", "last_h", "last_out", "memory",
                 "inv_food", "inv_mat", "prev_energy", "moved", "resting",
                 "n_attacks", "n_children", "n_sound", "state",
                 "trajectory", "last_interactions", "last_symbols", "traj_cap",
                 "interact_cap", "symbol_cap", "follow_target", "follow_streak",
                 # episodic + counters (cheap, all agents)
                 "events", "event_cap",
                 "atk_won", "atk_lost", "dmg_dealt", "dmg_received",
                 "energy_from_atk", "wounds", "kills",
                 "n_moves", "n_rests", "n_coop", "n_follow", "n_followed",
                 "peak_energy", "territory_bits", "new_cells", "sym_counts",
                 "t_first_food", "t_first_attack", "t_first_repro", "t_first_signal",
                 # spotlight-only (expensive, few agents)
                 "spotlighted", "last_input", "act_buffer", "act_history",
                 "reward_history", "last_confidence", "spot_cap")

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
        self.last_symbols: list[tuple[int, int]] = []
        self.follow_target: int = 0
        self.follow_streak: int = 0

        # episodic + counters
        self.events: list[dict] = []
        self.event_cap = 40
        self.atk_won = 0
        self.atk_lost = 0
        self.dmg_dealt = 0.0
        self.dmg_received = 0.0
        self.energy_from_atk = 0.0
        self.wounds = 0
        self.kills = 0
        self.n_moves = 0
        self.n_rests = 0
        self.n_coop = 0
        self.n_follow = 0
        self.n_followed = 0
        self.peak_energy = float(energy)
        self.territory_bits = 0
        self.new_cells = 0
        self.sym_counts = [0] * 10   # lifetime tally of each language symbol used
        self.t_first_food = 0
        self.t_first_attack = 0
        self.t_first_repro = 0
        self.t_first_signal = 0

        # spotlight-only
        self.spotlighted = False
        self.last_input = None
        self.act_buffer: list = []
        self.act_history: list = []
        self.reward_history: list = []
        self.last_confidence = 0.0
        self.spot_cap = 64

    def think(self, x_in):
        out, h = self.genome.forward(x_in, self.fast_w2)
        self.last_h = h
        self.last_out = out
        return out

    def learn(self, reward: float, lr: float, decay: float) -> None:
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

    # --------------------------------------------------------------- episodic
    def log_event(self, tick: int, kind: str, detail: str = "") -> None:
        self.events.append({"tick": tick, "kind": kind, "detail": detail})
        if len(self.events) > self.event_cap:
            self.events = self.events[-self.event_cap:]

    def mark_territory(self, w: int, h: int) -> bool:
        bx = min(TERR_COLS - 1, self.x * TERR_COLS // max(1, w))
        by = min(TERR_ROWS - 1, self.y * TERR_ROWS // max(1, h))
        bit = 1 << (by * TERR_COLS + bx)
        if not (self.territory_bits & bit):
            self.territory_bits |= bit
            self.new_cells += 1
            return True
        return False

    def territory_fraction(self) -> float:
        return bin(self.territory_bits).count("1") / TERR_BLOCKS

    # --------------------------------------------------------------- spotlight
    def record_decision(self, x_in, action_code: int, confidence: float, reward: float) -> None:
        """Only called for spotlighted agents — stores the introspection data
        that decision traces and cognitive metrics are computed from."""
        self.last_input = np.asarray(x_in, dtype=np.float32).copy()
        self.last_confidence = confidence
        if self.last_h is not None:
            self.act_buffer.append(np.abs(self.last_h).astype(np.float32))
            if len(self.act_buffer) > self.spot_cap:
                self.act_buffer = self.act_buffer[-self.spot_cap:]
        self.act_history.append(action_code)
        if len(self.act_history) > self.spot_cap:
            self.act_history = self.act_history[-self.spot_cap:]
        self.reward_history.append(round(float(reward), 3))
        if len(self.reward_history) > self.spot_cap:
            self.reward_history = self.reward_history[-self.spot_cap:]

    def clear_spotlight(self) -> None:
        self.spotlighted = False
        self.last_input = None
        self.act_buffer = []
        self.act_history = []
        self.reward_history = []

    def learning_index(self) -> float:
        """Cheap, all-agent proxy: how far lifetime plasticity has pushed the
        output weights away from the inherited genome."""
        denom = float(np.linalg.norm(self.genome.w2)) + 1e-6
        return round(float(np.linalg.norm(self.fast_w2)) / denom, 4)

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
            "events": self.events,
            "atk_won": self.atk_won, "atk_lost": self.atk_lost, "dmg_dealt": self.dmg_dealt,
            "dmg_received": self.dmg_received, "energy_from_atk": self.energy_from_atk,
            "wounds": self.wounds, "kills": self.kills,
            "n_moves": self.n_moves, "n_rests": self.n_rests, "n_coop": self.n_coop,
            "n_follow": self.n_follow, "n_followed": self.n_followed,
            "peak_energy": self.peak_energy, "territory_bits": self.territory_bits,
            "new_cells": self.new_cells, "sym_counts": self.sym_counts,
            "t_first_food": self.t_first_food, "t_first_attack": self.t_first_attack,
            "t_first_repro": self.t_first_repro, "t_first_signal": self.t_first_signal,
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
        a.events = d.get("events", [])
        a.atk_won = d.get("atk_won", 0)
        a.atk_lost = d.get("atk_lost", 0)
        a.dmg_dealt = d.get("dmg_dealt", 0.0)
        a.dmg_received = d.get("dmg_received", 0.0)
        a.energy_from_atk = d.get("energy_from_atk", 0.0)
        a.wounds = d.get("wounds", 0)
        a.kills = d.get("kills", 0)
        a.n_moves = d.get("n_moves", 0)
        a.n_rests = d.get("n_rests", 0)
        a.n_coop = d.get("n_coop", 0)
        a.n_follow = d.get("n_follow", 0)
        a.n_followed = d.get("n_followed", 0)
        a.peak_energy = d.get("peak_energy", a.energy)
        a.territory_bits = d.get("territory_bits", 0)
        a.new_cells = d.get("new_cells", 0)
        a.sym_counts = list(d.get("sym_counts", [0] * 10))
        a.t_first_food = d.get("t_first_food", 0)
        a.t_first_attack = d.get("t_first_attack", 0)
        a.t_first_repro = d.get("t_first_repro", 0)
        a.t_first_signal = d.get("t_first_signal", 0)
        a.memory.load_state(d["memory"])
        a.prev_energy = a.energy
        return a
