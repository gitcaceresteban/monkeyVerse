"""The simulation loop.

One `Simulation` owns a `World` and a population of `Agent`s. Each step every
agent perceives a small local patch, its brain produces raw action outputs, and
those are turned into movement / eating / reproduction / signal emission. That is
the *entire* rule set. There is no code for cooperation, territory, language, or
any social concept — those can only ever be emergent.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np

from .config import SimConfig
from .genome import Genome, GENE_BOUNDS
from .world import World

# 0 = stay, then the 8 Moore-neighbour directions.
MOVE_OFFSETS = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
                (1, 1), (1, -1), (-1, 1), (-1, -1)]
NEIGHBOR8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class Agent:
    __slots__ = ("id", "genome", "x", "y", "energy", "age", "generation",
                 "parent_id", "birth_tick", "memory", "last_signal", "moved")

    def __init__(self, aid: int, genome: Genome, x: int, y: int, energy: float,
                 generation: int, parent_id: int, birth_tick: int, mem: int, sig: int):
        self.id = aid
        self.genome = genome
        self.x = x
        self.y = y
        self.energy = energy
        self.age = 0
        self.generation = generation
        self.parent_id = parent_id
        self.birth_tick = birth_tick
        self.memory = np.zeros(mem, dtype=np.float32)
        self.last_signal = np.zeros(sig, dtype=np.float32)
        self.moved = False


class Simulation:
    def __init__(self, sim_id: str, cfg: SimConfig, persistence=None, populate: bool = True):
        self.id = sim_id
        self.cfg = cfg
        self.persistence = persistence
        self.seed = cfg.resolved_seed()
        self.rng = np.random.default_rng(self.seed)

        self.world = World(cfg, self.rng)
        self.S = max(0, cfg.signal_channels)
        self.M = max(0, cfg.memory_size)
        self.n_in = 16 + 3 * self.S + self.M
        self.n_out = 10 + self.S + self.M

        self.tick = 0
        self.next_id = 1
        self.agents: list[Agent] = []

        # running counters
        self.births_total = 0
        self.deaths_total = 0
        self._births_interval = 0
        self._deaths_interval = 0
        self._deaths_starve = 0
        self._deaths_age = 0
        self.last_event: Optional[str] = None

        if populate:
            self._populate()

    # ---------------------------------------------------------------- populate
    def _new_genome(self) -> Genome:
        return Genome.random(self.n_in, self.cfg.brain_hidden, self.n_out,
                             self.rng, self.cfg.initial_mutation_rate)

    def _populate(self) -> None:
        for _ in range(self.cfg.initial_population):
            x = int(self.rng.integers(0, self.world.w))
            y = int(self.rng.integers(0, self.world.h))
            a = Agent(self.next_id, self._new_genome(), x, y, self.cfg.initial_energy,
                      generation=0, parent_id=0, birth_tick=0, mem=self.M, sig=self.S)
            self.next_id += 1
            self.agents.append(a)
            if self.persistence:
                self.persistence.log_birth(self._birth_row(a))

    # ---------------------------------------------------------------- indexing
    def _build_buckets(self) -> dict[tuple[int, int], list[int]]:
        buckets: dict[tuple[int, int], list[int]] = {}
        for i, a in enumerate(self.agents):
            buckets.setdefault((a.x, a.y), []).append(i)
        return buckets

    # ---------------------------------------------------------------- perceive
    def _perceive(self, a: Agent, buckets) -> np.ndarray:
        w, h = self.world.w, self.world.h
        food = self.world.food
        sig = self.world.signal
        r = self.cfg.perception_radius

        inp = np.empty(self.n_in, dtype=np.float32)
        k = 0
        inp[k] = np.tanh(a.energy / 60.0); k += 1
        inp[k] = min(1.0, a.age / max(1.0, a.genome.genes["max_age"])); k += 1
        inp[k] = food[a.y, a.x] / (self.cfg.resource_capacity or 1.0); k += 1
        for dx, dy in NEIGHBOR8:
            inp[k] = food[(a.y + dy) % h, (a.x + dx) % w] / (self.cfg.resource_capacity or 1.0)
            k += 1
        # signal here
        if self.S:
            inp[k:k + self.S] = sig[a.y, a.x]; k += self.S
            # neighbourhood-averaged signal
            y0, x0 = (a.y - 1) % h, (a.x - 1) % w
            acc = np.zeros(self.S, dtype=np.float32)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    acc += sig[(a.y + dy) % h, (a.x + dx) % w]
            inp[k:k + self.S] = acc / 9.0; k += self.S

        # nearest other agent + local density, in a single neighbourhood sweep
        best_d2 = None
        best = None
        density = 0
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                occ = buckets.get(((a.x + dx) % w, (a.y + dy) % h))
                if not occ:
                    continue
                for j in occ:
                    other = self.agents[j]
                    if other.id == a.id:
                        continue
                    density += 1
                    d2 = dx * dx + dy * dy
                    if best_d2 is None or d2 < best_d2:
                        best_d2 = d2
                        best = (other, dx, dy)

        if best is not None:
            other, dx, dy = best
            inp[k] = dx / r; inp[k + 1] = dy / r
            inp[k + 2] = 1.0 - min(1.0, (best_d2 ** 0.5) / r)
            k += 3
            if self.S:
                inp[k:k + self.S] = other.last_signal; k += self.S
            inp[k] = other.genome.genes["hue"]; k += 1
        else:
            inp[k:k + 3 + self.S + 1] = 0.0
            k += 3 + self.S + 1
        inp[k] = np.tanh(density / 5.0); k += 1
        if self.M:
            inp[k:k + self.M] = a.memory; k += self.M
        return inp

    # ---------------------------------------------------------------- step
    def step(self) -> None:
        self.tick += 1
        self.last_event = self.world.update(self.tick)
        if self.last_event and self.persistence:
            self.persistence.log_event(self.tick, "climate", {"name": self.last_event})

        buckets = self._build_buckets()
        w, h = self.world.w, self.world.h
        cap = self.cfg.max_population
        newborns: list[Agent] = []

        for a in self.agents:
            out = a.genome.forward(self._perceive(a, buckets))

            # movement (sampled from the 9 move logits)
            logits = out[:9]
            p = np.exp(logits - logits.max())
            p /= p.sum()
            mv = int(self.rng.choice(9, p=p))
            dx, dy = MOVE_OFFSETS[mv]
            a.moved = mv != 0
            if a.moved:
                a.x = (a.x + dx) % w
                a.y = (a.y + dy) % h

            # metabolism
            a.energy -= self.cfg.base_metabolism * a.genome.genes["metabolism"]
            if a.moved:
                a.energy -= self.cfg.move_cost

            # eating (automatic: a mouth, not a strategy)
            available = self.world.food[a.y, a.x]
            if available > 0:
                intake = min(available, self.cfg.max_intake)
                self.world.food[a.y, a.x] = available - intake
                a.energy += float(intake) * a.genome.genes["diet_efficiency"] * self.cfg.food_energy
                if a.energy > self.cfg.max_energy:
                    a.energy = self.cfg.max_energy

            # signalling
            if self.S:
                s = _sigmoid(out[10:10 + self.S]).astype(np.float32) * self.cfg.signal_strength
                a.last_signal = s
                cur = self.world.signal[a.y, a.x]
                self.world.signal[a.y, a.x] = np.clip(cur + s, 0.0, 3.0)

            # memory (recurrent)
            if self.M:
                a.memory = np.tanh(out[10 + self.S:10 + self.S + self.M]).astype(np.float32)

            a.age += 1

            # reproduction
            repro_gate = out[9]
            thr = a.genome.genes["repro_threshold"]
            if (len(self.agents) + len(newborns) < cap and _sigmoid(repro_gate) > 0.5
                    and a.energy > thr):
                inv = a.genome.genes["repro_investment"]
                child_energy = a.energy * inv
                a.energy = a.energy * (1 - inv) - self.cfg.reproduce_overhead
                if a.energy > 1.0 and child_energy > 1.0:
                    cdx, cdy = MOVE_OFFSETS[int(self.rng.integers(1, 9))]
                    child = Agent(
                        self.next_id, a.genome.child(self.rng, self.cfg.weight_mutation_scale),
                        (a.x + cdx) % w, (a.y + cdy) % h, child_energy,
                        generation=a.generation + 1, parent_id=a.id,
                        birth_tick=self.tick, mem=self.M, sig=self.S)
                    self.next_id += 1
                    newborns.append(child)

        # integrate births
        for c in newborns:
            self.agents.append(c)
            self.births_total += 1
            self._births_interval += 1
            if self.persistence:
                self.persistence.log_birth(self._birth_row(c))

        # deaths
        survivors: list[Agent] = []
        for a in self.agents:
            if a.energy <= 0.0 or a.age >= a.genome.genes["max_age"]:
                self.deaths_total += 1
                self._deaths_interval += 1
                starved = a.energy <= 0.0
                if starved:
                    self._deaths_starve += 1
                else:
                    self._deaths_age += 1
                if self.persistence:
                    self.persistence.log_death(a.id, self.tick, a.age, a.generation,
                                               a.x, a.y, "hambre" if starved else "vejez")
            else:
                survivors.append(a)
        self.agents = survivors

        # abiogenesis / migration: never let a persistent world go fully dark
        if self.cfg.min_population > 0 and len(self.agents) < self.cfg.min_population:
            need = self.cfg.min_population - len(self.agents)
            for _ in range(need):
                x = int(self.rng.integers(0, self.world.w))
                y = int(self.rng.integers(0, self.world.h))
                a = Agent(self.next_id, self._new_genome(), x, y, self.cfg.initial_energy,
                          generation=0, parent_id=0, birth_tick=self.tick, mem=self.M, sig=self.S)
                self.next_id += 1
                self.agents.append(a)
                self.births_total += 1
                self._births_interval += 1
                if self.persistence:
                    self.persistence.log_birth(self._birth_row(a))
            if self.persistence:
                self.persistence.log_event(self.tick, "genesis", {"count": need})

        # periodic bookkeeping
        if self.persistence and self.tick % self.cfg.stats_every == 0:
            self.persistence.log_stats(self.stats_row())
            self._births_interval = 0
            self._deaths_interval = 0
            self._deaths_starve = 0
            self._deaths_age = 0

    # ---------------------------------------------------------------- rows
    def _birth_row(self, a: Agent) -> dict[str, Any]:
        return {
            "sim_id": self.id, "agent_id": a.id, "parent_id": a.parent_id,
            "generation": a.generation, "birth_tick": a.birth_tick,
            "birth_x": a.x, "birth_y": a.y,
            "genes": {k: round(float(v), 4) for k, v in a.genome.genes.items()},
        }

    def stats_row(self) -> dict[str, Any]:
        n = len(self.agents)
        if n:
            energy = float(np.mean([a.energy for a in self.agents]))
            age = float(np.mean([a.age for a in self.agents]))
            gen = float(np.mean([a.generation for a in self.agents]))
            max_gen = max(a.generation for a in self.agents)
            gene_means = {g: round(float(np.mean([a.genome.genes[g] for a in self.agents])), 4)
                          for g in GENE_BOUNDS}
        else:
            energy = age = gen = 0.0
            max_gen = 0
            gene_means = {g: 0.0 for g in GENE_BOUNDS}
        sig_act = float(np.mean(np.abs(self.world.signal))) if self.S else 0.0
        return {
            "sim_id": self.id, "tick": self.tick, "population": n,
            "births": self._births_interval, "deaths": self._deaths_interval,
            "avg_energy": round(energy, 3), "avg_age": round(age, 2),
            "avg_generation": round(gen, 3), "max_generation": int(max_gen),
            "deaths_starve": self._deaths_starve, "deaths_age": self._deaths_age,
            "signal_activity": round(sig_act, 5),
            "food_total": round(float(self.world.food.sum()), 2),
            "event": self.world.event_name,
            "gene_means": gene_means,
        }

    # ---------------------------------------------------------------- render
    def render_state(self, grid_w: int = 96, grid_h: int = 72) -> dict[str, Any]:
        agents = []
        for a in self.agents:
            agents.append([
                int(a.x), int(a.y),
                round(float(a.genome.genes["hue"]), 3),
                round(float(min(1.0, a.energy / 120.0)), 3),
                int(a.generation),
            ])
        return {
            "tick": self.tick,
            "width": self.world.w, "height": self.world.h,
            "food": self.world.food_downsampled(grid_w, grid_h),
            "agents": agents,
            "stats": self.stats_row(),
        }

    def agent_detail(self, aid: int) -> Optional[dict[str, Any]]:
        for a in self.agents:
            if a.id == aid:
                return {
                    "id": int(a.id), "parent_id": int(a.parent_id), "generation": int(a.generation),
                    "age": int(a.age), "energy": round(float(a.energy), 2),
                    "x": int(a.x), "y": int(a.y), "birth_tick": int(a.birth_tick),
                    "genes": {k: round(float(v), 4) for k, v in a.genome.genes.items()},
                    "last_signal": [round(float(s), 3) for s in a.last_signal],
                }
        return None

    # ---------------------------------------------------------------- snapshot
    def to_snapshot(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "next_id": self.next_id,
            "seed": self.seed,
            "rng_state": self.rng.bit_generator.state,
            "births_total": self.births_total,
            "deaths_total": self.deaths_total,
            "world": self.world.to_state(),
            "agents": [
                {
                    "id": a.id, "x": a.x, "y": a.y, "energy": a.energy, "age": a.age,
                    "generation": a.generation, "parent_id": a.parent_id,
                    "birth_tick": a.birth_tick,
                    "memory": a.memory, "last_signal": a.last_signal,
                    "genome": a.genome.to_state(),
                }
                for a in self.agents
            ],
        }

    def load_snapshot(self, s: dict[str, Any]) -> None:
        self.tick = s["tick"]
        self.next_id = s["next_id"]
        self.seed = s.get("seed", self.seed)
        try:
            self.rng.bit_generator.state = s["rng_state"]
        except Exception:
            pass
        self.births_total = s.get("births_total", 0)
        self.deaths_total = s.get("deaths_total", 0)
        self.world.load_state(s["world"])
        self.agents = []
        for d in s["agents"]:
            a = Agent(d["id"], Genome.from_state(d["genome"]), d["x"], d["y"],
                      d["energy"], d["generation"], d["parent_id"], d["birth_tick"],
                      self.M, self.S)
            a.age = d["age"]
            a.memory = np.asarray(d["memory"], dtype=np.float32)
            a.last_signal = np.asarray(d["last_signal"], dtype=np.float32)
            self.agents.append(a)
