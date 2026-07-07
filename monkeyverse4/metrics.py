"""Communication statistics + automatic analysis.

None of this defines what a sound means. It only *measures*: how often each tone
0-9 is used, in what context the emitter was (food nearby? another agent nearby?
about to mate?), and what the hearer tends to do afterwards (approach the
emitter? find food soon?). From those raw co-occurrences we can compute entropy,
per-sound response probabilities and a simple mutual-information estimate — and
only then, if the evidence is strong, call something a "possible emergent
meaning".
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .config import N_SOUNDS

CONTEXTS = ["comida_cerca", "agente_cerca", "energia_baja", "cortejo"]
RESPONSES = ["acercó", "alejó", "encontró_comida", "respondió"]


class CommStats:
    def __init__(self):
        self.emit = np.zeros(N_SOUNDS, np.int64)
        self.emit_ctx = np.zeros((N_SOUNDS, len(CONTEXTS)), np.int64)
        self.resp = np.zeros((N_SOUNDS, len(RESPONSES)), np.int64)
        self.heard_total = np.zeros(N_SOUNDS, np.int64)

    def record_emit(self, sound: int, ctx: dict[str, bool]) -> None:
        self.emit[sound] += 1
        for i, c in enumerate(CONTEXTS):
            if ctx.get(c):
                self.emit_ctx[sound, i] += 1

    def record_heard(self, sound: int) -> None:
        self.heard_total[sound] += 1

    def record_response(self, sound: int, kind: str) -> None:
        if kind in RESPONSES:
            self.resp[sound, RESPONSES.index(kind)] += 1

    # ---------------------------------------------------------------- measures
    @staticmethod
    def _entropy(counts) -> float:
        s = counts.sum()
        if s <= 0:
            return 0.0
        p = counts[counts > 0] / s
        h = float(-(p * np.log(p)).sum())
        return round(h / math.log(N_SOUNDS), 4) if N_SOUNDS > 1 else 0.0

    def diversity(self) -> float:
        return self._entropy(self.emit)

    def mutual_information(self) -> float:
        """I(sound; context) in bits, normalised — how much knowing the sound
        tells you about the emitter's context. 0 = sounds are context-blind."""
        joint = self.emit_ctx.astype(float)
        total = joint.sum()
        if total <= 0:
            return 0.0
        pj = joint / total
        ps = pj.sum(axis=1, keepdims=True)
        pc = pj.sum(axis=0, keepdims=True)
        denom = ps * pc
        with np.errstate(divide="ignore", invalid="ignore"):
            terms = pj * np.log2(np.where((pj > 0) & (denom > 0), pj / denom, 1.0))
        mi = float(np.nansum(terms))
        hs = -float(np.nansum(ps * np.log2(np.where(ps > 0, ps, 1.0))))
        return round(mi / hs, 4) if hs > 1e-9 else 0.0

    def report(self) -> dict[str, Any]:
        out = {"emit_counts": self.emit.tolist(), "diversity": self.diversity(),
               "mutual_information": self.mutual_information(),
               "contexts": CONTEXTS, "responses": RESPONSES, "per_sound": []}
        for s in range(N_SOUNDS):
            n = int(self.emit[s])
            heard = int(self.heard_total[s])
            row = {"sound": s, "emitted": n, "heard": heard}
            if n >= 5:
                ctx_fracs = (self.emit_ctx[s] / n).round(3)
                row["context"] = {CONTEXTS[i]: float(ctx_fracs[i]) for i in range(len(CONTEXTS))}
            if heard >= 5:
                resp_fracs = (self.resp[s] / heard).round(3)
                row["response"] = {RESPONSES[i]: float(resp_fracs[i]) for i in range(len(RESPONSES))}
            out["per_sound"].append(row)
        return out

    def emergent_meaning(self) -> list[dict[str, Any]]:
        """A sound is flagged with a *possible* meaning only when it is (a) used
        enough times, (b) strongly (>55%) tied to one context, AND (c) that
        association is well above the background rate for that context (lift ≥
        1.4). The lift test is essential: on a crowded island almost every sound
        co-occurs with «agente_cerca», so raw frequency alone would falsely flag
        every tone. Requiring the sound to stand out from the base rate keeps this
        honest and consistent with the near-zero mutual information."""
        total = int(self.emit.sum())
        if total < 30:
            return []
        base = self.emit_ctx.sum(axis=0) / max(total, 1)   # background P(context)
        found = []
        for s in range(N_SOUNDS):
            n = int(self.emit[s])
            if n < 15:
                continue
            fr = self.emit_ctx[s] / n
            i = int(np.argmax(fr))
            lift = fr[i] / base[i] if base[i] > 1e-6 else 0.0
            if fr[i] > 0.55 and lift >= 1.4:
                found.append({"sound": s, "context": CONTEXTS[i],
                              "strength": round(float(fr[i]), 3),
                              "lift": round(float(lift), 2), "n": n})
        return found

    def to_state(self):
        return {"emit": self.emit, "emit_ctx": self.emit_ctx, "resp": self.resp,
                "heard_total": self.heard_total}

    def load_state(self, s):
        self.emit = np.asarray(s["emit"], np.int64)
        self.emit_ctx = np.asarray(s["emit_ctx"], np.int64)
        self.resp = np.asarray(s["resp"], np.int64)
        self.heard_total = np.asarray(s["heard_total"], np.int64)


