"""Explicit interaction events, for the observer's chronicle.

An interaction is recorded whenever two agents' mechanical actions actually
touched each other this tick: an attack landed, a reproduction happened nearby,
a signal was emitted with another agent in earshot, or two agents were simply
adjacent. The *type* label (cooperación/competencia/huida/...) is applied here,
by the observer's instruments, to classify what the engine already did — the
agents themselves have no notion of these categories. This keeps the underlying
simulation free of programmed social behaviour while still giving the observer
a readable, filterable history.
"""

from __future__ import annotations

from typing import Any, Optional

# canonical interaction types (labels only — never fed back into agent decisions)
TYPES = ["encuentro", "cooperación", "competencia", "reproducción", "huida",
         "ataque", "seguimiento", "señal"]


def classify_signal(emitter_diet: float, target_diet: float, symbol: int,
                     energy_delta_emitter: float) -> str:
    """A signal emitted with another agent in earshot. We don't know what it
    means — 'señal' is the honest label. If emitting is later followed by the
    listener approaching (tracked separately as 'seguimiento'), that's a
    stronger empirical signature of coordination, but we don't presume it here.
    """
    return "señal"


def make_event(tick: int, agent_id: int, target_id: Optional[int], kind: str,
                signal: Optional[int], result: str, energy_delta: float,
                position: tuple[int, int]) -> dict[str, Any]:
    return {
        "tick": tick, "agent_id": agent_id, "target_id": target_id, "type": kind,
        "signal": signal, "result": result, "energy_delta": round(float(energy_delta), 3),
        "x": position[0], "y": position[1],
    }


def classify_encounter(a_diet: float, b_diet: float, a_agg: float, b_agg: float) -> str:
    """Two agents ended up adjacent with no attack and no reproduction this
    tick. Labelled by evolved disposition, purely for the observer: a pair of
    low-aggression, similar-diet agents lingering near each other reads as
    'cooperación' (they tolerate proximity); a high-aggression pairing that
    didn't escalate still reads as plain 'encuentro'."""
    if a_agg < -0.15 and b_agg < -0.15 and abs(a_diet - b_diet) < 0.3:
        return "cooperación"
    if a_agg > 0.3 or b_agg > 0.3:
        return "competencia"
    return "encuentro"
