"""The step loop for a living planet.

Perceive → decide (brain) → move / rest / eat / attack / signal / reproduce →
learn from the outcome → age → maybe die. Every complex phenomenon the observer
might see (herds, territories, calls that mean something, predator/prey cycles,
cultures) has to emerge from exactly this — nothing above is written down.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .agent import Agent
from .genome import Genome, GENE_BOUNDS
from .milestones import MilestoneTracker
from .species import SpeciesRegistry
from .world import World

MOVE = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class Simulation:
    def __init__(self, sim_id: str, cfg, persistence=None, populate: bool = True):
        self.id = sim_id
        self.cfg = cfg
        self.persistence = persistence
        self.seed = cfg.resolved_seed()
        self.rng = np.random.default_rng(self.seed)

        self.world = World(cfg, self.rng)
        self.species = SpeciesRegistry(cfg.species_threshold, self.rng)
        self.milestones = MilestoneTracker()

        self.S = max(0, cfg.sound_channels)
        self.P = max(0, cfg.pheromone_channels)
        self.C = max(0, cfg.color_channels)
        self.M = max(0, cfg.memory_size)
        self.n_in = 30 + 3 * self.S + self.P + self.C + self.M
        self.n_out = 12 + self.S + self.P + self.M

        self.tick = 0
        self.next_id = 1
        self.agents: list[Agent] = []

        self.births_total = 0
        self.deaths_total = 0
        self._bi = 0
        self._di = 0
        self._di_starve = self._di_pred = self._di_age = self._di_disaster = 0
        self._predations = 0
        self.last_events: list[str] = []
        self._pred_victims: set[int] = set()

        if populate:
            self._populate()

    # ---------------------------------------------------------------- populate
    def _new_genome(self):
        return Genome.random(self.n_in, self.cfg.brain_hidden, self.n_out,
                             self.C, self.rng, self.cfg.initial_mutation_rate)

    def _populate(self):
        founders = []
        for _ in range(max(1, self.cfg.founder_species)):
            g = self._new_genome()
            g.genes["diet"] = float(self.rng.uniform(0.0, self.cfg.founder_diet_max))
            founders.append((g, self.species.found(g, 0)))
        for _ in range(self.cfg.initial_population):
            g, sid = founders[int(self.rng.integers(0, len(founders)))]
            child = g.child(self.rng, self.cfg.weight_mutation_scale)
            x, y = self.world.terrain.random_fertile_cell(self.rng)
            a = Agent(self.next_id, child, x, y, self.cfg.initial_energy, 0, 0, 0,
                      self.cfg, species_id=sid)
            self.next_id += 1
            self.agents.append(a)
            if self.persistence:
                self.persistence.log_birth(self._birth_row(a))
        self.species.update(self.agents, 0)

    # ---------------------------------------------------------------- indexing
    def _buckets(self):
        b: dict[tuple[int, int], list[int]] = {}
        for i, a in enumerate(self.agents):
            b.setdefault((a.x, a.y), []).append(i)
        return b

    # ---------------------------------------------------------------- perceive
    def _perceive(self, a: Agent, buckets, light):
        w, h = self.world.w, self.world.h
        veg, meat = self.world.veg, self.world.meat
        snd, pher = self.world.sound, self.world.pher
        elev = self.world.terrain.elevation
        slope = self.world.terrain.slope
        r = self.cfg.perception_radius
        vis = a.genome.genes["vision"]
        see = 0.4 + 0.6 * light        # night dims distance perception

        inp = np.empty(self.n_in, dtype=np.float32)
        k = 0
        inp[k] = np.tanh(a.energy / 60.0); k += 1
        inp[k] = min(1.0, a.age / max(1.0, a.genome.genes["max_age"])); k += 1
        inp[k] = light; k += 1
        inp[k] = elev[a.y, a.x]; k += 1
        inp[k] = slope[a.y, a.x]; k += 1
        inp[k] = veg[a.y, a.x] / (self.cfg.veg_capacity or 1); k += 1
        for dx, dy in N8:
            inp[k] = veg[(a.y + dy) % h, (a.x + dx) % w] / (self.cfg.veg_capacity or 1) * see; k += 1
        inp[k] = min(1.0, meat[a.y, a.x]); k += 1
        if self.S:
            inp[k:k + self.S] = snd[a.y, a.x]; k += self.S
            acc = np.zeros(self.S, np.float32)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    acc += snd[(a.y + dy) % h, (a.x + dx) % w]
            inp[k:k + self.S] = acc / 9.0; k += self.S
        if self.P:
            inp[k:k + self.P] = pher[a.y, a.x]; k += self.P

        # nearest other agent + density
        best, best_d2, density = None, None, 0
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                occ = buckets.get(((a.x + dx) % w, (a.y + dy) % h))
                if not occ:
                    continue
                for j in occ:
                    o = self.agents[j]
                    if o.id == a.id:
                        continue
                    density += 1
                    d2 = dx * dx + dy * dy
                    if best_d2 is None or d2 < best_d2:
                        best_d2, best = d2, (o, dx, dy)
        a_density = density
        if best is not None:
            o, dx, dy = best
            inp[k] = dx / r * see; inp[k + 1] = dy / r * see
            inp[k + 2] = (1 - min(1, best_d2 ** 0.5 / r)) * see; k += 3
            if self.C:
                inp[k:k + self.C] = o.genome.color * see; k += self.C
            inp[k] = o.genome.genes["diet"]; k += 1
            inp[k] = (o.genome.genes["size"] - 0.6) / 1.0; k += 1
            inp[k] = np.tanh(a.memory.feeling(o.id)); k += 1
            if self.S:
                inp[k:k + self.S] = o.genome.color[:self.S] * 0 + snd[o.y, o.x]; k += self.S
        else:
            inp[k:k + 3 + self.C + 3 + self.S] = 0.0
            k += 3 + self.C + 3 + self.S
        inp[k] = np.tanh(a_density / 5.0); k += 1

        noise = max(0.0, 1.35 - vis) * 0.25
        fdx, fdy, fs = a.memory.recall(a.x, a.y, True, noise, self.rng)
        inp[k] = fdx; inp[k + 1] = fdy; inp[k + 2] = fs; k += 3
        ddx, ddy, ds = a.memory.recall(a.x, a.y, False, noise, self.rng)
        inp[k] = ddx; inp[k + 1] = ddy; inp[k + 2] = ds; k += 3
        inp[k] = np.tanh(a.inv_food); k += 1
        inp[k] = a.genome.genes["diet"]; k += 1
        if self.M:
            inp[k:k + self.M] = a.mem_vec; k += self.M
        return inp, a_density

    # ---------------------------------------------------------------- step
    def step(self):
        self.tick += 1
        t = self.tick
        self._pred_victims = set()
        self.last_events = self.world.update(t)
        for ev in self.last_events:
            self._log_event("desastre", {"name": ev})
            fk = {"incendio": "first_fire", "inundación": "first_flood",
                  "terremoto": "first_quake"}.get(ev)
            if fk:
                self._milestone(fk, {"name": ev})

        light = self.world.light(t)
        buckets = self._buckets()
        w, h = self.world.w, self.world.h
        cap = self.cfg.max_population
        newborns: list[Agent] = []
        max_density = 0
        learners = 0

        for a in self.agents:
            a.prev_energy = a.energy
            x_in, dens = self._perceive(a, buckets, light)
            max_density = max(max_density, dens)
            out = a.think(x_in)

            # --- movement (curiosity mixes in exploration) ---
            logits = out[:9]
            p = np.exp(logits - logits.max()); p /= p.sum()
            e = a.genome.genes["explore_bias"] * 0.5
            p = (1 - e) * p + e / 9.0
            resting = _sig(out[9]) > 0.6
            a.resting = resting
            a.moved = False
            if not resting:
                mv = int(self.rng.choice(9, p=p))
                a.moved = self._try_move(a, mv)
                if a.moved and self.rng.random() < a.genome.genes["speed"]:
                    self._try_move(a, mv)  # a faster stride

            # --- metabolism ---
            g = a.genome.genes
            cost = self.cfg.base_metabolism * g["metabolism"] * (0.6 + 0.4 * g["size"])
            if resting:
                cost *= (1.0 - self.cfg.rest_recovery)
            if a.moved:
                cost += self.cfg.move_cost * (1.0 + self.cfg.slope_cost *
                                              float(self.world.terrain.slope[a.y, a.x]))
            a.energy -= cost

            self._eat(a, g)
            self._maybe_attack(a, out, buckets, g)
            self._emit(a, out)

            # --- reproduction ---
            if (len(self.agents) + len(newborns) < cap and _sig(out[11]) > 0.5
                    and a.energy > g["repro_threshold"]):
                child = self._reproduce(a, g)
                if child is not None:
                    newborns.append(child)

            # --- recurrent memory ---
            base = 12 + self.S + self.P
            if self.M:
                a.mem_vec = np.tanh(out[base:base + self.M]).astype(np.float32)

            a.age += 1

            # --- learn + remember from the outcome ---
            reward = a.energy - a.prev_energy
            lr = self.cfg.lifetime_learning
            a.learn(reward, lr, self.cfg.plasticity_decay)
            if lr > 0 and abs(reward) > 2:
                learners += 1
            a.memory.note_place(a.x, a.y, reward * 0.4)
            a.memory.decay()

            # --- migration milestone ---
            if a.age > 300:
                dx = (a.x - a.birth_x + w / 2) % w - w / 2
                dy = (a.y - a.birth_y + h / 2) % h - h / 2
                if (dx * dx + dy * dy) ** 0.5 > 0.35 * min(w, h):
                    self._milestone("first_migration", {"agent": a.id})

        # integrate newborns
        for c in newborns:
            self.agents.append(c)
            self.births_total += 1
            self._bi += 1
            if self.persistence:
                self.persistence.log_birth(self._birth_row(c))

        # deaths (starvation, age, fire, flood)
        self._process_deaths()

        # abiogenesis floor
        if self.cfg.min_population > 0 and len(self.agents) < self.cfg.min_population:
            self._reseed(self.cfg.min_population - len(self.agents))

        # milestones from population-level signals
        if max_density >= 8:
            self._milestone("first_community", {"size": int(max_density)})
        if learners >= 5:
            self._milestone("first_learning", {})
        if self.S and float(np.mean(np.abs(self.world.sound))) > 0.04:
            self._milestone("first_signal", {})

        # species bookkeeping + extinction events
        if t % 20 == 0:
            for ev in self.species.update(self.agents, t):
                self._log_event("hito", ev)
                self._milestone("first_extinction" if ev["kind"] == "extinción"
                                else "first_speciation", ev)
                self.persistence and self.persistence.log_milestone(
                    {"tick": t, "kind": ev["kind"], "label": ev.get("name", ""), "data": ev})

        if t % self.cfg.stats_every == 0:
            if self.persistence:
                self.persistence.log_stats(self.stats_row())
            self._bi = self._di = 0
            self._di_starve = self._di_pred = self._di_age = self._di_disaster = 0

    # ---------------------------------------------------------------- actions
    def _passable(self, x, y):
        return bool(self.world.terrain.passable[y % self.world.h, x % self.world.w])

    def _try_move(self, a, mv):
        dx, dy = MOVE[mv]
        if dx == 0 and dy == 0:
            return False
        nx, ny = (a.x + dx) % self.world.w, (a.y + dy) % self.world.h
        if self._passable(nx, ny):
            a.x, a.y = nx, ny
            return True
        return False

    def _eat(self, a, g):
        cell = (a.y, a.x)
        veg = self.world.veg[cell]
        gained = 0.0
        if veg > 0:
            intake = min(veg, self.cfg.max_intake)
            self.world.veg[cell] = veg - intake
            gained += float(intake) * g["plant_eff"] * self.cfg.food_energy * (1 - 0.7 * g["diet"])
        meat = self.world.meat[cell]
        if meat > 0:
            im = min(meat, self.cfg.max_intake)
            self.world.meat[cell] = meat - im
            mg = float(im) * g["meat_eff"] * self.cfg.meat_energy * (0.3 + 0.7 * g["diet"])
            if mg > 0.1:
                self._milestone("first_scavenge", {"agent": a.id})
            gained += mg
        if gained > 0:
            a.energy += gained
            if a.energy > self.cfg.max_energy:  # surplus is stored (economy substrate)
                a.inv_food = min(50.0, a.inv_food + (a.energy - self.cfg.max_energy))
                a.energy = self.cfg.max_energy
        elif a.inv_food > 0 and a.energy < 0.5 * self.cfg.max_energy:
            take = min(a.inv_food, 3.0)  # draw from stores when hungry
            a.inv_food -= take
            a.energy += take

    def _maybe_attack(self, a, out, buckets, g):
        if _sig(out[10] + g["agg_bias"]) <= 0.5:
            return
        # striking costs energy whether or not it pays off
        a.energy -= self.cfg.attack_cost
        for dx, dy in MOVE[1:] + [(0, 0)]:
            occ = buckets.get(((a.x + dx) % self.world.w, (a.y + dy) % self.world.h))
            if not occ:
                continue
            for j in occ:
                o = self.agents[j]
                if o.id == a.id or o.energy <= 0:
                    continue
                dmg = self.cfg.attack_damage * g["size"] / max(0.6, o.genome.genes["size"])
                o.energy -= dmg
                if o.energy <= 0:
                    self._pred_victims.add(o.id)
                # energy is conserved: the predator recovers only a fraction of the
                # damage as food, and only a carnivorous digestion can do so at all.
                frac = float(np.clip(g["meat_eff"] * max(0.0, g["diet"] - 0.3), 0.0, 0.9))
                a.energy = min(self.cfg.max_energy, a.energy + dmg * frac)
                if o.inv_food > 0:                       # theft
                    a.inv_food = min(50.0, a.inv_food + o.inv_food)
                    o.inv_food = 0.0
                o.memory.note_social(a.id, -1.0)         # the victim remembers
                a.n_attacks += 1
                self._milestone("first_predation", {"attacker": a.id, "victim": o.id})
                return

    def _emit(self, a, out):
        base = 12
        if self.S:
            s = _sig(out[base:base + self.S]).astype(np.float32)
            self.world.sound[a.y, a.x] = np.clip(self.world.sound[a.y, a.x] + s, 0, 4)
            if float(s.max()) > 0.6:
                a.n_sound += 1
        if self.P:
            pb = base + self.S
            pv = _sig(out[pb:pb + self.P]).astype(np.float32)
            self.world.pher[a.y, a.x] = np.clip(self.world.pher[a.y, a.x] + pv, 0, 6)

    def _reproduce(self, a, g):
        inv = g["repro_investment"]
        ce = a.energy * inv
        a.energy = a.energy * (1 - inv) - self.cfg.reproduce_overhead
        if a.energy <= 1 or ce <= 1:
            return None
        # placement on a passable neighbour
        nbrs = MOVE[1:].copy()
        self.rng.shuffle(nbrs)
        cx = cy = None
        for dx, dy in nbrs:
            nx, ny = (a.x + dx) % self.world.w, (a.y + dy) % self.world.h
            if self._passable(nx, ny):
                cx, cy = nx, ny
                break
        if cx is None:
            cx, cy = a.x, a.y
        cg = a.genome.child(self.rng, self.cfg.weight_mutation_scale)
        sid, spec_ev = self.species.assign_child(cg, a.species_id, self.tick)
        child = Agent(self.next_id, cg, cx, cy, ce, a.generation + 1, a.id, self.tick,
                      self.cfg, species_id=sid)
        self.next_id += 1
        a.n_children += 1
        self._milestone("first_reproduction", {"parent": a.id})
        if spec_ev is not None:
            self._log_event("hito", spec_ev)
            self._milestone("first_speciation", spec_ev)
            self.persistence and self.persistence.log_milestone(
                {"tick": self.tick, "kind": "especiación", "label": spec_ev["name"], "data": spec_ev})
        return child

    # ---------------------------------------------------------------- deaths
    def _process_deaths(self):
        survivors = []
        for a in self.agents:
            cause = None
            if a.energy <= 0:
                if a.id in self._pred_victims:
                    cause = "depredado"; self._di_pred += 1
                else:
                    cause = "hambre"; self._di_starve += 1
            elif a.age >= a.genome.genes["max_age"]:
                cause = "vejez"; self._di_age += 1
            elif self.world.fire[a.y, a.x] > 0.5:
                cause = "fuego"; self._di_disaster += 1
            elif self.world.flood[a.y, a.x] > 0.5 and self.rng.random() < 0.3:
                cause = "ahogo"; self._di_disaster += 1
            if cause is not None:
                # a corpse feeds the ground (scavenging substrate)
                self.world.meat[a.y, a.x] = min(4.0, self.world.meat[a.y, a.x]
                                                + 0.6 * a.genome.genes["size"] + max(0, a.energy) * 0.02)
                self.deaths_total += 1
                self._di += 1
                self._milestone("first_death", {"cause": cause})
                if self.persistence:
                    self.persistence.log_death(a.id, self.tick, a.age, a.generation,
                                               a.x, a.y, cause)
            else:
                survivors.append(a)
        self.agents = survivors

    def _reseed(self, n):
        for _ in range(n):
            g = self._new_genome()
            g.genes["diet"] = float(self.rng.uniform(0.0, self.cfg.founder_diet_max))
            sid = self.species.found(g, self.tick)
            x, y = self.world.terrain.random_fertile_cell(self.rng)
            a = Agent(self.next_id, g, x, y, self.cfg.initial_energy, 0, 0, self.tick, self.cfg, sid)
            self.next_id += 1
            self.agents.append(a)
            self.births_total += 1
            self._bi += 1
            if self.persistence:
                self.persistence.log_birth(self._birth_row(a))
        self._log_event("génesis", {"count": n})

    # ---------------------------------------------------------------- logging
    def _log_event(self, type_, data):
        if self.persistence:
            self.persistence.log_event(self.tick, type_, data)

    def _milestone(self, kind, data):
        ms = self.milestones.first(kind, self.tick, data)
        if ms and self.persistence:
            self.persistence.log_milestone(ms)

    # ---------------------------------------------------------------- rows
    def _birth_row(self, a):
        return {"sim_id": self.id, "agent_id": a.id, "parent_id": a.parent_id,
                "generation": a.generation, "species_id": a.species_id,
                "birth_tick": a.birth_tick, "birth_x": a.x, "birth_y": a.y,
                "genes": {k: round(float(v), 4) for k, v in a.genome.genes.items()}}

    def stats_row(self):
        n = len(self.agents)
        if n:
            E = [a.energy for a in self.agents]
            gene_means = {g: round(float(np.mean([a.genome.genes[g] for a in self.agents])), 4)
                          for g in GENE_BOUNDS}
            avg_gen = float(np.mean([a.generation for a in self.agents]))
            max_gen = max(a.generation for a in self.agents)
            diets = np.array([a.genome.genes["diet"] for a in self.agents])
            herb = int((diets < 0.4).sum()); carn = int((diets > 0.6).sum())
        else:
            E = [0]; gene_means = {g: 0.0 for g in GENE_BOUNDS}
            avg_gen = 0.0; max_gen = 0; herb = carn = 0
        return {
            "sim_id": self.id, "tick": self.tick, "population": n,
            "births": self._bi, "deaths": self._di,
            "deaths_starve": self._di_starve, "deaths_pred": self._di_pred,
            "deaths_age": self._di_age, "deaths_disaster": self._di_disaster,
            "avg_energy": round(float(np.mean(E)), 3),
            "avg_generation": round(avg_gen, 3), "max_generation": int(max_gen),
            "species": len(self.species.living()),
            "herbivores": herb, "carnivores": carn,
            "sound_activity": round(float(np.mean(np.abs(self.world.sound))) if self.S else 0.0, 5),
            "pher_activity": round(float(np.mean(np.abs(self.world.pher))) if self.P else 0.0, 5),
            "veg_total": round(float(self.world.veg.sum()), 1),
            "weather": self.world.weather_name, "climate": round(self.world.climate, 4),
            "gene_means": gene_means,
        }

    # ---------------------------------------------------------------- render
    def render_state(self, gw=128, gh=90):
        agents = []
        for a in self.agents:
            col = a.genome.color
            hue = float(col[0]) if len(col) else 0.5
            agents.append([int(a.x), int(a.y), round(hue, 3),
                           round(float(min(1, a.energy / 120.0)), 3),
                           int(a.species_id), round(float(a.genome.genes["diet"]), 2)])
        layers = self.world.render_layers(gw, gh)
        return {
            "tick": self.tick, "width": self.world.w, "height": self.world.h,
            "light": round(self.world.light(self.tick), 3),
            "layers": layers, "agents": agents,
            "species": self.species.living()[:12],
            "stats": self.stats_row(),
        }

    def frame(self, gw=96, gh=68):
        """Compact keyframe for the time machine."""
        layers = self.world.render_layers(gw, gh)
        agents = [[int(a.x), int(a.y), int(a.species_id),
                   round(float(a.genome.genes["diet"]), 2)] for a in self.agents]
        return {"tick": self.tick, "width": self.world.w, "height": self.world.h,
                "layers": layers, "agents": agents, "stats": self.stats_row()}

    def agent_detail(self, aid):
        for a in self.agents:
            if a.id == aid:
                sp = self.species.species.get(a.species_id, {})
                return {"id": int(a.id), "parent_id": int(a.parent_id),
                        "generation": int(a.generation), "species": sp.get("name", "?"),
                        "species_id": int(a.species_id), "age": int(a.age),
                        "energy": round(float(a.energy), 2), "x": int(a.x), "y": int(a.y),
                        "inv_food": round(float(a.inv_food), 2),
                        "attacks": int(a.n_attacks), "children": int(a.n_children),
                        "genes": {k: round(float(v), 4) for k, v in a.genome.genes.items()},
                        "color": [round(float(c), 3) for c in a.genome.color],
                        "known_agents": len(a.memory.social)}
        return None

    # ---------------------------------------------------------------- snapshot
    def to_snapshot(self):
        return {
            "tick": self.tick, "next_id": self.next_id, "seed": self.seed,
            "rng_state": self.rng.bit_generator.state,
            "births_total": self.births_total, "deaths_total": self.deaths_total,
            "world": self.world.to_state(), "species": self.species.to_state(),
            "milestones": self.milestones.to_state(),
            "agents": [a.to_state() for a in self.agents],
        }

    def load_snapshot(self, s):
        self.tick = s["tick"]; self.next_id = s["next_id"]; self.seed = s.get("seed", self.seed)
        try:
            self.rng.bit_generator.state = s["rng_state"]
        except Exception:
            pass
        self.births_total = s.get("births_total", 0)
        self.deaths_total = s.get("deaths_total", 0)
        self.world.load_state(s["world"])
        self.species.load_state(s["species"])
        self.milestones.load_state(s["milestones"])
        self.agents = [Agent.from_state(d, self.cfg) for d in s["agents"]]
