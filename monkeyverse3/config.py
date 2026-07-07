"""Initial conditions for a living, observable planet (v3).

Only preconditions for existence live here — never behaviours. Every field is a
knob for the "new world" menu and for sensitivity analysis across parallel runs.

v3 replaces the free "steps per second" dial with a fixed real-time `tick_rate`
(ticks actually happen at this pace, wall-clock, full stop) so that watching the
world is watching what is actually happening — not a fast-forwarded summary.
It also replaces the old continuous `sound_channels` with a fixed 10-symbol
discrete language channel (see language.py) and adds a `cognition_mode` that
trades population for per-agent brain richness.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class SimConfig:
    # --- identity -----------------------------------------------------------
    name: str = "planeta"
    seed: int = 0
    cognition_mode: str = "liviano"   # "liviano" (more agents) | "avanzado" (richer brains, <=100 agents)

    # --- world geometry -----------------------------------------------------
    width: int = 160
    height: int = 112

    # --- terrain ------------------------------------------------------------
    terrain_octaves: int = 5
    water_level: float = 0.34
    mountain_level: float = 0.82
    slope_cost: float = 1.2
    erosion_rate: float = 0.0006

    # --- life ---------------------------------------------------------------
    initial_population: int = 80      # lower start so a harsh terrain isn't overgrazed at once
    max_population: int = 240         # hard cap; clamped to <=100 in "avanzado" mode.
                                       # Kept modest: richer per-agent perception/interaction
                                       # bookkeeping costs CPU, and v3's point is a real-time
                                       # tick_rate that's actually sustained.
    min_population: int = 10          # abiogenesis floor (0 = allow extinction)
    initial_energy: float = 90.0
    max_energy: float = 240.0
    founder_species: int = 2

    # --- vegetation / resources --------------------------------------------
    veg_regen: float = 0.032         # faster regrowth -> resilient to grazing, no famine collapse
    veg_capacity: float = 1.0
    food_energy: float = 9.0         # richer plants -> carrying capacity stays above the reseed floor
    meat_energy: float = 10.0
    corpse_decay: float = 0.014

    # --- metabolism ---------------------------------------------------------
    base_metabolism: float = 0.43
    move_cost: float = 0.13
    rest_recovery: float = 0.4
    max_intake: float = 0.7
    attack_damage: float = 18.0
    attack_cost: float = 1.5
    reproduce_overhead: float = 5.0
    founder_diet_max: float = 0.35
    # crowding: reproduction is suppressed where the local neighbourhood is packed.
    # This is an environmental constraint (crowding stress), not a decision the
    # agent makes — its job is to give the ecosystem *early* negative feedback so
    # populations approach carrying capacity smoothly instead of overshooting the
    # food supply and collapsing to near-extinction in violent boom/bust cycles.
    repro_crowd_limit: int = 6        # 0 = disabled

    # --- climate & weather --------------------------------------------------
    day_length: int = 240
    season_length: int = 6000
    season_amplitude: float = 0.5
    rain_base: float = 0.5
    weather_volatility: float = 1.0

    # --- disasters ------------------------------------------------------------
    p_fire: float = 0.0009
    p_flood: float = 0.0004
    p_quake: float = 0.0003
    climate_drift: float = 0.00002

    # --- signalling -----------------------------------------------------------
    pheromone_channels: int = 2        # persistent ground marks
    pheromone_decay: float = 0.97
    color_channels: int = 3           # visible display trait
    # the spoken language is always the 10 digits 0-9 — see language.py

    # --- perception / brain --------------------------------------------------
    perception_radius: int = 3
    brain_hidden: int = 16            # floor-raised automatically in "avanzado" mode
    memory_size: int = 6
    episodic_slots: int = 4
    interaction_log_size: int = 10    # per-agent ring buffer of recent interactions
    trajectory_length: int = 40       # per-agent recent-position trail, in ticks

    # --- learning & evolution --------------------------------------------------
    lifetime_learning: float = 0.06
    plasticity_decay: float = 0.004
    initial_mutation_rate: float = 0.09
    weight_mutation_scale: float = 0.16
    species_threshold: float = 0.5     # genetic distance to split a species (higher = fewer)
    species_min_members: int = 3       # a lineage only counts as a species once this many are alive
    # Pure emergence: when False, NOTHING biases an agent's decisions — every
    # move/attack/signal comes only from its randomly-initialised brain shaped by
    # evolution and lifetime learning. When True, two innate "temperament" genes
    # (agg_bias, explore_bias) are added on top of the brain's outputs.
    innate_biases: bool = False

    # --- runtime: fixed real-time pacing ---------------------------------------
    tick_rate: float = 8.0            # ticks per second, wall-clock. Not a "speed" dial.
    snapshot_every: int = 1500
    stats_every: int = 25
    frame_every: int = 150
    heatmap_decay: float = 0.995      # movement-heatmap fade per tick

    def resolved_seed(self) -> int:
        if self.seed and self.seed != 0:
            return int(self.seed)
        import random
        return random.randint(1, 2**31 - 1)

    def apply_cognition_mode(self) -> None:
        """'avanzado' trades headcount for per-agent brain richness. Applied once
        at world creation so sensitivity analysis across modes stays comparable."""
        if self.cognition_mode == "avanzado":
            self.max_population = min(self.max_population, 100)
            self.brain_hidden = max(self.brain_hidden, 28)
            self.memory_size = max(self.memory_size, 10)
            self.episodic_slots = max(self.episodic_slots, 6)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SimConfig":
        fields = {f.name for f in dataclasses.fields(cls)}
        clean = {k: v for k, v in (d or {}).items() if k in fields}
        # coerce the bool-from-select field ("sí"/"no" from the menu). Note bool("no")
        # is truthy, so a plain cast would be wrong — parse the string explicitly.
        if "innate_biases" in clean and isinstance(clean["innate_biases"], str):
            clean["innate_biases"] = clean["innate_biases"].strip().lower() in ("sí", "si", "true", "1", "yes")
        return cls(**clean)


CONFIG_SCHEMA: list[dict[str, Any]] = [
    {"key": "name", "label": "Nombre", "type": "text", "default": "planeta",
     "help": "Nombre de este planeta."},
    {"key": "seed", "label": "Semilla", "type": "int", "default": 0, "min": 0, "max": 2**31 - 1,
     "help": "0 = aleatoria. Fija una semilla para reproducir un planeta exacto."},
    {"key": "cognition_mode", "label": "Modo cognitivo", "type": "select", "default": "liviano",
     "options": ["liviano", "avanzado"],
     "help": "Liviano: muchos agentes, cerebro simple. Avanzado: cerebro más rico, tope de 100 agentes."},
    {"key": "width", "label": "Ancho", "type": "int", "default": 160, "min": 48, "max": 320},
    {"key": "height", "label": "Alto", "type": "int", "default": 112, "min": 48, "max": 320},
    {"key": "water_level", "label": "Nivel del mar", "type": "float", "default": 0.34, "min": 0.0, "max": 0.8,
     "step": 0.01, "help": "Fracción del planeta cubierta por agua."},
    {"key": "mountain_level", "label": "Nivel de montaña", "type": "float", "default": 0.82, "min": 0.5, "max": 1.0,
     "step": 0.01, "help": "Por encima, roca infranqueable."},
    {"key": "initial_population", "label": "Población inicial", "type": "int", "default": 110, "min": 2, "max": 1200},
    {"key": "max_population", "label": "Población máxima", "type": "int", "default": 300, "min": 10, "max": 4000,
     "help": "Tope duro. Súbelo con cuidado: cada agente cuesta más CPU que en v2. En modo avanzado se limita a 100."},
    {"key": "min_population", "label": "Población mínima (génesis)", "type": "int", "default": 10, "min": 0, "max": 200,
     "help": "Si baja de aquí aparece vida nueva. 0 = permitir la extinción."},
    {"key": "founder_species", "label": "Especies fundadoras", "type": "int", "default": 2, "min": 1, "max": 12,
     "help": "Linajes distintos al comienzo. Pueden divergir en más especies."},
    {"key": "food_energy", "label": "Energía por planta", "type": "float", "default": 9.0, "min": 1, "max": 40,
     "step": 0.5, "help": "Regula la economía vegetal (herbívoros)."},
    {"key": "meat_energy", "label": "Energía por carne", "type": "float", "default": 10.0, "min": 1, "max": 60,
     "step": 0.5, "help": "Alimento de depredadores y carroñeros."},
    {"key": "base_metabolism", "label": "Metabolismo base", "type": "float", "default": 0.43, "min": 0.05, "max": 2.0,
     "step": 0.01, "help": "Energía que cuesta existir. Sube la presión de escasez."},
    {"key": "innate_biases", "label": "Sesgos innatos", "type": "select", "default": "no", "options": ["no", "sí"],
     "help": "No = pura emergencia: cada decisión viene solo del cerebro que evoluciona y aprende. Sí = añade dos genes de temperamento sobre las salidas."},
    {"key": "day_length", "label": "Duración del día", "type": "int", "default": 240, "min": 0, "max": 4000,
     "help": "Ticks por ciclo día-noche. 0 = siempre de día."},
    {"key": "season_length", "label": "Duración de estación", "type": "int", "default": 6000, "min": 0, "max": 100000},
    {"key": "rain_base", "label": "Humedad base", "type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.02},
    {"key": "p_fire", "label": "Prob. incendio", "type": "float", "default": 0.0009, "min": 0.0, "max": 0.02, "step": 0.0001},
    {"key": "p_flood", "label": "Prob. inundación", "type": "float", "default": 0.0004, "min": 0.0, "max": 0.02, "step": 0.0001},
    {"key": "p_quake", "label": "Prob. terremoto", "type": "float", "default": 0.0003, "min": 0.0, "max": 0.02, "step": 0.0001},
    {"key": "pheromone_channels", "label": "Canales de feromona", "type": "int", "default": 2, "min": 0, "max": 6,
     "help": "Marcas persistentes en el suelo."},
    {"key": "color_channels", "label": "Canales de color", "type": "int", "default": 3, "min": 0, "max": 6,
     "help": "Apariencia visible para los demás. Puede volverse una señal."},
    {"key": "brain_hidden", "label": "Neuronas ocultas", "type": "int", "default": 16, "min": 4, "max": 64,
     "help": "En modo avanzado se eleva a un mínimo de 28."},
    {"key": "memory_size", "label": "Memoria de trabajo", "type": "int", "default": 6, "min": 0, "max": 24},
    {"key": "episodic_slots", "label": "Recuerdos de lugares", "type": "int", "default": 4, "min": 0, "max": 12,
     "help": "Lugares (comida/peligro) que recuerda, con olvido."},
    {"key": "lifetime_learning", "label": "Aprendizaje en vida", "type": "float", "default": 0.06, "min": 0.0, "max": 0.4,
     "step": 0.01, "help": "Plasticidad guiada por recompensa. 0 = solo evolución."},
    {"key": "initial_mutation_rate", "label": "Tasa de mutación", "type": "float", "default": 0.09, "min": 0.0, "max": 0.5,
     "step": 0.01},
    {"key": "species_threshold", "label": "Umbral de especiación", "type": "float", "default": 0.5, "min": 0.05, "max": 0.9,
     "step": 0.01, "help": "Distancia genética que hace nacer una nueva especie (más alto = menos especies)."},
    {"key": "tick_rate", "label": "Ritmo (ticks/seg, tiempo real)", "type": "float", "default": 8.0, "min": 2, "max": 15,
     "step": 0.5, "help": "Ritmo fijo en tiempo real. No es un acelerador: es el pulso del planeta."},
]
