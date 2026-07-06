"""The step loop for an observable, living planet.

Perceive → decide (brain) → move / rest / eat / attack / speak / reproduce →
learn from the outcome → age → maybe die. Every complex phenomenon the observer
might see (herds, territories, calls that mean something, predator/prey cycles,
cultures) has to emerge from exactly this — nothing above is written down.

v3 adds, purely as an *observation layer* on top of the same mechanics: a
discrete 10-symbol spoken channel (meaning never hardcoded, only measured),
explicit interaction events for the chronicle, a per-agent trajectory trail,
and a heuristic "current state" label — all derived from what the agent's
brain already decided, none of it fed back as new behaviour.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import cognition, fitness as fitnessmod, introspect, narrative, personality
from .agent import Agent
from .discoveries import DiscoveryEngine
from .genome import Genome, GENE_BOUNDS
from .interactions import classify_encounter, make_event
from .language import CONTEXTS, LEGEND, N_SYMBOLS, SymbolStats
from .milestones import MilestoneTracker
from .species import SpeciesRegistry
from .world import World

MOVE = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

FOLLOW_STREAK_MILESTONE = 6
SYMBOL_USE_MILESTONE = 60          # same species, same symbol, this many times -> "sustained"


def _sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class Simulation:
    def __init__(self, sim_id: str, cfg, persistence=None, populate: bool = True):
        self.id = sim_id
        self.cfg = cfg
        cfg.apply_cognition_mode()
        self.persistence = persistence
        self.seed = cfg.resolved_seed()
        self.rng = np.random.default_rng(self.seed)

        self.world = World(cfg, self.rng)
        self.species = SpeciesRegistry(cfg.species_threshold, self.rng)
        self.milestones = MilestoneTracker()
        self.symbol_stats = SymbolStats()

        self.S = N_SYMBOLS                      # the spoken language: fixed at 10 digits
        self.P = max(0, cfg.pheromone_channels)
        self.C = max(0, cfg.color_channels)
        self.M = max(0, cfg.memory_size)
        # perceptual base (see _perceive): 16 fixed scalars (energy, age, light,
        # elevation, slope, own vegetation, 8-neighbour vegetation, meat, danger)
        # + nearest-agent block (position=3, diet/size/feeling=3, density=1) +
        # memory recall (food=3, danger=3) + inventory/diet(2) = 31 total, plus
        # the language channel counted three times (own cell, 3x3 neighbourhood
        # average, nearest agent's cell) and pheromone/colour/working-memory once.
        self.BASE_IN = 31
        self.n_in = self.BASE_IN + 3 * self.S + self.P + self.C + self.M
        # outputs: 9 move logits, rest, attack, repro = 12; 10 symbol logits + speak
        # gate = 11; then P pheromone + M memory
        self.OUT_MOVE = 0
        self.OUT_REST = 9
        self.OUT_ATTACK = 10
        self.OUT_REPRO = 11
        self.OUT_SYMBOL = 12                    # 12..12+S-1
        self.OUT_SPEAK = 12 + self.S
        self.OUT_PHER = self.OUT_SPEAK + 1
        self.OUT_MEM = self.OUT_PHER + self.P
        self.n_out = self.OUT_MEM + self.M

        self.tick = 0
        self.next_id = 1
        self.agents: list[Agent] = []
        self.recent_interactions: list[dict] = []   # fast in-memory ring for the API/UI

        self.births_total = 0
        self.deaths_total = 0
        self._bi = 0
        self._di = 0
        self._di_starve = self._di_pred = self._di_age = self._di_disaster = 0
        self.deaths_starve_total = self.deaths_pred_total = 0
        self.deaths_age_total = self.deaths_disaster_total = 0
        self._interactions_interval = 0
        self.interactions_total = 0
        self.last_events: list[str] = []
        self._pred_victims: set[int] = set()
        self._species_symbol_seen: set[tuple[int, int]] = set()
        self._encounter_cooldown: dict[tuple[int, int], int] = {}
        self._signal_cooldown: dict[tuple[int, int], int] = {}
        self.ENCOUNTER_COOLDOWN = 60   # ticks: an ongoing encounter isn't re-logged every tick
        self.SIGNAL_COOLDOWN = 20

        # research layer: automatic discovery engine + the observer's spotlight.
        # spotlight maps agent_id -> expiry_tick; only these (few) agents pay the
        # cost of recording decision traces / activation buffers.
        self.discoveries = DiscoveryEngine()
        self.spotlight: dict[int, int] = {}
        self.SPOTLIGHT_TTL = 300
        self._out_idx = {"REST": self.OUT_REST, "ATTACK": self.OUT_ATTACK,
                         "REPRO": self.OUT_REPRO, "SPEAK": self.OUT_SPEAK}
        self._bucket_map = self._build_bucket_map()
        # named input indices (for plain-language perception readings in traces)
        near = 16 + 2 * self.S + self.P
        density = near + 6 + self.C + self.S
        self._idx = {
            "energy": 0, "veg_here": 5, "danger": 15,
            "lang_own": 16, "lang_avg": 16 + self.S, "pher": 16 + 2 * self.S,
            "near": near, "near_dist": near + 2, "density": density,
            "recall_food": density + 1, "recall_danger": density + 4,
            "inv": density + 7, "diet_self": density + 8,
        }

        if populate:
            self._populate()

    # ---------------------------------------------------------------- labels
    def _build_bucket_map(self) -> list[str]:
        """Semantic category per perception input, in the exact order _perceive
        fills them. Used to explain which *kinds* of input drove a decision."""
        b: list[str] = ["energía", "edad", "luz", "terreno", "terreno", "comida"]
        b += ["comida"] * 8                       # 8-neighbour vegetation
        b += ["carne", "peligro"]
        b += ["mi_voz"] * self.S                   # own cell language
        b += ["voz_oída"] * self.S                 # neighbourhood language
        b += ["feromona"] * self.P
        b += ["vecino", "vecino", "vecino"]        # nearest dx, dy, dist
        b += ["vecino"] * self.C                   # nearest colour
        b += ["vecino", "vecino", "vecino"]        # diet, size, feeling
        b += ["voz_oída"] * self.S                 # nearest agent's language
        b += ["densidad"]
        b += ["memoria", "memoria", "memoria"]     # food recall
        b += ["memoria", "memoria", "memoria"]     # danger recall
        b += ["inventario", "dieta"]
        b += ["memoria_trabajo"] * self.M
        return b

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
    def _perceive(self, a: Agent, buckets, light, danger_field):
        """Builds the input vector and also returns the nearest neighbour
        (snapshotted position, so later mutation this tick can't retroactively
        change what 'a' perceived) — used by the caller for interaction logging,
        earshot checks and the 'following' heuristic.

        Writes directly into a preallocated array (rather than building a Python
        list and converting at the end) — with hundreds of agents per tick, the
        per-call interpreter overhead of list.append/extend dominates, so this
        is the difference between a watchable real-time pace and not.
        """
        w, h = self.world.w, self.world.h
        veg, meat, lang, pher = self.world.veg, self.world.meat, self.world.lang, self.world.pher
        elev, slope = self.world.terrain.elevation, self.world.terrain.slope
        r = self.cfg.perception_radius
        vis = a.genome.genes["vision"]
        see = 0.4 + 0.6 * light
        cap = self.cfg.veg_capacity or 1

        inp = np.empty(self.n_in, dtype=np.float32)
        k = 0
        inp[k] = np.tanh(a.energy / 60.0); k += 1
        inp[k] = min(1.0, a.age / max(1.0, a.genome.genes["max_age"])); k += 1
        inp[k] = light; k += 1
        inp[k] = elev[a.y, a.x]; k += 1
        inp[k] = slope[a.y, a.x]; k += 1
        inp[k] = veg[a.y, a.x] / cap; k += 1
        for dx, dy in N8:
            inp[k] = veg[(a.y + dy) % h, (a.x + dx) % w] / cap * see; k += 1
        inp[k] = min(1.0, meat[a.y, a.x]); k += 1
        inp[k] = float(danger_field[a.y, a.x]); k += 1

        inp[k:k + self.S] = lang[a.y, a.x]; k += self.S
        acc = np.zeros(self.S, np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                acc += lang[(a.y + dy) % h, (a.x + dx) % w]
        inp[k:k + self.S] = acc / 9.0; k += self.S
        if self.P:
            inp[k:k + self.P] = pher[a.y, a.x]; k += self.P

        # nearest other agent + local density
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
                        best_d2, best = d2, o
        nearest_info = None
        if best is not None:
            dx = (best.x - a.x + w / 2) % w - w / 2
            dy = (best.y - a.y + h / 2) % h - h / 2
            inp[k] = dx / r * see; inp[k + 1] = dy / r * see
            inp[k + 2] = (1 - min(1, best_d2 ** 0.5 / r)) * see; k += 3
            if self.C:
                inp[k:k + self.C] = best.genome.color * see; k += self.C
            inp[k] = best.genome.genes["diet"]; k += 1
            inp[k] = (best.genome.genes["size"] - 0.6) / 1.0; k += 1
            inp[k] = float(np.tanh(a.memory.feeling(best.id))); k += 1
            inp[k:k + self.S] = lang[best.y, best.x]; k += self.S
            nearest_info = (best, best.x, best.y, float(best_d2 ** 0.5))
        else:
            inp[k:k + 3 + self.C + 3 + self.S] = 0.0
            k += 3 + self.C + 3 + self.S
        inp[k] = float(np.tanh(density / 5.0)); k += 1

        noise = max(0.0, 1.35 - vis) * 0.25
        fdx, fdy, fs = a.memory.recall(a.x, a.y, True, noise, self.rng)
        inp[k] = fdx; inp[k + 1] = fdy; inp[k + 2] = fs; k += 3
        ddx, ddy, ds = a.memory.recall(a.x, a.y, False, noise, self.rng)
        inp[k] = ddx; inp[k + 1] = ddy; inp[k + 2] = ds; k += 3
        inp[k] = float(np.tanh(a.inv_food)); k += 1
        inp[k] = a.genome.genes["diet"]; k += 1
        if self.M:
            inp[k:k + self.M] = a.mem_vec; k += self.M

        return inp, density, nearest_info

    # ---------------------------------------------------------------- step
    def step(self):
        self.tick += 1
        t = self.tick
        self._pred_victims = set()
        pair_logged: set[tuple[int, int]] = set()
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
        danger_field = np.maximum(self.world.fire, self.world.flood)
        newborns: list[Agent] = []
        max_density = 0
        learners = 0
        tick_interactions: list[dict] = []

        for a in self.agents:
            a.prev_energy = a.energy
            x_in, dens, nearest = self._perceive(a, buckets, light, danger_field)
            max_density = max(max_density, dens)
            out = a.think(x_in)
            g = a.genome.genes

            # --- movement (curiosity mixes in exploration) ---
            logits = out[self.OUT_MOVE:self.OUT_MOVE + 9]
            p = np.exp(logits - logits.max()); p /= p.sum()
            e = g["explore_bias"] * 0.5
            p = (1 - e) * p + e / 9.0
            resting = _sig(out[self.OUT_REST]) > 0.6
            a.resting = resting
            a.moved = False
            mv = 0
            if resting:
                a.n_rests += 1
            else:
                mv = int(self.rng.choice(9, p=p))
                a.moved = self._try_move(a, mv)
                if a.moved and self.rng.random() < g["speed"]:
                    self._try_move(a, mv)
                if a.moved:
                    a.n_moves += 1
            a.push_position(a.x, a.y)
            self.world.heatmap[a.y, a.x] = min(500.0, self.world.heatmap[a.y, a.x] + 1.0)
            if a.mark_territory(w, h) and a.age > 5:
                a.log_event(t, "territorio", "descubrió una región nueva")
            if a.energy > a.peak_energy:
                a.peak_energy = a.energy

            # --- fleeing heuristic (observation-only label, no new behaviour) ---
            fleeing = False
            if nearest is not None:
                nb, nx0, ny0, nd0 = nearest
                if nb.genome.genes["agg_bias"] > 0.3:
                    nd1 = self._toroidal_dist(a.x, a.y, nx0, ny0)
                    fleeing = a.moved and nd1 > nd0

            # --- metabolism ---
            cost = self.cfg.base_metabolism * g["metabolism"] * (0.6 + 0.4 * g["size"])
            if resting:
                cost *= (1.0 - self.cfg.rest_recovery)
            if a.moved:
                cost += self.cfg.move_cost * (1.0 + self.cfg.slope_cost *
                                              float(self.world.terrain.slope[a.y, a.x]))
            a.energy -= cost

            self._eat(a, g)
            hit = self._maybe_attack(a, out, buckets, g, danger_field, tick_interactions, pair_logged)
            spoke, symbol = self._speak(a, out, dens, danger_field, resting, hit is not None,
                                        nearest, tick_interactions, pair_logged)

            reproduced = False
            if (len(self.agents) + len(newborns) < cap and _sig(out[self.OUT_REPRO]) > 0.5
                    and a.energy > g["repro_threshold"]):
                child = self._reproduce(a, g, tick_interactions)
                if child is not None:
                    newborns.append(child)
                    reproduced = True

            # --- encounter logging + following heuristic ---
            if nearest is not None:
                nb, nx0, ny0, nd0 = nearest
                pair = (min(a.id, nb.id), max(a.id, nb.id))
                last_logged = self._encounter_cooldown.get(pair, -10**9)
                if nd0 <= 1.5 and pair not in pair_logged and t - last_logged >= self.ENCOUNTER_COOLDOWN:
                    kind = classify_encounter(g["diet"], nb.genome.genes["diet"],
                                              g["agg_bias"], nb.genome.genes["agg_bias"])
                    ev = make_event(t, a.id, nb.id, kind, None, "convivencia",
                                    0.0, (a.x, a.y))
                    self._push_interaction(ev, a, nb, tick_interactions)
                    pair_logged.add(pair)
                    self._encounter_cooldown[pair] = t
                    if kind == "cooperación":
                        a.n_coop += 1
                        nb.n_coop += 1
                        a.memory.note_social(nb.id, "pos", t)
                        nb.memory.note_social(a.id, "pos", t)
                        a.log_event(t, "cooperación", f"convivió con #{nb.id}")
                        self._milestone("first_cooperation", {"a": a.id, "b": nb.id})
                if a.follow_target == nb.id:
                    a.follow_streak += 1
                else:
                    a.follow_target = nb.id
                    a.follow_streak = 1
                if a.follow_streak == FOLLOW_STREAK_MILESTONE:
                    a.n_follow += 1
                    nb.n_followed += 1
                    a.memory.note_social(nb.id, "pos", t)
                    a.log_event(t, "seguimiento", f"siguió a #{nb.id}")
                    nb.log_event(t, "seguido", f"fue seguido por #{a.id}")
                    ev = make_event(t, a.id, nb.id, "seguimiento", None,
                                    "asociación sostenida", 0.0, (a.x, a.y))
                    self._push_interaction(ev, a, nb, tick_interactions)
                    self._milestone("first_following", {"a": a.id, "b": nb.id})
            else:
                a.follow_target = 0
                a.follow_streak = 0

            # --- recurrent memory ---
            if self.M:
                a.mem_vec = np.tanh(out[self.OUT_MEM:self.OUT_MEM + self.M]).astype(np.float32)

            a.age += 1

            # --- learn + remember from the outcome ---
            reward = a.energy - a.prev_energy
            lr = self.cfg.lifetime_learning
            a.learn(reward, lr, self.cfg.plasticity_decay)
            if lr > 0 and abs(reward) > 2:
                learners += 1
            a.memory.note_place(a.x, a.y, reward * 0.4, t)
            a.memory.decay()

            # --- state label (observer's classification, not a new behaviour) ---
            a.state = self._label_state(a, resting, reproduced, hit, fleeing, dens)

            # --- expensive introspection: only for spotlighted (focused) agents ---
            if a.id in self.spotlight:
                if reproduced:
                    action_code = 2
                elif hit is not None:
                    action_code = 1
                elif resting:
                    action_code = 0
                elif spoke:
                    action_code = 3
                else:
                    action_code = 4
                conf = introspect.move_confidence(out)
                a.record_decision(x_in, action_code, conf, reward)

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

        self._process_deaths()

        if self.cfg.min_population > 0 and len(self.agents) < self.cfg.min_population:
            self._reseed(self.cfg.min_population - len(self.agents))

        if max_density >= 8:
            self._milestone("first_community", {"size": int(max_density)})
        if learners >= 5:
            self._milestone("first_learning", {})
        if float(np.mean(np.abs(self.world.lang))) > 0.04:
            self._milestone("first_symbol_use", {})

        if t % 4000 == 0:
            self._encounter_cooldown = {k: v for k, v in self._encounter_cooldown.items()
                                        if t - v < self.ENCOUNTER_COOLDOWN * 3}
            self._signal_cooldown = {k: v for k, v in self._signal_cooldown.items()
                                     if t - v < self.SIGNAL_COOLDOWN * 3}

        if t % 20 == 0:
            for ev in self.species.update(self.agents, t):
                self._log_event("hito", ev)
                self._milestone("first_extinction" if ev["kind"] == "extinción"
                                else "first_speciation", ev)
                label = (f"Nueva especie: {ev['name']} (de {ev.get('parent_name', '?')})"
                        if ev["kind"] == "especiación"
                        else f"Extinción: {ev['name']} (llegó a {ev.get('peak_pop', 0)} individuos)")
                self.persistence and self.persistence.log_milestone(
                    {"tick": t, "kind": ev["kind"], "label": label, "data": ev})
            self._check_meaning_emergence(t)

        # automatic discoveries (slow cadence, compares time windows)
        for disc in self.discoveries.maybe_run(self):
            self._log_event("descubrimiento", disc)
            if self.persistence:
                self.persistence.log_discovery(disc)

        # expire spotlights so introspection cost stays bounded
        if t % 60 == 0 and self.spotlight:
            expired = [aid for aid, exp in self.spotlight.items() if exp < t]
            for aid in expired:
                del self.spotlight[aid]

        # interaction bookkeeping: bounded in-memory ring + persisted rolling table
        if tick_interactions:
            self.recent_interactions.extend(tick_interactions)
            if len(self.recent_interactions) > 500:
                self.recent_interactions = self.recent_interactions[-500:]
            self._interactions_interval += len(tick_interactions)
            self.interactions_total += len(tick_interactions)
            if self.persistence:
                for ev in tick_interactions:
                    self.persistence.log_interaction(ev)

        if t % self.cfg.stats_every == 0:
            if self.persistence:
                self.persistence.log_stats(self.stats_row())
            self._bi = self._di = 0
            self._di_starve = self._di_pred = self._di_age = self._di_disaster = 0
            self._interactions_interval = 0

    # ---------------------------------------------------------------- helpers
    def _toroidal_dist(self, x0, y0, x1, y1) -> float:
        w, h = self.world.w, self.world.h
        dx = (x1 - x0 + w / 2) % w - w / 2
        dy = (y1 - y0 + h / 2) % h - h / 2
        return float((dx * dx + dy * dy) ** 0.5)

    def _push_interaction(self, ev, a, b, tick_bucket) -> None:
        a.push_interaction(ev)
        if b is not None:
            b.push_interaction(ev)
        tick_bucket.append(ev)

    def _label_state(self, a, resting, reproduced, hit, fleeing, density) -> str:
        if resting:
            return "descansando"
        if reproduced:
            return "reproduciéndose"
        if hit is not None:
            return "cazando" if a.genome.genes["diet"] > 0.5 else "interactuando"
        if fleeing:
            return "huyendo"
        if a.follow_streak >= 3:
            return "siguiendo_señal"
        if density >= 2:
            return "interactuando"
        return "explorando" if a.genome.genes["explore_bias"] > 0.5 else "buscando_comida"

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
            if a.energy > self.cfg.max_energy:
                a.inv_food = min(50.0, a.inv_food + (a.energy - self.cfg.max_energy))
                a.energy = self.cfg.max_energy
            if gained > 2.0:   # a meaningful meal, not a nibble
                if a.t_first_food == 0:
                    a.t_first_food = self.tick
                    a.log_event(self.tick, "primera_comida", f"comió por primera vez (+{gained:.0f})")
                else:
                    a.log_event(self.tick, "comió", f"comió (+{gained:.0f} energía)")
        elif a.inv_food > 0 and a.energy < 0.5 * self.cfg.max_energy:
            take = min(a.inv_food, 3.0)
            a.inv_food -= take
            a.energy += take

    def _maybe_attack(self, a, out, buckets, g, danger_field, tick_bucket, pair_logged):
        if _sig(out[self.OUT_ATTACK] + g["agg_bias"]) <= 0.5:
            return None
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
                killed = o.energy <= 0
                if killed:
                    self._pred_victims.add(o.id)
                frac = float(np.clip(g["meat_eff"] * max(0.0, g["diet"] - 0.3), 0.0, 0.9))
                gain = dmg * frac
                a.energy = min(self.cfg.max_energy, a.energy + gain)
                if o.inv_food > 0:
                    a.inv_food = min(50.0, a.inv_food + o.inv_food)
                    o.inv_food = 0.0
                o.memory.note_social(a.id, "neg", self.tick)
                # combat bookkeeping (winner = attacker; loser = defender)
                a.n_attacks += 1
                a.atk_won += 1
                a.dmg_dealt += dmg
                a.energy_from_atk += gain
                if killed:
                    a.kills += 1
                if a.t_first_attack == 0:
                    a.t_first_attack = self.tick
                o.atk_lost += 1
                o.dmg_received += dmg
                o.wounds += 1
                a.log_event(self.tick, "atacó",
                            f"atacó a #{o.id}" + (" (lo mató)" if killed else f" (-{dmg:.0f})"))
                o.log_event(self.tick, "fue_atacado",
                            f"fue atacado por #{a.id} (-{dmg:.0f})")
                self._milestone("first_predation", {"attacker": a.id, "victim": o.id})
                ev = make_event(self.tick, a.id, o.id, "ataque", None,
                               "muerte" if killed else "herida", -dmg, (a.x, a.y))
                self._push_interaction(ev, a, o, tick_bucket)
                pair_logged.add((min(a.id, o.id), max(a.id, o.id)))
                return ev
        return None

    def _speak(self, a, out, density, danger_field, resting, attacking, nearest,
               tick_bucket, pair_logged):
        symbol_logits = out[self.OUT_SYMBOL:self.OUT_SYMBOL + self.S]
        speak = _sig(out[self.OUT_SPEAK]) > 0.5
        pb = self.OUT_SPEAK + 1
        if self.P:
            pv = _sig(out[pb:pb + self.P]).astype(np.float32)
            self.world.pher[a.y, a.x] = np.clip(self.world.pher[a.y, a.x] + pv, 0, 6)
        if not speak:
            return False, None

        p = np.exp(symbol_logits - symbol_logits.max()); p /= p.sum()
        symbol = int(self.rng.choice(self.S, p=p))
        self.world.lang[a.y, a.x, symbol] = min(6.0, self.world.lang[a.y, a.x, symbol] + 1.0)
        a.push_symbol(self.tick, symbol)
        a.n_sound += 1
        a.sym_counts[symbol] += 1
        if a.t_first_signal == 0:
            a.t_first_signal = self.tick

        context = {
            "food_near": bool(self.world.veg[a.y, a.x] > 0.4),
            "danger_near": bool(danger_field[a.y, a.x] > 0.1),
            "agent_near": density > 0,
            "low_energy": a.energy < 0.35 * self.cfg.max_energy,
            "resting": resting,
            "attacking": attacking,
        }
        self.symbol_stats.record(a.species_id, symbol, context)
        key = (a.species_id, symbol)
        if key not in self._species_symbol_seen:
            tot = self.symbol_stats.totals.get(a.species_id)
            if tot is not None and tot[symbol] >= SYMBOL_USE_MILESTONE:
                self._species_symbol_seen.add(key)

        if nearest is not None and density > 0:
            nb, nx0, ny0, nd0 = nearest
            if nd0 <= self.cfg.perception_radius:
                pair = (min(a.id, nb.id), max(a.id, nb.id))
                last_logged = self._signal_cooldown.get(pair, -10**9)
                if pair not in pair_logged and self.tick - last_logged >= self.SIGNAL_COOLDOWN:
                    ev = make_event(self.tick, a.id, nb.id, "señal", symbol,
                                    LEGEND.get(symbol, str(symbol)), 0.0, (a.x, a.y))
                    self._push_interaction(ev, a, nb, tick_bucket)
                    pair_logged.add(pair)
                    self._signal_cooldown[pair] = self.tick
                    a.log_event(self.tick, "emitió_señal", f"emitió señal [{symbol}] {LEGEND[symbol]}")
                    nb.log_event(self.tick, "escuchó_señal", f"escuchó señal [{symbol}] de #{a.id}")
        return True, symbol

    def _check_meaning_emergence(self, tick: int) -> None:
        for sid in list(self.symbol_stats.totals.keys()):
            prof = self.symbol_stats.species_profile(sid)
            if prof["associations"]:
                self._milestone("first_meaning", {"species": sid, "associations": prof["associations"]})
                return

    def _reproduce(self, a, g, tick_bucket):
        inv = g["repro_investment"]
        ce = a.energy * inv
        a.energy = a.energy * (1 - inv) - self.cfg.reproduce_overhead
        if a.energy <= 1 or ce <= 1:
            return None
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
        if a.t_first_repro == 0:
            a.t_first_repro = self.tick
        a.log_event(self.tick, "reproducción", f"tuvo un descendiente (#{child.id})")
        self._milestone("first_reproduction", {"parent": a.id})
        ev = make_event(self.tick, a.id, child.id, "reproducción", None,
                       "nace un descendiente", -(ce + self.cfg.reproduce_overhead), (a.x, a.y))
        self._push_interaction(ev, a, None, tick_bucket)
        if spec_ev is not None:
            self._log_event("hito", spec_ev)
            self._milestone("first_speciation", spec_ev)
            label = f"Nueva especie: {spec_ev['name']} (de {spec_ev.get('parent_name', '?')})"
            self.persistence and self.persistence.log_milestone(
                {"tick": self.tick, "kind": "especiación", "label": label, "data": spec_ev})
        return child

    # ---------------------------------------------------------------- deaths
    def _process_deaths(self):
        survivors = []
        for a in self.agents:
            cause = None
            if a.energy <= 0:
                if a.id in self._pred_victims:
                    cause = "depredado"; self._di_pred += 1; self.deaths_pred_total += 1
                else:
                    cause = "hambre"; self._di_starve += 1; self.deaths_starve_total += 1
            elif a.age >= a.genome.genes["max_age"]:
                cause = "vejez"; self._di_age += 1; self.deaths_age_total += 1
            elif self.world.fire[a.y, a.x] > 0.5:
                cause = "fuego"; self._di_disaster += 1; self.deaths_disaster_total += 1
            elif self.world.flood[a.y, a.x] > 0.5 and self.rng.random() < 0.3:
                cause = "ahogo"; self._di_disaster += 1; self.deaths_disaster_total += 1
            if cause is not None:
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
            avg_age = float(np.mean([a.age for a in self.agents]))
            gene_vecs = np.array([a.genome.gene_vector() for a in self.agents])
            genetic_diversity = round(float(np.mean(np.std(gene_vecs, axis=0))), 4)
        else:
            E = [0]; gene_means = {g: 0.0 for g in GENE_BOUNDS}
            avg_gen = 0.0; max_gen = 0; herb = carn = 0; avg_age = 0.0; genetic_diversity = 0.0
        return {
            "sim_id": self.id, "tick": self.tick, "population": n,
            "births": self._bi, "deaths": self._di,
            "deaths_starve": self._di_starve, "deaths_pred": self._di_pred,
            "deaths_age": self._di_age, "deaths_disaster": self._di_disaster,
            "avg_energy": round(float(np.mean(E)), 3), "avg_age": round(avg_age, 2),
            "avg_generation": round(avg_gen, 3), "max_generation": int(max_gen),
            "species": len(self.species.living()),
            "herbivores": herb, "carnivores": carn,
            "language_diversity": self.symbol_stats.diversity(),
            "genetic_diversity": genetic_diversity,
            "interactions_interval": self._interactions_interval,
            "interactions_total": self.interactions_total,
            "deaths_totals": {"hambre": self.deaths_starve_total, "depredado": self.deaths_pred_total,
                             "vejez": self.deaths_age_total, "desastre": self.deaths_disaster_total},
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
                           int(a.species_id), round(float(a.genome.genes["diet"]), 2),
                           int(a.id)])
        layers = self.world.render_layers(gw, gh)
        return {
            "tick": self.tick, "width": self.world.w, "height": self.world.h,
            "light": round(self.world.light(self.tick), 3),
            "layers": layers, "agents": agents,
            "species": self.species.living()[:12],
            "stats": self.stats_row(),
        }

    def frame(self, gw=96, gh=68):
        layers = self.world.render_layers(gw, gh)
        agents = [[int(a.x), int(a.y), int(a.species_id),
                   round(float(a.genome.genes["diet"]), 2)] for a in self.agents]
        return {"tick": self.tick, "width": self.world.w, "height": self.world.h,
                "layers": layers, "agents": agents, "stats": self.stats_row()}

    # ---------------------------------------------------------------- spotlight
    def set_spotlight(self, aid: int) -> None:
        """Mark an agent as focused so it records decision traces / activation
        buffers. Cheap: only these few agents pay the introspection cost."""
        self.spotlight[aid] = self.tick + self.SPOTLIGHT_TTL

    def _find(self, aid):
        for a in self.agents:
            if a.id == aid:
                return a
        return None

    def _live_descendants(self, aid: int):
        child_map: dict[int, list[int]] = {}
        for a in self.agents:
            if a.parent_id:
                child_map.setdefault(a.parent_id, []).append(a.id)
        kids = child_map.get(aid, [])
        grand = sum(len(child_map.get(k, [])) for k in kids)
        return len(kids), grand

    def _avg_age(self) -> float:
        return float(np.mean([a.age for a in self.agents])) if self.agents else 0.0

    # ---------------------------------------------------------------- trace
    def _decision_trace(self, a) -> dict[str, Any]:
        if a.last_input is None:
            return {"available": False,
                    "note": "Selecciona/sigue al agente unos segundos para capturar sus decisiones."}
        x = a.last_input
        readings = []
        e_norm = float(x[self._idx["energy"]])
        readings.append(("Energía", "baja" if e_norm < 0.3 else "alta" if e_norm > 0.7 else "media"))
        veg = float(x[self._idx["veg_here"]]) + float(np.sum(x[6:14]))
        if veg > 0.3:
            readings.append(("Comida", "la ve cerca"))
        if float(x[self._idx["danger"]]) > 0.1:
            readings.append(("Peligro", "lo percibe"))
        if float(np.sum(x[self._idx["lang_avg"]:self._idx["lang_avg"] + self.S])) > 0.1:
            readings.append(("Señales", "escucha voces cercanas"))
        if float(x[self._idx["near_dist"]]) > 0.2:
            readings.append(("Vecino", "hay alguien cerca"))
        if float(x[self._idx["recall_food"] + 2]) > 0.2:
            readings.append(("Memoria", "recuerda comida en otra parte"))
        return {
            "available": True,
            "readings": [{"label": k, "value": v} for k, v in readings],
            "salient_inputs": introspect.salient_inputs(x, a.genome.w1, self._bucket_map),
            "top_neurons": introspect.top_neurons(a.last_h),
            "goals": introspect.inferred_goals(a.last_out, a.genome.genes, self._out_idx, self.S),
            "confidence": a.last_confidence,
            "state": a.state,
        }

    def _timeline(self, a) -> list[dict[str, Any]]:
        marks = [{"tick": int(a.birth_tick), "label": "Nacimiento"}]
        for t, lbl in ((a.t_first_food, "Primera comida"), (a.t_first_signal, "Primera señal"),
                       (a.t_first_attack, "Primer ataque"), (a.t_first_repro, "Primera reproducción")):
            if t:
                marks.append({"tick": int(t), "label": lbl})
        marks.sort(key=lambda m: m["tick"])
        return marks

    def agent_detail(self, aid, full: bool = True):
        a = self._find(aid)
        if a is None:
            return None
        if full:
            self.set_spotlight(aid)
        sp = self.species.species.get(a.species_id, {})
        children_alive, grandchildren = self._live_descendants(aid)
        prof = personality.profile(a)
        fit = fitnessmod.compute(a, descendants=children_alive, grandchildren=grandchildren)
        detail = {
            "id": int(a.id), "parent_id": int(a.parent_id),
            "generation": int(a.generation), "species": sp.get("name", "?"),
            "species_id": int(a.species_id), "age": int(a.age),
            "energy": round(float(a.energy), 2), "peak_energy": round(float(a.peak_energy), 1),
            "x": int(a.x), "y": int(a.y), "state": a.state,
            "inv_food": round(float(a.inv_food), 2),
            "attacks": int(a.n_attacks), "children": int(a.n_children),
            "genes": {k: round(float(v), 4) for k, v in a.genome.genes.items()},
            "color": [round(float(c), 3) for c in a.genome.color],
            "known_agents": len(a.memory.social),
            "trajectory": [[int(px), int(py)] for px, py in a.trajectory],
            "last_interactions": a.last_interactions[-a.interact_cap:],
            "last_symbols": [{"tick": int(tt), "symbol": int(ss), "label": LEGEND.get(ss, str(ss))}
                             for tt, ss in a.last_symbols],
            "perception_radius": self.cfg.perception_radius,
            # --- research layer ---
            "personality": prof,
            "fitness": fit,
            "combat": {
                "made": int(a.n_attacks), "won": int(a.atk_won), "lost": int(a.atk_lost),
                "avg_damage": round(a.dmg_dealt / max(1, a.atk_won), 1),
                "energy_gained": round(float(a.energy_from_atk), 1),
                "wounds_received": int(a.wounds), "damage_received": round(float(a.dmg_received), 1),
                "kills": int(a.kills),
            },
            "reproduction": {
                "children": int(a.n_children), "children_alive": children_alive,
                "grandchildren": grandchildren, "note": "reproducción asexual (sin parejas)",
            },
            "memory_stats": a.memory.stats(self.tick),
            "events": list(reversed(a.events[-24:])),
            "timeline": self._timeline(a),
            "symbol_usage": list(a.sym_counts),
        }
        if full:
            detail["decision_trace"] = self._decision_trace(a)
            detail["cognition"] = cognition.compute(a)
            detail["social"] = a.memory.relations(self.tick)
            detail["narrative"] = narrative.summarize(
                sp.get("name", "?"), int(a.age), self._avg_age(), int(a.n_children),
                int(a.n_coop), int(a.n_attacks), a.state,
                personality.dominant_trait(prof), a.sym_counts)
        return detail

    def compare(self, aid_a: int, aid_b: int):
        da = self.agent_detail(aid_a, full=True)
        db = self.agent_detail(aid_b, full=True)
        if da is None or db is None:
            return None
        return {"a": da, "b": db}

    def agent_export(self, aid: int):
        """Complete scientific dump of one individual, including brain weights."""
        a = self._find(aid)
        if a is None:
            return None
        detail = self.agent_detail(aid, full=True)
        gs = a.genome.to_state()
        detail["brain_weights"] = {
            "w1": gs["w1"].tolist(), "b1": gs["b1"].tolist(),
            "w2": gs["w2"].tolist(), "b2": gs["b2"].tolist(),
            "fast_w2": a.fast_w2.tolist(),
        }
        detail["memory_landmarks"] = a.memory.land.tolist()
        detail["all_events"] = a.events
        detail["reward_history"] = a.reward_history
        return detail

    # ---------------------------------------------------------------- snapshot
    def to_snapshot(self):
        return {
            "tick": self.tick, "next_id": self.next_id, "seed": self.seed,
            "rng_state": self.rng.bit_generator.state,
            "births_total": self.births_total, "deaths_total": self.deaths_total,
            "deaths_starve_total": self.deaths_starve_total, "deaths_pred_total": self.deaths_pred_total,
            "deaths_age_total": self.deaths_age_total, "deaths_disaster_total": self.deaths_disaster_total,
            "interactions_total": self.interactions_total,
            "world": self.world.to_state(), "species": self.species.to_state(),
            "milestones": self.milestones.to_state(),
            "symbol_stats": self.symbol_stats.to_state(),
            "discoveries": self.discoveries.to_state(),
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
        self.deaths_starve_total = s.get("deaths_starve_total", 0)
        self.deaths_pred_total = s.get("deaths_pred_total", 0)
        self.deaths_age_total = s.get("deaths_age_total", 0)
        self.deaths_disaster_total = s.get("deaths_disaster_total", 0)
        self.interactions_total = s.get("interactions_total", 0)
        self.world.load_state(s["world"])
        self.species.load_state(s["species"])
        self.milestones.load_state(s["milestones"])
        if "symbol_stats" in s:
            self.symbol_stats.load_state(s["symbol_stats"])
        if "discoveries" in s:
            self.discoveries.load_state(s["discoveries"])
        self.agents = [Agent.from_state(d, self.cfg) for d in s["agents"]]
