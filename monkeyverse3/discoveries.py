"""Automatic discovery of interesting phenomena.

Every so often the observer takes a snapshot of a few population-level indicators
(dominant species, diet mix, cooperation vs. aggression rates, language usage,
following/alliance activity). By comparing the newest snapshot against an earlier
one, it flags qualitative *changes* — a new dominant species, a swing toward
cooperation, a collapse in aggression, a newly popular symbol, the first stable
alliance or following chain. These read as headlines in a "Descubrimientos" feed.

This is cheap: it runs on a slow cadence (every `interval` ticks), over compact
aggregates, never per agent per tick.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


class DiscoveryEngine:
    def __init__(self, interval: int = 400, window: int = 1):
        self.interval = interval
        self.window = window           # how many snapshots back to compare against
        self.snapshots: list[dict[str, Any]] = []
        self.seen_firsts: set[str] = set()

    def _snapshot(self, sim) -> dict[str, Any]:
        agents = sim.agents
        n = len(agents)
        if n == 0:
            return {"tick": sim.tick, "n": 0}
        diets = np.array([a.genome.genes["diet"] for a in agents])
        # per-tick rates approximated from lifetime counters over population
        total_coop = sum(a.n_coop + a.n_follow for a in agents)
        total_atk = sum(a.n_attacks for a in agents)
        # dominant species
        counts: dict[int, int] = {}
        for a in agents:
            counts[a.species_id] = counts.get(a.species_id, 0) + 1
        dom = max(counts, key=counts.get)
        # most-used symbol globally
        gt = sim.symbol_stats.global_totals
        top_sym = int(np.argmax(gt)) if gt.sum() > 0 else -1
        return {
            "tick": sim.tick, "n": n,
            "dominant_species": dom,
            "carnivore_frac": float((diets > 0.6).mean()),
            "coop_ratio": total_coop / max(1, total_coop + total_atk),
            "top_symbol": top_sym,
            "following_active": sum(1 for a in agents if a.follow_streak >= 3),
        }

    def maybe_run(self, sim) -> list[dict[str, Any]]:
        if sim.tick % self.interval != 0:
            return []
        snap = self._snapshot(sim)
        self.snapshots.append(snap)
        if len(self.snapshots) > 40:
            self.snapshots = self.snapshots[-40:]
        if snap["n"] == 0 or len(self.snapshots) <= self.window:
            return []
        old = self.snapshots[-1 - self.window]
        if old["n"] == 0:
            return []
        found: list[dict[str, Any]] = []

        if snap["dominant_species"] != old["dominant_species"]:
            nm = sim.species.species.get(snap["dominant_species"], {}).get("name", "?")
            found.append({"kind": "especie_dominante",
                          "label": f"Nueva especie dominante: {nm}"})

        d_carn = snap["carnivore_frac"] - old["carnivore_frac"]
        if d_carn > 0.2:
            found.append({"kind": "estrategia_alimenticia",
                          "label": "Auge de una estrategia carnívora"})
        elif d_carn < -0.2:
            found.append({"kind": "estrategia_alimenticia",
                          "label": "Retorno al herbivorismo dominante"})

        d_coop = snap["coop_ratio"] - old["coop_ratio"]
        if d_coop > 0.12:
            found.append({"kind": "cooperación",
                          "label": "Aumento sostenido de la cooperación"})
        elif d_coop < -0.12:
            found.append({"kind": "agresividad",
                          "label": "Disminución de la cooperación / más conflicto"})

        if snap["top_symbol"] != old["top_symbol"] and snap["top_symbol"] >= 0:
            from .language import LEGEND
            found.append({"kind": "lenguaje",
                          "label": f"Un nuevo símbolo domina la comunicación: "
                                   f"[{snap['top_symbol']}] {LEGEND[snap['top_symbol']]}"})

        if snap["following_active"] >= 5 and "cadena_seguimiento" not in self.seen_firsts:
            self.seen_firsts.add("cadena_seguimiento")
            found.append({"kind": "cadena_seguimiento",
                          "label": "Primera cadena de seguimiento generalizada"})

        for f in found:
            f["tick"] = sim.tick
        return found

    # -------------------------------------------------------------- persistence
    def to_state(self) -> dict[str, Any]:
        return {"snapshots": self.snapshots, "seen_firsts": sorted(self.seen_firsts)}

    def load_state(self, s: dict[str, Any]) -> None:
        self.snapshots = s.get("snapshots", [])
        self.seen_firsts = set(s.get("seen_firsts", []))
