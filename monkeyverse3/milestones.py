"""Automatic chronicler of the planet's history.

Watches the simulation and records the *first time* notable things happen, plus
open-ended landmark events (new species, extinctions, disasters). This is how a
world without an author still gets a history worth reading back.
"""

from __future__ import annotations

from typing import Any, Optional

FIRST_LABELS = {
    "first_birth": "El primer nacimiento",
    "first_death": "La primera muerte",
    "first_reproduction": "La primera reproducción",
    "first_predation": "La primera depredación",
    "first_scavenge": "El primer carroñeo",
    "first_signal": "La primera señal usada de forma sostenida",
    "first_migration": "La primera gran migración",
    "first_community": "La primera comunidad estable",
    "first_speciation": "El nacimiento de una nueva especie",
    "first_extinction": "La primera extinción",
    "first_fire": "El primer incendio",
    "first_flood": "La primera inundación",
    "first_quake": "El primer terremoto",
    "first_learning": "Los primeros cerebros que aprendieron en vida",
    "first_symbol_use": "El primer uso sostenido de un símbolo",
    "first_meaning": "Un símbolo adquirió un significado empírico asociado",
    "first_cooperation": "La primera cooperación observada",
    "first_following": "El primer seguimiento sostenido entre individuos",
}


class MilestoneTracker:
    def __init__(self):
        self.seen: set[str] = set()

    def first(self, kind: str, tick: int, data: Optional[dict] = None) -> Optional[dict[str, Any]]:
        if kind in self.seen:
            return None
        self.seen.add(kind)
        return {"tick": tick, "kind": kind,
                "label": FIRST_LABELS.get(kind, kind), "data": data or {}}

    def to_state(self) -> dict[str, Any]:
        return {"seen": sorted(self.seen)}

    def load_state(self, s: dict[str, Any]) -> None:
        self.seen = set(s.get("seen", []))
