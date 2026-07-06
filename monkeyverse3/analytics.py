"""Global, planet-level analysis — the "Análisis" view.

Everything here is read-only aggregation over state the simulation already
produced (species registry, symbol statistics, the in-memory interaction ring).
Nothing here feeds back into the simulation; it exists purely for the observer.
"""

from __future__ import annotations

from typing import Any


def compute(sim) -> dict[str, Any]:
    species = sim.species.species
    living = sim.species.living()
    extinct = [sp for sp in species.values() if sp["extinct_tick"] is not None]
    stats = sim.stats_row()

    most_successful = sorted(species.values(), key=lambda sp: -sp["peak_pop"])[:8]
    dominant = sorted(living, key=lambda sp: -sp["pop"])[:5]

    comm = sim.symbol_stats.most_communicative_species(6)
    communicative = [
        {"species_id": sid, "name": species.get(sid, {}).get("name", f"#{sid}"), "emissions": n}
        for sid, n in comm
    ]

    social = _social_graph(sim)

    return {
        "population": stats["population"],
        "species_alive": len(living),
        "species_extinct": len(extinct),
        "max_generation": stats["max_generation"],
        "avg_age": stats["avg_age"],
        "births_total": sim.births_total,
        "deaths_total": sim.deaths_total,
        "death_causes": stats["deaths_totals"],
        "genetic_diversity": stats["genetic_diversity"],
        "language_diversity": stats["language_diversity"],
        "interactions_per_tick": stats["interactions_interval"] / max(1, sim.cfg.stats_every),
        "interactions_total": sim.interactions_total,
        "most_used_symbols": sim.symbol_stats.most_used(5),
        "most_communicative_species": communicative,
        "most_successful_species": [
            {"id": sp["id"], "name": sp["name"], "peak_pop": sp["peak_pop"],
             "pop": sp["pop"], "founded_tick": sp["founded_tick"]}
            for sp in most_successful
        ],
        "dominant_lineages": [
            {"id": sp["id"], "name": sp["name"], "pop": sp["pop"]} for sp in dominant
        ],
        "social_graph": social,
    }


def _species_of(sim) -> dict[int, int]:
    return {a.id: a.species_id for a in sim.agents}


def _social_graph(sim, window: int = 500) -> list[dict[str, Any]]:
    """Species-to-species interaction counts from the recent in-memory window.
    A lightweight substitute for a force-directed graph: an edge list the UI can
    render as a matrix or a simple circular node-link diagram."""
    agent_species = _species_of(sim)
    edges: dict[tuple[int, int], int] = {}
    for ev in sim.recent_interactions[-window:]:
        sa = agent_species.get(ev["agent_id"])
        sb = agent_species.get(ev.get("target_id")) if ev.get("target_id") else None
        if sa is None or sb is None:
            continue
        key = (sa, sb) if sa <= sb else (sb, sa)
        edges[key] = edges.get(key, 0) + 1
    names = sim.species.species
    return [
        {"a": a, "a_name": names.get(a, {}).get("name", f"#{a}"),
         "b": b, "b_name": names.get(b, {}).get("name", f"#{b}"),
         "count": n}
        for (a, b), n in sorted(edges.items(), key=lambda kv: -kv[1])[:40]
    ]
