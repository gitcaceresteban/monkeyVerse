"""Emergent personality — read off behaviour, never set as a parameter.

Every number here is a ratio of things the agent actually *did* over its life
(attacks, cooperations, exploration, signalling, time near others...), not a
gene. Two siblings with identical genomes can end up with different personality
profiles if their experiences pushed their brains to behave differently. The
genome only contributes weak innate biases; the profile is the realised
behaviour.
"""

from __future__ import annotations

from typing import Any


def _norm(x: float) -> int:
    return int(max(0.0, min(1.0, x)) * 100)


def profile(a) -> dict[str, int]:
    age = max(1, a.age)
    actions = max(1, a.n_moves + a.n_rests + a.n_attacks)
    attacks_total = max(1, a.atk_won + a.atk_lost)
    social_events = a.n_coop + a.n_follow + a.n_followed + a.n_attacks

    # aggression: how much of its action budget went to attacking
    aggression = a.n_attacks / actions * 3.0
    # cooperation: share of social contact that was peaceful co-presence/following
    cooperation = (a.n_coop + a.n_follow) / max(1, social_events)
    # curiosity: rate of discovering brand-new territory blocks over life
    curiosity = a.new_cells / age * 40.0
    # exploration: how much of the world it has ever set foot in
    exploration = a.territory_fraction()
    # territoriality: aggression concentrated while barely dispersing = defending turf
    territoriality = (a.n_attacks / actions * 2.0) * (1.0 - min(1.0, exploration))
    # sociability: how often it was in company (any social event) per unit time
    sociability = social_events / age * 6.0
    # dominance: fraction of its fights it won
    dominance = a.atk_won / attacks_total if (a.atk_won + a.atk_lost) else 0.0

    return {
        "agresividad": _norm(aggression),
        "cooperación": _norm(cooperation),
        "curiosidad": _norm(curiosity),
        "exploración": _norm(exploration),
        "territorialidad": _norm(territoriality),
        "sociabilidad": _norm(sociability),
        "dominancia": _norm(dominance),
    }


def dominant_trait(prof: dict[str, int]) -> str:
    if not prof:
        return "indefinida"
    return max(prof, key=prof.get)
