"""Initial conditions for a world.

Everything here is a *minimal precondition for existence*, never a behaviour.
These are the knobs exposed in the "new simulation" menu, so a value only lives
here if changing it is scientifically interesting (sensitivity analysis).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class SimConfig:
    # --- identity -----------------------------------------------------------
    name: str = "world"
    seed: int = 0  # 0 => random seed chosen at creation time

    # --- world geometry -----------------------------------------------------
    width: int = 128
    height: int = 96

    # --- initial life -------------------------------------------------------
    initial_population: int = 100
    max_population: int = 450          # hard cap, protects the Raspberry Pi
    min_population: int = 8            # abiogenesis: reseed fresh life below this (0 = allow extinction)
    initial_energy: float = 70.0
    max_energy: float = 220.0          # agents cannot hoard energy past this

    # --- environment / resources -------------------------------------------
    resource_patches: int = 6          # number of fertile regions
    resource_capacity: float = 1.0     # max food a fertile cell holds
    resource_floor: float = 0.02       # baseline fertility of "barren" ground
    resource_regen: float = 0.020      # logistic regrowth rate per step
    food_energy: float = 6.5           # energy yielded per unit of food eaten
    season_length: int = 3000          # steps per full seasonal cycle (0 = off)
    season_amplitude: float = 0.55     # how strongly seasons scale fertility
    event_probability: float = 0.0008  # per-step chance of a random climate event

    # --- metabolism (base values; genes shift them per individual) ----------
    base_metabolism: float = 0.60      # energy spent just by existing, per step
    move_cost: float = 0.15            # extra energy per move
    max_intake: float = 0.7            # max food eaten from a cell per step
    reproduce_overhead: float = 6.0    # energy lost in the act of reproducing

    # --- signalling substrate (emergent communication) ----------------------
    signal_channels: int = 3
    signal_decay: float = 0.86         # how fast emitted signals fade each step
    signal_strength: float = 1.0       # scale of what an agent can broadcast

    # --- perception / brain -------------------------------------------------
    perception_radius: int = 3         # fixed, to bound compute
    brain_hidden: int = 12
    memory_size: int = 4               # recurrent memory (agents "remember")

    # --- evolution ----------------------------------------------------------
    initial_mutation_rate: float = 0.09  # genes carry their own mutation rate too
    weight_mutation_scale: float = 0.18

    # --- runtime ------------------------------------------------------------
    target_sps: float = 25.0           # simulation steps per second (speed)
    snapshot_every: int = 1500         # steps between resumable snapshots
    stats_every: int = 25              # steps between logged statistics samples

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
        clean = {k: v for k, v in (d or {}).items() if k in fields}
        return cls(**clean)


# Metadata so the web menu can render sensible inputs with ranges/help text.
CONFIG_SCHEMA: list[dict[str, Any]] = [
    {"key": "name", "label": "Nombre", "type": "text", "default": "world",
     "help": "Nombre de esta simulación."},
    {"key": "seed", "label": "Semilla", "type": "int", "default": 0, "min": 0, "max": 2**31 - 1,
     "help": "0 = aleatoria. Fija una semilla para reproducir exactamente un mundo."},
    {"key": "width", "label": "Ancho del mundo", "type": "int", "default": 128, "min": 32, "max": 256},
    {"key": "height", "label": "Alto del mundo", "type": "int", "default": 96, "min": 32, "max": 256},
    {"key": "initial_population", "label": "Población inicial", "type": "int", "default": 100, "min": 2, "max": 1000},
    {"key": "max_population", "label": "Población máxima", "type": "int", "default": 450, "min": 10, "max": 4000,
     "help": "Tope duro para proteger la Raspberry Pi."},
    {"key": "initial_energy", "label": "Energía inicial", "type": "float", "default": 70.0, "min": 10, "max": 300},
    {"key": "max_energy", "label": "Energía máxima", "type": "float", "default": 220.0, "min": 30, "max": 1000,
     "help": "Límite de energía acumulable. Impide el acaparamiento y mantiene la presión."},
    {"key": "resource_patches", "label": "Zonas fértiles", "type": "int", "default": 6, "min": 1, "max": 40,
     "help": "Heterogeneidad del terreno: más zonas = recursos más repartidos."},
    {"key": "food_energy", "label": "Energía por alimento", "type": "float", "default": 6.5, "min": 1, "max": 40,
     "step": 0.5, "help": "Qué tan nutritivo es el alimento. Regula la economía del mundo."},
    {"key": "min_population", "label": "Población mínima (génesis)", "type": "int", "default": 8, "min": 0, "max": 100,
     "help": "Si la población cae por debajo, aparece vida nueva (migración/abiogénesis). 0 = permitir la extinción."},
    {"key": "resource_regen", "label": "Regeneración de recursos", "type": "float", "default": 0.020,
     "min": 0.0, "max": 0.2, "step": 0.001, "help": "Velocidad a la que vuelve a crecer el alimento."},
    {"key": "season_length", "label": "Duración de estación", "type": "int", "default": 3000, "min": 0, "max": 50000,
     "help": "0 = sin estaciones. Ciclo climático que sube y baja la fertilidad."},
    {"key": "season_amplitude", "label": "Intensidad estacional", "type": "float", "default": 0.55,
     "min": 0.0, "max": 1.0, "step": 0.01},
    {"key": "event_probability", "label": "Prob. de eventos climáticos", "type": "float", "default": 0.0008,
     "min": 0.0, "max": 0.02, "step": 0.0001, "help": "Sequías y florecimientos espontáneos."},
    {"key": "base_metabolism", "label": "Metabolismo base", "type": "float", "default": 0.60,
     "min": 0.05, "max": 2.0, "step": 0.01, "help": "Energía que cuesta simplemente existir. Sube la presión de escasez."},
    {"key": "move_cost", "label": "Costo de moverse", "type": "float", "default": 0.15,
     "min": 0.0, "max": 1.0, "step": 0.01},
    {"key": "signal_channels", "label": "Canales de señal", "type": "int", "default": 3, "min": 0, "max": 8,
     "help": "Sustrato de comunicación. Sin significado inicial."},
    {"key": "signal_decay", "label": "Desvanecimiento de señales", "type": "float", "default": 0.86,
     "min": 0.0, "max": 0.999, "step": 0.01},
    {"key": "perception_radius", "label": "Radio de percepción", "type": "int", "default": 3, "min": 1, "max": 6},
    {"key": "brain_hidden", "label": "Neuronas ocultas", "type": "int", "default": 12, "min": 2, "max": 48},
    {"key": "memory_size", "label": "Memoria (recurrencia)", "type": "int", "default": 4, "min": 0, "max": 16},
    {"key": "initial_mutation_rate", "label": "Tasa de mutación inicial", "type": "float", "default": 0.09,
     "min": 0.0, "max": 0.5, "step": 0.01, "help": "También evoluciona: cada individuo hereda la suya."},
    {"key": "target_sps", "label": "Velocidad (pasos/seg)", "type": "float", "default": 25.0,
     "min": 1, "max": 200, "step": 1, "help": "Se puede cambiar en vivo."},
]
