"""Everything tunable about a Simple Island run, in one place.

Names mirror the V4 spec (INITIAL_AGENTS, MAP_SIZE, REPRODUCTION_MIN_AFFINITY,
SOUND_RANGE, ...). Kept as a dataclass so it serializes cleanly, seeds the
"new island" form, and can be exported alongside a run for reproducibility.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, asdict
from typing import Any

N_SOUNDS = 10  # the alphabet: tones 0..9, initially meaningless


@dataclass
class Config:
    name: str = "isla"
    seed: int = 0                      # 0 => random

    # --- world ---------------------------------------------------------------
    map_size: int = 50                 # MAP_SIZE (square grid, island inscribed)
    island_ratio: float = 0.86         # island radius as a fraction of half-map
    vegetation_density: float = 0.4    # VEGETATION_DENSITY: fraction of land that starts vegetated
    vegetation_regrowth_rate: float = 0.02    # VEGETATION_REGROWTH_RATE (slow but enough)
    veg_capacity: float = 1.0

    # --- population ----------------------------------------------------------
    initial_agents: int = 20           # INITIAL_AGENTS
    initial_a: int = 10                # INITIAL_A
    initial_b: int = 10                # INITIAL_B
    max_agents: int = 60               # MAX_AGENTS

    # --- energy / metabolism -------------------------------------------------
    initial_energy: float = 60.0
    max_energy: float = 120.0
    energy_decay_rate: float = 0.04    # ENERGY_DECAY_RATE per tick (base metabolism)
    move_energy_cost: float = 0.03
    food_energy_gain: float = 18.0     # FOOD_ENERGY_GAIN per unit eaten
    max_intake: float = 0.7
    graze_radius: int = 2              # how far an agent can reach for food (cells)
    starve_energy: float = 8.0         # below this = "extreme hunger"

    # --- movement / time -----------------------------------------------------
    base_tick_rate: float = 3.0        # ticks/second at 1x (slow & observable)
    realtime_speed: float = 1.0        # REALTIME_SPEED default multiplier
    move_step: float = 0.6             # cells per tick at full drive (agents move slowly)

    # --- communication -------------------------------------------------------
    sound_range: float = 9.0           # SOUND_RANGE (cells)
    sound_energy_cost: float = 0.15    # SOUND_ENERGY_COST per emission
    hearing_decay: float = 0.5         # heard-sound memory fade per tick

    # --- brain / learning ----------------------------------------------------
    hidden_size: int = 24              # recurrent hidden units
    learning_rate: float = 0.05        # LEARNING_RATE (lifetime plasticity)
    plasticity_decay: float = 0.003
    mutation_rate: float = 0.08        # MUTATION_RATE
    weight_mutation_scale: float = 0.15

    # --- reproduction (A + B, with real prerequisites) -----------------------
    reproduction_min_energy: float = 45.0   # REPRODUCTION_MIN_ENERGY
    reproduction_min_age: int = 100         # REPRODUCTION_MIN_AGE (ticks) — maturity
    reproduction_min_affinity: float = 0.4  # REPRODUCTION_MIN_AFFINITY
    reproduction_min_interactions: int = 2  # REPRODUCTION_MIN_INTERACTIONS between the pair
    reproduction_min_signals: int = 1       # min sounds heard/answered between the pair
    reproduction_cooldown: int = 90         # REPRODUCTION_COOLDOWN (ticks)
    reproduction_cost: float = 15.0         # energy cost for EACH parent
    courtship_window: int = 12              # ticks a partner's mating intent persists
    max_age: int = 6000

    # --- runtime -------------------------------------------------------------
    metrics_every: int = 30            # ticks between logged metric snapshots
    interaction_radius: float = 3.0    # cells: "near" for social interaction
    repro_radius: float = 5.0          # cells: courting reach (a little more forgiving)

    def resolved_seed(self) -> int:
        if self.seed and self.seed != 0:
            return int(self.seed)
        import random
        return random.randint(1, 2**31 - 1)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Config":
        fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in fields})


# speed presets exposed in the UI
SPEED_PRESETS = [
    {"label": "⏸", "value": 0.0},
    {"label": "0.5×", "value": 0.5},
    {"label": "1×", "value": 1.0},
    {"label": "2×", "value": 2.0},
    {"label": "5×", "value": 5.0},
]

# menu metadata for the "new island" form
CONFIG_SCHEMA: list[dict[str, Any]] = [
    {"key": "name", "label": "Nombre", "type": "text", "default": "isla"},
    {"key": "seed", "label": "Semilla", "type": "int", "default": 0, "min": 0, "max": 2**31 - 1,
     "help": "0 = aleatoria."},
    {"key": "map_size", "label": "Tamaño del mapa", "type": "int", "default": 60, "min": 30, "max": 100},
    {"key": "initial_a", "label": "Agentes tipo A", "type": "int", "default": 10, "min": 1, "max": 30},
    {"key": "initial_b", "label": "Agentes tipo B", "type": "int", "default": 10, "min": 1, "max": 30},
    {"key": "max_agents", "label": "Máximo de agentes", "type": "int", "default": 40, "min": 4, "max": 120},
    {"key": "vegetation_density", "label": "Densidad de vegetación", "type": "float", "default": 0.35,
     "min": 0.05, "max": 1.0, "step": 0.05},
    {"key": "vegetation_regrowth_rate", "label": "Regeneración vegetal", "type": "float", "default": 0.006,
     "min": 0.001, "max": 0.05, "step": 0.001},
    {"key": "energy_decay_rate", "label": "Consumo de energía", "type": "float", "default": 0.10,
     "min": 0.01, "max": 0.5, "step": 0.01},
    {"key": "food_energy_gain", "label": "Energía por comer", "type": "float", "default": 14.0, "min": 2, "max": 40},
    {"key": "sound_range", "label": "Alcance del sonido", "type": "float", "default": 9.0, "min": 2, "max": 30},
    {"key": "sound_energy_cost", "label": "Costo de emitir sonido", "type": "float", "default": 0.15,
     "min": 0.0, "max": 2.0, "step": 0.05},
    {"key": "learning_rate", "label": "Tasa de aprendizaje", "type": "float", "default": 0.05,
     "min": 0.0, "max": 0.3, "step": 0.01},
    {"key": "mutation_rate", "label": "Tasa de mutación", "type": "float", "default": 0.08,
     "min": 0.0, "max": 0.4, "step": 0.01},
    {"key": "reproduction_min_affinity", "label": "Afinidad mínima repr.", "type": "float", "default": 0.4,
     "min": 0.0, "max": 1.0, "step": 0.05},
    {"key": "reproduction_min_interactions", "label": "Interacciones mínimas repr.", "type": "int", "default": 3,
     "min": 0, "max": 20},
    {"key": "reproduction_cooldown", "label": "Cooldown reproductivo", "type": "int", "default": 300,
     "min": 0, "max": 3000},
    {"key": "realtime_speed", "label": "Velocidad inicial", "type": "float", "default": 1.0,
     "min": 0.5, "max": 5.0, "step": 0.5},
]
