"""A plain-language portrait of one individual.

Assembled entirely from measured quantities (age vs. the living average, its own
reproduction and cooperation counts, its most-used signals, its combat tally,
its current inferred state and dominant personality trait). It is a readout, not
a story the simulation was told to produce.
"""

from __future__ import annotations

from .language import LEGEND


def summarize(name: str, age: int, avg_age: float, children: int, n_coop: int,
              attacks: int, state: str, dominant_trait: str,
              sym_counts: list[int]) -> str:
    parts = [f"Este individuo pertenece a la especie {name}."]
    parts.append(f"Tiene {age} ticks de edad.")
    if avg_age > 0:
        if age > avg_age * 1.3:
            parts.append("Ha sobrevivido bastante más que el promedio de la población.")
        elif age < avg_age * 0.6:
            parts.append("Es más joven que el promedio de la población.")
        else:
            parts.append("Su edad ronda el promedio de la población.")

    if children == 0:
        parts.append("Nunca logró reproducirse")
    elif children == 1:
        parts.append("Se reprodujo una vez")
    else:
        parts.append(f"Se reprodujo {children} veces")
    if n_coop > 3:
        parts[-1] += ", pero participa frecuentemente en convivencia pacífica."
    elif n_coop > 0:
        parts[-1] += " y ha convivido pacíficamente en algunas ocasiones."
    else:
        parts[-1] += " y apenas ha convivido con otros."

    total_sym = sum(sym_counts)
    if total_sym > 20:
        top = sorted(range(10), key=lambda i: -sym_counts[i])[:2]
        labels = " y ".join(LEGEND[i] for i in top if sym_counts[i] > 0)
        if labels:
            parts.append(f"Sus señales más utilizadas están asociadas a «{labels}».")

    if attacks == 0:
        parts.append("Nunca ha atacado a nadie.")
    else:
        parts.append(f"Ha atacado {attacks} veces.")

    trait_phrase = {
        "agresividad": "un temperamento marcadamente agresivo",
        "cooperación": "una fuerte tendencia a cooperar",
        "curiosidad": "una marcada curiosidad",
        "exploración": "un carácter explorador",
        "territorialidad": "un fuerte apego a su territorio",
        "sociabilidad": "una notable sociabilidad",
        "dominancia": "un perfil dominante en el combate",
    }.get(dominant_trait)
    if trait_phrase:
        parts.append(f"Su comportamiento revela {trait_phrase}.")

    parts.append(f"Actualmente se encuentra en estado «{state}».")
    return " ".join(parts)
