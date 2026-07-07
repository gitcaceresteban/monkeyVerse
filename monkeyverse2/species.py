"""Species are not defined in advance. They are discovered: as lineages drift
genetically, a child too different from its parent's species founds a new one.
Species can also go extinct. This gives an open, branching tree of life.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

_SYL_A = ["ka", "mo", "ti", "vu", "ne", "sa", "ro", "li", "gu", "ze", "pha", "dry", "xu", "ol"]
_SYL_B = ["ron", "tis", "mera", "vok", "nel", "sai", "dux", "lith", "gar", "zon", "pod", "wing"]


def _name(sid: int, rng: np.random.Generator) -> str:
    a = _SYL_A[rng.integers(0, len(_SYL_A))]
    b = _SYL_B[rng.integers(0, len(_SYL_B))]
    return (a + b).capitalize()


class SpeciesRegistry:
    def __init__(self, threshold: float, rng: np.random.Generator):
        self.threshold = threshold
        self.rng = rng
        self.species: dict[int, dict[str, Any]] = {}
        self.next_id = 1

    def _create(self, centroid: np.ndarray, parent: int, tick: int, color) -> int:
        sid = self.next_id
        self.next_id += 1
        self.species[sid] = {
            "id": sid, "name": _name(sid, self.rng), "parent": parent,
            "founded_tick": tick, "extinct_tick": None,
            "centroid": np.asarray(centroid, np.float32),
            "color": [round(float(c), 3) for c in (color if len(color) else [0.5, 0.5, 0.5])],
            "pop": 0, "peak_pop": 0,
        }
        return sid

    def found(self, genome, tick: int) -> int:
        return self._create(genome.gene_vector(), 0, tick, genome.color)

    def assign_child(self, child_genome, parent_species: int, tick: int):
        """Return (species_id, speciation_event_or_None)."""
        sp = self.species.get(parent_species)
        vec = child_genome.gene_vector()
        if sp is None:
            sid = self._create(vec, 0, tick, child_genome.color)
            return sid, None
        if child_genome.distance(sp["centroid"]) > self.threshold:
            sid = self._create(vec, parent_species, tick, child_genome.color)
            ev = {"kind": "especiación", "species": sid, "name": self.species[sid]["name"],
                  "parent": parent_species, "parent_name": sp["name"]}
            return sid, ev
        return parent_species, None

    def update(self, agents, tick: int) -> list[dict[str, Any]]:
        """Recount populations, drift centroids, detect extinctions."""
        counts: dict[int, int] = {}
        vecs: dict[int, list] = {}
        for a in agents:
            counts[a.species_id] = counts.get(a.species_id, 0) + 1
            vecs.setdefault(a.species_id, []).append(a.genome.gene_vector())
        events = []
        for sid, sp in self.species.items():
            pop = counts.get(sid, 0)
            sp["pop"] = pop
            sp["peak_pop"] = max(sp["peak_pop"], pop)
            if pop > 0 and sid in vecs:
                mean = np.mean(vecs[sid], axis=0)
                sp["centroid"] = (0.98 * sp["centroid"] + 0.02 * mean).astype(np.float32)
            if pop == 0 and sp["extinct_tick"] is None and sp["peak_pop"] > 0:
                sp["extinct_tick"] = tick
                events.append({"kind": "extinción", "species": sid, "name": sp["name"],
                               "peak_pop": sp["peak_pop"]})
        return events

    def living(self) -> list[dict[str, Any]]:
        out = []
        for sp in self.species.values():
            if sp["pop"] > 0:
                out.append({"id": sp["id"], "name": sp["name"], "pop": sp["pop"],
                            "color": sp["color"], "parent": sp["parent"],
                            "founded_tick": sp["founded_tick"]})
        out.sort(key=lambda d: -d["pop"])
        return out

    # -------------------------------------------------------------- persistence
    def to_state(self) -> dict[str, Any]:
        return {"next_id": self.next_id,
                "species": {sid: {**sp, "centroid": sp["centroid"]} for sid, sp in self.species.items()}}

    def load_state(self, s: dict[str, Any]) -> None:
        self.next_id = s["next_id"]
        self.species = {}
        for sid, sp in s["species"].items():
            sp = dict(sp)
            sp["centroid"] = np.asarray(sp["centroid"], np.float32)
            self.species[int(sid)] = sp
