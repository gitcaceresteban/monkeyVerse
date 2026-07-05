"""Initial conditions for a living planet (v2).

Only preconditions for existence live here — never behaviours. Every field is a
knob for the "new world" menu and for sensitivity analysis across parallel runs.
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

    # --- world geometry -----------------------------------------------------
    width: int = 160
    height: int = 112

    # --- terrain ------------------------------------------------------------
    terrain_octaves: int = 5          # detail of the elevation noise
    water_level: float = 0.34         # fraction of the planet below sea level
    mountain_level: float = 0.82      # above this, impassable rock
    slope_cost: float = 1.2           # extra move energy per unit of uphill slope
    erosion_rate: float = 0.0006      # slow smoothing of the terrain over time

    # --- life ---------------------------------------------------------------
    initial_population: int = 140
    max_population: int = 550         # hard cap to protect the host
    min_population: int = 10          # abiogenesis floor (0 = allow extinction)
    initial_energy: float = 80.0
    max_energy: float = 240.0
    founder_species: int = 2          # how many seed lineages at genesis

    # --- vegetation / resources --------------------------------------------
    veg_regen: float = 0.024          # plant regrowth rate
    veg_capacity: float = 1.0
    food_energy: float = 8.0          # energy per unit of plant eaten (herbivory)
    meat_energy: float = 10.0         # energy per unit of meat (predation/scavenge)
    corpse_decay: float = 0.014       # how fast carcasses rot away

    # --- metabolism ---------------------------------------------------------
    base_metabolism: float = 0.45
    move_cost: float = 0.13
    rest_recovery: float = 0.4        # metabolism reduction while resting
    max_intake: float = 0.7
    attack_damage: float = 18.0       # energy a successful attack drains from prey
    attack_cost: float = 1.5          # energy the attacker spends striking
    reproduce_overhead: float = 5.0
    founder_diet_max: float = 0.35    # seed lineages start herbivore-leaning

    # --- climate & weather --------------------------------------------------
    day_length: int = 240             # steps per day-night cycle (0 = always day)
    season_length: int = 6000         # steps per seasonal cycle (0 = off)
    season_amplitude: float = 0.5
    rain_base: float = 0.5            # baseline global moisture supply
    weather_volatility: float = 1.0   # scales how wild rain/drought swings are

    # --- disasters (per-step probabilities) --------------------------------
    p_fire: float = 0.0009
    p_flood: float = 0.0004
    p_quake: float = 0.0003
    climate_drift: float = 0.00002    # slow, permanent warming/cooling per step

    # --- signalling ---------------------------------------------------------
    sound_channels: int = 3           # transient calls
    pheromone_channels: int = 2       # persistent ground marks
    pheromone_decay: float = 0.97
    color_channels: int = 3           # a visible display trait (perceived by others)

    # --- perception / brain -------------------------------------------------
    perception_radius: int = 3
    brain_hidden: int = 16
    memory_size: int = 6              # recurrent working memory
    episodic_slots: int = 4           # remembered places (food/danger)

    # --- learning & evolution ----------------------------------------------
    lifetime_learning: float = 0.06   # reward-modulated plasticity strength (0 = pure evolution)
    plasticity_decay: float = 0.004   # forgetting: fast weights fade back to genome
    initial_mutation_rate: float = 0.09
    weight_mutation_scale: float = 0.16
    species_threshold: float = 0.32   # genetic distance that splits a new species

    # --- runtime ------------------------------------------------------------
    target_sps: float = 22.0
    snapshot_every: int = 1500        # resumable snapshots
    stats_every: int = 25
    frame_every: int = 150            # time-machine keyframes

    def resolved_seed(self) -> int:
        if self.seed and self.seed != 0:
            return int(self.seed)
        import random
        return random.randint(1, 2**31 - 1)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SimConfig":
        fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in fields})


CONFIG_SCHEMA: list[dict[str, Any]] = [
    {"key": "name", "label": "Nombre", "type": "text", "default": "planeta",
     "help": "Nombre de este planeta."},
    {"key": "seed", "label": "Semilla", "type": "int", "default": 0, "min": 0, "max": 2**31 - 1,
     "help": "0 = aleatoria. Fija una semilla para reproducir un planeta exacto."},
    {"key": "width", "label": "Ancho", "type": "int", "default": 160, "min": 48, "max": 320},
    {"key": "height", "label": "Alto", "type": "int", "default": 112, "min": 48, "max": 320},
    {"key": "water_level", "label": "Nivel del mar", "type": "float", "default": 0.34, "min": 0.0, "max": 0.8,
     "step": 0.01, "help": "Fracción del planeta cubierta por agua."},
    {"key": "mountain_level", "label": "Nivel de montaña", "type": "float", "default": 0.82, "min": 0.5, "max": 1.0,
     "step": 0.01, "help": "Por encima, roca infranqueable."},
    {"key": "initial_population", "label": "Población inicial", "type": "int", "default": 140, "min": 2, "max": 1200},
    {"key": "max_population", "label": "Población máxima", "type": "int", "default": 550, "min": 10, "max": 4000,
     "help": "Tope duro para proteger la Raspberry Pi."},
    {"key": "min_population", "label": "Población mínima (génesis)", "type": "int", "default": 10, "min": 0, "max": 200,
     "help": "Si baja de aquí aparece vida nueva. 0 = permitir la extinción."},
    {"key": "founder_species", "label": "Especies fundadoras", "type": "int", "default": 2, "min": 1, "max": 12,
     "help": "Linajes distintos al comienzo. Pueden divergir en más especies."},
    {"key": "food_energy", "label": "Energía por planta", "type": "float", "default": 6.5, "min": 1, "max": 40,
     "step": 0.5, "help": "Regula la economía vegetal (herbívoros)."},
    {"key": "meat_energy", "label": "Energía por carne", "type": "float", "default": 9.0, "min": 1, "max": 60,
     "step": 0.5, "help": "Alimento de depredadores y carroñeros."},
    {"key": "base_metabolism", "label": "Metabolismo base", "type": "float", "default": 0.55, "min": 0.05, "max": 2.0,
     "step": 0.01, "help": "Energía que cuesta existir. Sube la presión de escasez."},
    {"key": "day_length", "label": "Duración del día", "type": "int", "default": 240, "min": 0, "max": 4000,
     "help": "Pasos por ciclo día-noche. 0 = siempre de día."},
    {"key": "season_length", "label": "Duración de estación", "type": "int", "default": 6000, "min": 0, "max": 100000},
    {"key": "rain_base", "label": "Humedad base", "type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.02},
    {"key": "p_fire", "label": "Prob. incendio", "type": "float", "default": 0.0009, "min": 0.0, "max": 0.02, "step": 0.0001},
    {"key": "p_flood", "label": "Prob. inundación", "type": "float", "default": 0.0004, "min": 0.0, "max": 0.02, "step": 0.0001},
    {"key": "p_quake", "label": "Prob. terremoto", "type": "float", "default": 0.0003, "min": 0.0, "max": 0.02, "step": 0.0001},
    {"key": "sound_channels", "label": "Canales de sonido", "type": "int", "default": 3, "min": 0, "max": 8},
    {"key": "pheromone_channels", "label": "Canales de feromona", "type": "int", "default": 2, "min": 0, "max": 6,
     "help": "Marcas persistentes en el suelo."},
    {"key": "color_channels", "label": "Canales de color", "type": "int", "default": 3, "min": 0, "max": 6,
     "help": "Apariencia visible para los demás. Puede volverse una señal."},
    {"key": "brain_hidden", "label": "Neuronas ocultas", "type": "int", "default": 16, "min": 4, "max": 64},
    {"key": "memory_size", "label": "Memoria de trabajo", "type": "int", "default": 6, "min": 0, "max": 24},
    {"key": "episodic_slots", "label": "Recuerdos de lugares", "type": "int", "default": 4, "min": 0, "max": 12,
     "help": "Lugares (comida/peligro) que recuerda, con olvido."},
    {"key": "lifetime_learning", "label": "Aprendizaje en vida", "type": "float", "default": 0.06, "min": 0.0, "max": 0.4,
     "step": 0.01, "help": "Plasticidad guiada por recompensa. 0 = solo evolución."},
    {"key": "initial_mutation_rate", "label": "Tasa de mutación", "type": "float", "default": 0.09, "min": 0.0, "max": 0.5,
     "step": 0.01},
    {"key": "species_threshold", "label": "Umbral de especiación", "type": "float", "default": 0.32, "min": 0.05, "max": 0.9,
     "step": 0.01, "help": "Distancia genética que hace nacer una nueva especie."},
    {"key": "target_sps", "label": "Velocidad (pasos/seg)", "type": "float", "default": 22.0, "min": 1, "max": 200, "step": 1},
]
