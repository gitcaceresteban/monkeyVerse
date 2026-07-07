"""The Simple Island step loop — slow, observable, two-pass.

Each tick: (1) every agent perceives the world *as it was at the start of the
tick* and its recurrent brain produces outputs; (2) everyone moves (bouncing off
water); (3) social outcomes are resolved using everyone's outputs together —
sounds are emitted and heard, interactions succeed only when *mutual*, and A+B
reproduction fires only when both agents want it and a list of real prerequisites
(maturity, energy, affinity, prior interactions, prior signals, cooldown) is met;
(4) rewards are tallied and each brain learns from them.

Sounds carry no built-in meaning. Everything about "who heard what and did what
next" is logged so meaning can be *measured*, never assumed.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from .agent import Agent, crossover_genes, random_genes
from .brain import Brain, reward_learn
from .config import N_SOUNDS
from .island import Island
from .metrics import CommStats, CONTEXTS

# output layout
O_MOVEX, O_MOVEY, O_EAT, O_EXPLORE, O_APPROACH, O_AVOID = 0, 1, 2, 3, 4, 5
O_EMIT, O_RESPOND, O_INTERACT, O_BOND, O_REPRO = 6, 7, 8, 9, 10
O_SOUND0 = 11
N_OUT = O_SOUND0 + N_SOUNDS
RESP_WINDOW = 25   # ticks to watch a hearer's reaction to a sound

# human-readable labels for the debug / "why did it do that" view
IN_LABELS = (["energía", "hambre", "edad", "sexo",
              "comida_dx", "comida_dy", "comida_dist", "veg_aquí",
              "vecino_dx", "vecino_dy", "vecino_dist", "vecino_sexo",
              "vecino_afinidad", "vecino_familiaridad", "densidad"]
             + [f"oyó_{i}" for i in range(N_SOUNDS)]
             + ["última_recompensa", "agua_N", "agua_E", "agua_S", "agua_O"])
OUT_LABELS = (["mover_x", "mover_y", "comer", "explorar", "acercarse", "evitar",
               "emitir", "responder", "interactuar", "vincular", "reproducir"]
              + [f"sonido_{i}" for i in range(N_SOUNDS)])


def _sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class Simulation:
    def __init__(self, sim_id: str, cfg, store=None, populate: bool = True):
        self.id = sim_id
        self.cfg = cfg
        self.store = store
        self.seed = cfg.resolved_seed()
        self.rng = np.random.default_rng(self.seed)
        self.island = Island(cfg, self.rng)
        self.comm = CommStats()

        self.tick = 0
        self.next_id = 1
        self.agents: list[Agent] = []
        self.n_in = self._perceive_len()
        self.n_out = N_OUT

        # counters
        self.births_total = 0
        self.deaths_total = 0
        self.repro_success = 0
        self.repro_attempts = 0
        self.repro_affinity_sum = 0.0
        self.repro_signals_sum = 0.0
        self._interactions_interval = 0
        self._sounds_interval = 0
        self.interactions_total = 0
        self.pop_history: list[int] = []
        self._pending: dict[int, list] = {}         # agent_id -> [pending sound observations]
        self._pending_offspring: list = []          # (parent_ids, child_id, due_tick)

        if populate:
            self._populate()

    # ---------------------------------------------------------------- populate
    def _new_brain(self):
        return Brain.random(self.n_in, self.cfg.hidden_size, self.n_out, self.rng)

    def _spawn(self, sex, generation=0, pa=0, pb=0, brain=None, genes=None, near=None,
               append=True):
        if near is not None:
            x, y = self._place_near(*near)
        else:
            x, y = self.island.random_land_cell()
        a = Agent(self.next_id, sex, x, y, brain or self._new_brain(),
                  genes or random_genes(self.rng), self.cfg, generation, pa, pb, self.tick)
        self.next_id += 1
        if append:
            self.agents.append(a)
        return a

    def _populate(self):
        for _ in range(self.cfg.initial_a):
            self._spawn("A")
        for _ in range(self.cfg.initial_b):
            self._spawn("B")
        for a in self.agents:
            self._log("agent_birth", a.id, None, a.x, a.y,
                      extra={"sex": a.sex, "generation": 0, "genes": {k: round(v, 3) for k, v in a.genes.items()}})

    def _place_near(self, x, y, r=2.0):
        for _ in range(20):
            nx = x + self.rng.uniform(-r, r)
            ny = y + self.rng.uniform(-r, r)
            if self.island.is_land(nx, ny):
                return nx, ny
        return (x, y) if self.island.is_land(x, y) else self.island.random_land_cell()

    # ---------------------------------------------------------------- perceive
    def _perceive_len(self) -> int:
        return 4 + 3 + 1 + 6 + 1 + N_SOUNDS + 1 + 4   # keep in sync with _perceive

    def _perceive(self, a: Agent, snap):
        w = self.island.n
        vals = [
            min(1.0, a.energy / self.cfg.max_energy),
            a.hunger,
            min(1.0, a.age / self.cfg.max_age),
            0.0 if a.sex == "A" else 1.0,
        ]
        food = self.island.nearest_food(a.x, a.y)
        if food:
            vals += [food[0], food[1], min(1.0, food[2] / 10.0)]
        else:
            vals += [0.0, 0.0, 1.0]
        vals.append(self.island.veg_at(a.x, a.y))

        # nearest other agent (from start-of-tick snapshot)
        nb, nd = self._nearest(a, snap)
        if nb is not None:
            dx = (nb.x - a.x); dy = (nb.y - a.y)
            d = max(1e-3, nd)
            r = a.relationship(nb.id)
            vals += [dx / d, dy / d, min(1.0, d / self.cfg.sound_range),
                     0.0 if nb.sex == "A" else 1.0, r.affinity, r.familiarity]
        else:
            vals += [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]

        density = sum(1 for (oid, ox, oy, os) in snap
                      if oid != a.id and (ox - a.x) ** 2 + (oy - a.y) ** 2 <= self.cfg.interaction_radius ** 2)
        vals.append(min(1.0, density / 4.0))

        vals += a.heard_vec.tolist()
        vals.append(float(np.tanh(a.last_reward)))
        # water in 4 directions (learn to avoid the shore)
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            vals.append(0.0 if self.island.is_land(a.x + dx, a.y + dy) else 1.0)
        return np.asarray(vals, dtype=np.float32)

    def _nearest(self, a, snap):
        best = None; best_d = None
        for (oid, ox, oy, os) in snap:
            if oid == a.id:
                continue
            d = math.hypot(ox - a.x, oy - a.y)
            if best_d is None or d < best_d:
                best_d = d; best = oid
        if best is None:
            return None, None
        return self._by_id.get(best), best_d

    # ---------------------------------------------------------------- step
    def step(self):
        self.tick += 1
        t = self.tick
        if t % 3 == 0:
            self.island.regrow()
        self._by_id = {a.id: a for a in self.agents}
        snap = [(a.id, a.x, a.y, a.sex) for a in self.agents]
        rew = {a.id: 0.0 for a in self.agents}
        outs = {}

        # --- pass 1: perceive + decide (no side effects) ---
        for a in self.agents:
            x_in = self._perceive(a, snap)
            out, h = a.brain.step(x_in, a.h, a.fast_wo)
            a.h = h
            a.dbg_in = x_in
            a.dbg_out = out
            outs[a.id] = out
            if _sig(out[O_REPRO]) > 0.5:
                a.repro_desire_tick = t             # courtship intent persists briefly
            rew[a.id] += 0.02                      # small reward just for being alive

        # --- pass 2: move + metabolism + eat ---
        for a in self.agents:
            out = outs[a.id]
            moved = self._move(a, out, snap)
            decay = self.cfg.energy_decay_rate * a.genes["metabolism"]
            if moved:
                decay += self.cfg.move_energy_cost
            a.energy -= decay
            # eating: mostly automatic where there is vegetation nearby, with a
            # learned boost. Grazes the 3×3 neighbourhood so a slow forager beside
            # food still feeds (the island is meant to be forgiving, not lethal).
            if a.energy < self.cfg.max_energy:
                drive = 0.45 + 0.55 * float(_sig(out[O_EAT]))
                got = self.island.graze(a.x, a.y, self.cfg.max_intake * drive,
                                        self.cfg.graze_radius)
                if got > 0.01:
                    gain = got * self.cfg.food_energy_gain
                    a.energy = min(self.cfg.max_energy, a.energy + gain)
                    rew[a.id] += gain * 0.12
                    self._resolve_pending_food(a)
                    if got > 0.1:
                        self._log("agent_eat", a.id, None, a.x, a.y,
                                  e_before=a.energy - gain, e_after=a.energy, result=round(gain, 1))
            if a.energy < self.cfg.starve_energy:
                rew[a.id] -= 0.3

        # --- pass 3: social — sounds, interactions, reproduction ---
        emissions = []                             # (emitter, sound)
        newborns = []
        for a in self.agents:
            out = outs[a.id]
            # emit sound
            if _sig(out[O_EMIT]) > 0.5 and a.energy > self.cfg.sound_energy_cost:
                logits = out[O_SOUND0:O_SOUND0 + N_SOUNDS]
                p = np.exp(logits - logits.max()); p /= p.sum()
                sound = int(self.rng.choice(N_SOUNDS, p=p))
                a.energy -= self.cfg.sound_energy_cost
                a.push_emitted(t, sound)
                self._sounds_interval += 1
                nb, nd = self._nearest_now(a)
                ctx = {
                    "comida_cerca": self.island.veg_at(a.x, a.y) > 0.3 or (self.island.nearest_food(a.x, a.y) or (0, 0, 99))[2] < 3,
                    "agente_cerca": nb is not None and nd <= self.cfg.sound_range,
                    "energia_baja": a.energy < 0.35 * self.cfg.max_energy,
                    "cortejo": _sig(out[O_REPRO]) > 0.5,
                }
                self.comm.record_emit(sound, ctx)
                emissions.append((a, sound))
                self._log("agent_sound_emit", a.id, None, a.x, a.y, sound=sound,
                          extra={"context": {k: bool(v) for k, v in ctx.items()}})

            # mutual social interaction with nearest
            nb, nd = self._nearest_now(a)
            if nb is not None and nd <= self.cfg.interaction_radius:
                self._interact(a, nb, out, outs.get(nb.id), rew, t)

        # distribute sounds to hearers
        for emitter, sound in emissions:
            self._hear(emitter, sound, t)

        # reproduction (needs both parties' outputs + prerequisites)
        for a in self.agents:
            if len(self.agents) + len(newborns) >= self.cfg.max_agents:
                break
            child = self._try_reproduce(a, outs, newborns, rew, t)
            if child:
                newborns.append(child)

        # integrate newborns
        for c in newborns:
            self.agents.append(c)
            self.births_total += 1

        # --- pass 4: learn, age, state, deaths ---
        for a in self.agents:
            a.last_reward = rew.get(a.id, 0.0)
            a.reward_total += a.last_reward
            lr = self.cfg.learning_rate * a.genes["learn_mul"]
            a.fast_wo = reward_learn(a.fast_wo, a.h, a.dbg_out, a.last_reward, lr, self.cfg.plasticity_decay)
            a.age += 1
            if a.repro_cd > 0:
                a.repro_cd -= 1
            a.state = self._state_label(a, outs.get(a.id))
            a.dbg_action = a.state

        self._advance_pending(t)
        self._credit_offspring(t)
        self._process_deaths(t)

        # metrics snapshot + interval reset
        if t % self.cfg.metrics_every == 0:
            self.pop_history.append(len(self.agents))
            if len(self.pop_history) > 400:
                self.pop_history = self.pop_history[-400:]
            if self.store:
                self.store.log_metrics(self.metrics_row())
            self._interactions_interval = 0
            self._sounds_interval = 0

    # ---------------------------------------------------------------- movement
    def _move(self, a, out, snap) -> bool:
        mx = math.tanh(out[O_MOVEX]); my = math.tanh(out[O_MOVEY])
        approach = float(_sig(out[O_APPROACH])); avoid = float(_sig(out[O_AVOID]))
        explore = float(_sig(out[O_EXPLORE]))
        nb, nd = self._nearest(a, snap)
        if nb is not None and nd and nd > 1e-3:
            tx = (nb.x - a.x) / nd; ty = (nb.y - a.y) / nd
            mx += (approach - avoid) * tx
            my += (approach - avoid) * ty
        if explore > 0.4:
            ang = self.rng.uniform(0, 2 * math.pi)
            mx += explore * 0.5 * math.cos(ang); my += explore * 0.5 * math.sin(ang)
        mag = math.hypot(mx, my)
        if mag < 1e-4:
            return False
        step = self.cfg.move_step * a.genes["speed"]
        ux, uy = mx / mag, my / mag
        nx = a.x + ux * step
        ny = a.y + uy * step
        if self.island.is_land(nx, ny):
            a.x, a.y = nx, ny
            return True
        # blocked by water: try each axis alone
        if self.island.is_land(nx, a.y):
            a.x = nx; return True
        if self.island.is_land(a.x, ny):
            a.y = ny; return True
        # deflect: rotate the intended heading and, as a last resort, steer back
        # toward the island centre — this prevents agents getting pinned on the
        # shore and starving next to unreachable food.
        for ang in (0.7, -0.7, 1.4, -1.4, 2.2, -2.2):
            c, s = math.cos(ang), math.sin(ang)
            rx = ux * c - uy * s
            ry = ux * s + uy * c
            tx, ty = a.x + rx * step, a.y + ry * step
            if self.island.is_land(tx, ty):
                a.x, a.y = tx, ty
                return True
        cx = (self.island.n - 1) / 2.0
        tx = a.x + (0.0 if a.x == cx else math.copysign(step, cx - a.x))
        ty = a.y + (0.0 if a.y == cx else math.copysign(step, cx - a.y))
        if self.island.is_land(tx, ty):
            a.x, a.y = tx, ty
            return True
        if self.island.is_land(tx, a.y):
            a.x = tx; return True
        if self.island.is_land(a.x, ty):
            a.y = ty; return True
        return False

    def _nearest_now(self, a):
        best = None; best_d = None
        for o in self.agents:
            if o.id == a.id:
                continue
            d = math.hypot(o.x - a.x, o.y - a.y)
            if best_d is None or d < best_d:
                best_d = d; best = o
        return best, best_d

    # ---------------------------------------------------------------- social
    def _interact(self, a, b, out_a, out_b, rew, t):
        want_a = _sig(out_a[O_INTERACT]) > 0.5
        want_b = out_b is not None and _sig(out_b[O_INTERACT]) > 0.5
        ra = a.relationship(b.id); rb = b.relationship(a.id)
        ra.familiarity = min(1.0, ra.familiarity + 0.02)
        ra.last = t
        if want_a and want_b:
            # mutual, successful interaction
            ra.affinity = min(1.0, ra.affinity + 0.06); ra.pos += 1
            rb.affinity = min(1.0, rb.affinity + 0.06); rb.pos += 1
            rb.familiarity = min(1.0, rb.familiarity + 0.02); rb.last = t
            ra.trust = min(1.0, ra.trust + 0.03); rb.trust = min(1.0, rb.trust + 0.03)
            if _sig(out_a[O_BOND]) > 0.5 and out_b is not None and _sig(out_b[O_BOND]) > 0.5:
                ra.trust = min(1.0, ra.trust + 0.05); rb.trust = min(1.0, rb.trust + 0.05)
            rew[a.id] += 0.5; rew[b.id] = rew.get(b.id, 0.0) + 0.5
            a.fail_streak = 0
            ev = {"tick": t, "type": "interacción", "with": b.id, "result": "mutua"}
            a.push_interaction(ev); b.push_interaction({**ev, "with": a.id})
            self._interactions_interval += 1; self.interactions_total += 1
            self._log("agent_interaction", a.id, b.id, a.x, a.y, result="mutua")
        elif want_a:
            # one-sided attempt
            ra.affinity = max(-1.0, ra.affinity - 0.01); ra.neg += 1
            a.fail_streak += 1
            if a.fail_streak >= 3:
                rew[a.id] -= 0.2
            self._log("agent_interaction", a.id, b.id, a.x, a.y, result="ignorada")
        # following / avoiding labels for the record
        if _sig(out_a[O_APPROACH]) > 0.6 and _sig(out_a[O_APPROACH]) > _sig(out_a[O_AVOID]):
            self._log("agent_follow", a.id, b.id, a.x, a.y)
        elif _sig(out_a[O_AVOID]) > 0.6:
            self._log("agent_avoid", a.id, b.id, a.x, a.y)

    def _hear(self, emitter, sound, t):
        for o in self.agents:
            if o.id == emitter.id:
                continue
            d = math.hypot(o.x - emitter.x, o.y - emitter.y)
            if d <= self.cfg.sound_range:
                intensity = 1.0 - d / self.cfg.sound_range
                o.heard_vec[sound] = min(1.0, o.heard_vec[sound] + intensity)
                o.push_heard(t, sound, emitter.id)
                r = o.relationship(emitter.id)
                r.sounds_heard += 1; r.familiarity = min(1.0, r.familiarity + 0.005)
                self.comm.record_heard(sound)
                self._pending.setdefault(o.id, []).append(
                    {"sound": sound, "emitter": emitter.id, "ex": emitter.x, "ey": emitter.y,
                     "d0": d, "t": t, "food0": o.energy})
                self._log("agent_sound_heard", o.id, emitter.id, o.x, o.y, sound=sound,
                          extra={"intensity": round(intensity, 2)})

    def _resolve_pending_food(self, a):
        # called when `a` just ate: any recent heard-sound gets a "food after" credit
        for obs in self._pending.get(a.id, []):
            if not obs.get("_food"):
                obs["_food"] = True
                self.comm.record_response(obs["sound"], "encontró_comida")

    def _advance_pending(self, t):
        for aid, lst in list(self._pending.items()):
            agent = self._by_id.get(aid)
            keep = []
            for obs in lst:
                if agent is not None and not obs.get("_moved"):
                    d = math.hypot(agent.x - obs["ex"], agent.y - obs["ey"])
                    if d < obs["d0"] - 1.0:
                        obs["_moved"] = True
                        self.comm.record_response(obs["sound"], "acercó")
                        r = agent.relationship(obs["emitter"]); r.responses += 1
                    elif d > obs["d0"] + 2.0:
                        self.comm.record_response(obs["sound"], "alejó")
                if t - obs["t"] < RESP_WINDOW:
                    keep.append(obs)
            if keep:
                self._pending[aid] = keep
            else:
                self._pending.pop(aid, None)

    # ---------------------------------------------------------------- reproduction
    def _try_reproduce(self, a, outs, newborns, rew, t):
        out_a = outs.get(a.id)
        if out_a is None or _sig(out_a[O_REPRO]) <= 0.5:
            return None
        if not (a.mature(self.cfg) and a.energy >= self.cfg.reproduction_min_energy and a.repro_cd == 0):
            return None
        # look among *all* nearby opposite-sex agents (not just the single nearest)
        # and court the best-bonded willing one. A mating agent seeks its partner,
        # not merely whoever is closest — so a strong pair-bond can actually breed.
        cands = []
        for o in self.agents:
            if o.id == a.id or o.sex == a.sex:
                continue
            d = math.hypot(o.x - a.x, o.y - a.y)
            if d <= self.cfg.repro_radius:
                cands.append((a.relationship(o.id).affinity, o))
        if not cands:
            return None
        self.repro_attempts += 1
        cands.sort(key=lambda c: -c[0])            # best-bonded first
        b = None
        best_reason = "rechazada"
        for _aff, cand in cands:
            out_b = outs.get(cand.id)
            b_willing = (out_b is not None and _sig(out_b[O_REPRO]) > 0.5) or \
                        (t - cand.repro_desire_tick <= self.cfg.courtship_window)
            if not b_willing:
                best_reason = "rechazada"; continue
            if not (cand.mature(self.cfg) and cand.energy >= self.cfg.reproduction_min_energy
                    and cand.repro_cd == 0):
                best_reason = "pareja_no_apta"; continue
            rc = a.relationship(cand.id)
            if (rc.affinity < self.cfg.reproduction_min_affinity
                    or rc.pos < self.cfg.reproduction_min_interactions
                    or rc.sounds_heard < self.cfg.reproduction_min_signals):
                best_reason = "vínculo_insuficiente"; continue
            b = cand; break
        if b is None:
            self._log("reproduction_attempt", a.id, cands[0][1].id, a.x, a.y, result=best_reason)
            return None
        ra = a.relationship(b.id)
        # success: father A/B roles by sex
        pa = a if a.sex == "A" else b
        pb = b if b.sex == "B" else a
        child_brain = pa.brain.crossover(pb.brain, self.rng, self.cfg.mutation_rate, self.cfg.weight_mutation_scale)
        child_genes = crossover_genes(pa.genes, pb.genes, self.rng, self.cfg.mutation_rate)
        sex = "A" if self.rng.random() < 0.5 else "B"
        gen = max(a.generation, b.generation) + 1
        # created detached; the caller adds it via `newborns` so we don't mutate
        # self.agents while iterating over it in pass 3.
        child = self._spawn(sex, gen, pa.id, pb.id, child_brain, child_genes,
                            near=(a.x, a.y), append=False)
        # cost + cooldown
        a.energy -= self.cfg.reproduction_cost; b.energy -= self.cfg.reproduction_cost
        a.repro_cd = self.cfg.reproduction_cooldown; b.repro_cd = self.cfg.reproduction_cooldown
        a.n_children += 1; b.n_children += 1
        rew[a.id] += 5.0; rew[b.id] = rew.get(b.id, 0.0) + 5.0
        self.repro_success += 1
        self.repro_affinity_sum += ra.affinity
        self.repro_signals_sum += (1.0 if ra.sounds_heard > 0 else 0.0)
        self._pending_offspring.append(((pa.id, pb.id), child.id, t + 100))
        self._log("reproduction_success", pa.id, pb.id, a.x, a.y,
                  extra={"child": child.id, "generation": gen, "sex": sex,
                         "affinity": round(ra.affinity, 3), "interactions": ra.pos,
                         "genes": {k: round(v, 3) for k, v in child_genes.items()},
                         "parent_energy": [round(a.energy, 1), round(b.energy, 1)]})
        self._log("agent_birth", child.id, None, child.x, child.y,
                  extra={"sex": sex, "generation": gen, "parent_a": pa.id, "parent_b": pb.id})
        return child

    @property
    def repro_affinity_mean(self):
        return self.repro_affinity_sum / self.repro_success if self.repro_success else 0.0

    @property
    def repro_signals_mean(self):
        return self.repro_signals_sum / self.repro_success if self.repro_success else 0.0

    def _credit_offspring(self, t):
        due = [o for o in self._pending_offspring if o[2] <= t]
        for parents, cid, _ in due:
            if self._by_id.get(cid) is not None:      # child survived the window
                for pid in parents:
                    p = self._by_id.get(pid)
                    if p is not None:
                        p.reward_total += 3.0
        self._pending_offspring = [o for o in self._pending_offspring if o[2] > t]

    # ---------------------------------------------------------------- deaths
    def _process_deaths(self, t):
        survivors = []
        for a in self.agents:
            if a.energy <= 0 or a.age >= self.cfg.max_age * a.genes["longevity"]:
                self.deaths_total += 1
                cause = "hambre" if a.energy <= 0 else "vejez"
                self._log("agent_death", a.id, None, a.x, a.y, result=cause,
                          extra={"age": a.age, "children": a.n_children, "reward_total": round(a.reward_total, 2)})
            else:
                survivors.append(a)
        self.agents = survivors

    # ---------------------------------------------------------------- labels
    def _state_label(self, a, out):
        if out is None:
            return "explorando"
        nb, nd = self._nearest_now(a)
        near = nb is not None and nd <= self.cfg.interaction_radius
        if near and _sig(out[O_REPRO]) > 0.5 and a.mature(self.cfg):
            return "reproduciéndose"
        if near and _sig(out[O_INTERACT]) > 0.5:
            return "interactuando"
        if _sig(out[O_EMIT]) > 0.5:
            return "comunicando"
        if near and _sig(out[O_AVOID]) > 0.6 and _sig(out[O_AVOID]) > _sig(out[O_APPROACH]):
            return "evitando"
        if nb is not None and _sig(out[O_APPROACH]) > 0.6:
            return "siguiendo"
        if a.hunger > 0.5:
            return "buscando_comida"
        return "explorando"

    # ---------------------------------------------------------------- logging
    def _log(self, type_, aid, target, x, y, sound=None, e_before=None, e_after=None,
             result=None, extra=None):
        if self.store:
            self.store.log_event({
                "tick": self.tick, "type": type_, "agent": aid, "target": target,
                "x": round(float(x), 2), "y": round(float(y), 2), "sound": sound,
                "e_before": None if e_before is None else round(float(e_before), 2),
                "e_after": None if e_after is None else round(float(e_after), 2),
                "result": result, "extra": extra or {},
            })

    # ---------------------------------------------------------------- rows / render
    def metrics_row(self):
        n = len(self.agents)
        a_cnt = sum(1 for a in self.agents if a.sex == "A")
        if n:
            avg_e = float(np.mean([a.energy for a in self.agents]))
            avg_age = float(np.mean([a.age for a in self.agents]))
            avg_hunger = float(np.mean([a.hunger for a in self.agents]))
            max_gen = max(a.generation for a in self.agents)
            gene_means = {k: round(float(np.mean([a.genes[k] for a in self.agents])), 3)
                          for k in ("metabolism", "speed", "learn_mul", "longevity")}
            avg_reward = round(float(np.mean([a.reward_total for a in self.agents])), 3)
        else:
            avg_e = avg_age = avg_hunger = 0.0; max_gen = 0; gene_means = {}; avg_reward = 0.0
        return {
            "tick": self.tick, "population": n, "sex_a": a_cnt, "sex_b": n - a_cnt,
            "births": self.births_total, "deaths": self.deaths_total,
            "avg_energy": round(avg_e, 2), "avg_age": round(avg_age, 1),
            "avg_hunger": round(avg_hunger, 3), "veg_total": round(self.island.veg_total(), 1),
            "interactions_interval": self._interactions_interval, "sounds_interval": self._sounds_interval,
            "reproductions": self.repro_success, "repro_attempts": self.repro_attempts,
            "max_generation": int(max_gen), "avg_reward": avg_reward,
            "lang_diversity": self.comm.diversity(), "mutual_information": self.comm.mutual_information(),
            "gene_means": gene_means,
        }

    def render_state(self):
        agents = []
        recent_sounds = []
        for a in self.agents:
            agents.append({
                "id": a.id, "sex": a.sex, "x": round(a.x, 2), "y": round(a.y, 2),
                "energy": round(a.energy, 1), "state": a.state, "gen": a.generation,
                "hue": round(a.genes["hue"], 2), "last_sound": a.last_sound if a.emitted and a.emitted[-1][0] >= self.tick - 2 else -1,
            })
            if a.emitted and a.emitted[-1][0] >= self.tick - 2:
                recent_sounds.append({"id": a.id, "x": round(a.x, 2), "y": round(a.y, 2),
                                      "sound": a.emitted[-1][1]})
        # interaction lines from this tick's mutual interactions
        links = []
        for a in self.agents:
            for ev in a.interactions[-3:]:
                if ev.get("tick") == self.tick and ev.get("result") == "mutua":
                    o = self._by_id.get(ev["with"]) if hasattr(self, "_by_id") else None
                    if o:
                        links.append([round(a.x, 1), round(a.y, 1), round(o.x, 1), round(o.y, 1)])
        return {
            "tick": self.tick, "island": {"size": self.island.n},
            "veg": self.island.veg.round(2).tolist(),
            "land": self.island.land.astype(int).tolist() if self.tick <= 1 else None,
            "agents": agents, "sounds": recent_sounds, "links": links,
            "metrics": self.metrics_row(),
        }

    def island_render(self):
        """Full land + vegetation map (sent once on connect / on demand)."""
        return self.island.render()

    # ---------------------------------------------------------------- agent panel
    def _by_id_now(self):
        return {a.id: a for a in self.agents}

    def agent_detail(self, aid: int) -> Optional[dict[str, Any]]:
        a = next((x for x in self.agents if x.id == aid), None)
        if a is None:
            return None
        idx = self._by_id_now()
        # nearby agents + relationship with each
        nearby = []
        for o in self.agents:
            if o.id == a.id:
                continue
            d = math.hypot(o.x - a.x, o.y - a.y)
            if d <= self.cfg.sound_range:
                r = a.rel.get(o.id)
                nearby.append({
                    "id": o.id, "sex": o.sex, "dist": round(d, 1), "state": o.state,
                    "affinity": round(r.affinity, 3) if r else 0.0,
                    "familiarity": round(r.familiarity, 3) if r else 0.0,
                })
        nearby.sort(key=lambda z: z["dist"])
        # known relationships (sorted by familiarity)
        rels = sorted((r.to_dict(self.tick, oid) for oid, r in a.rel.items()),
                      key=lambda z: -z["familiarity"])[:12]
        # decision trace (debug): top output activations
        dbg = None
        if a.dbg_out is not None:
            out = a.dbg_out
            acts = [(OUT_LABELS[i], round(float(_sig(out[i])), 3)) for i in range(len(OUT_LABELS))]
            top = sorted(acts, key=lambda z: -z[1])[:6]
            inp = a.dbg_in
            ins = [(IN_LABELS[i], round(float(inp[i]), 3)) for i in range(len(IN_LABELS))] if inp is not None else []
            dbg = {"inputs": ins, "outputs": acts, "top_outputs": top,
                   "chosen": a.dbg_action, "last_reward": round(a.last_reward, 3)}
        return {
            "id": a.id, "sex": a.sex, "x": round(a.x, 2), "y": round(a.y, 2),
            "energy": round(a.energy, 1), "hunger": round(a.hunger, 3),
            "age": a.age, "mature": a.mature(self.cfg), "state": a.state,
            "generation": a.generation, "parent_a": a.parent_a, "parent_b": a.parent_b,
            "n_children": a.n_children, "n_sounds": a.n_sounds, "n_interactions": a.n_interactions,
            "reward_total": round(a.reward_total, 2), "last_reward": round(a.last_reward, 3),
            "repro_cd": a.repro_cd, "hue": round(a.genes["hue"], 2),
            "genes": {k: round(v, 3) for k, v in a.genes.items()},
            "emitted": [{"tick": t, "sound": s} for (t, s) in a.emitted[-12:]],
            "heard": [{"tick": t, "sound": s, "from": f} for (t, s, f) in a.heard[-12:]],
            "heard_vec": [round(float(v), 2) for v in a.heard_vec],
            "nearby": nearby[:10], "relationships": rels,
            "memory": {
                "distinct_known": len(a.rel),
                "recent_interactions": a.interactions[-6:],
                "fast_weight_norm": round(float(np.linalg.norm(a.fast_wo)), 3),
            },
            "debug": dbg,
        }

    # ---------------------------------------------------------------- reports
    def comm_report(self) -> dict[str, Any]:
        rep = self.comm.report()
        rep["emergent_meaning"] = self.comm.emergent_meaning()
        rep["sounds_total"] = int(self.comm.emit.sum())
        rep["most_used"] = int(np.argmax(self.comm.emit)) if self.comm.emit.sum() else None
        return rep

    def reproduction_report(self) -> dict[str, Any]:
        # top pairs by children produced (from living agents' genealogy links)
        from collections import Counter
        pair_children: Counter = Counter()
        for a in self.agents:
            if a.parent_a and a.parent_b:
                key = tuple(sorted((a.parent_a, a.parent_b)))
                pair_children[key] += 1
        top_pairs = [{"parents": list(k), "children": v}
                     for k, v in pair_children.most_common(8)]
        # living lineages: distinct generation-0 ancestors still represented
        lineages = sorted({a.generation for a in self.agents})
        return {
            "attempts": self.repro_attempts, "successes": self.repro_success,
            "avg_affinity_before": round(self.repro_affinity_mean, 3),
            "signals_fraction": round(self.repro_signals_mean, 3),
            "top_pairs": top_pairs,
            "max_generation": max((a.generation for a in self.agents), default=0),
            "generations_present": lineages,
            "min_affinity": self.cfg.reproduction_min_affinity,
            "min_interactions": self.cfg.reproduction_min_interactions,
            "min_signals": self.cfg.reproduction_min_signals,
            "min_energy": self.cfg.reproduction_min_energy,
            "min_age": self.cfg.reproduction_min_age,
        }