def auto_analysis(sim) -> dict[str, Any]:
    """Plain-language readout of the run — only claims things the data supports."""
    ag = sim.agents
    n = len(ag)
    a_cnt = sum(1 for x in ag if x.sex == "A")
    b_cnt = n - a_cnt
    notes: list[str] = []

    # population trend from recent metric history
    hist = sim.pop_history[-20:]
    if len(hist) >= 6:
        early = np.mean(hist[:len(hist)//2]); late = np.mean(hist[len(hist)//2:])
        if late > early * 1.15:
            notes.append("La población está creciendo.")
        elif late < early * 0.85:
            notes.append("La población está disminuyendo.")
        else:
            notes.append("La población se mantiene estable.")
    if n == 0:
        notes.append("La población se extinguió.")

    if abs(a_cnt - b_cnt) <= max(1, n * 0.2):
        notes.append(f"Equilibrio entre sexos (A={a_cnt}, B={b_cnt}).")
    else:
        notes.append(f"Desequilibrio entre sexos (A={a_cnt}, B={b_cnt}).")

    comm = sim.comm
    if comm.emit.sum() > 0:
        top = int(np.argmax(comm.emit))
        notes.append(f"El sonido más usado es el {top}.")
    meaning = comm.emergent_meaning()
    if meaning:
        for m in meaning:
            notes.append(f"Posible significado emergente: el sonido {m['sound']} "
                         f"aparece junto a «{m['context']}» el {int(m['strength']*100)}% de las veces "
                         f"(n={m['n']}).")
    else:
        notes.append("Todavía no hay evidencia estadística de que ningún sonido tenga un significado fijo.")

    # communication before reproduction
    if sim.repro_success > 0:
        notes.append(f"Reproducciones exitosas: {sim.repro_success}. "
                     f"Afinidad media previa a reproducirse: {round(sim.repro_affinity_mean, 3)}.")
        if sim.repro_signals_mean > 0.5:
            notes.append("Las parejas que se reprodujeron habían intercambiado señales antes.")
    else:
        notes.append("Aún no ha habido reproducciones.")

    # most social agents
    social = sorted(ag, key=lambda x: -x.n_interactions)[:3]
    if social and social[0].n_interactions > 0:
        notes.append("Agentes más sociales: " + ", ".join(f"#{x.id}({x.n_interactions})" for x in social))

    return {
        "notes": notes,
        "population": n, "sex_a": a_cnt, "sex_b": b_cnt,
        "max_generation": max((x.generation for x in ag), default=0),
        "births": sim.births_total, "deaths": sim.deaths_total,
        "reproductions": sim.repro_success,
        "possible_meanings": meaning,
    }
