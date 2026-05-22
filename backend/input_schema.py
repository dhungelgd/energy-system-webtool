from dataclasses import dataclass
from typing import Dict, Any, Optional, List

# solver configuration
@dataclass
class SolverConfig:
    name: str ="cbc"
    tee: bool =False

# electricity demand
@dataclass
class DemandConfig:
    profile: str
    column: str
    scaling_factor: float
    bus: str
    label: str

# grid supply
@dataclass
class GridConfig:
    bus: str
    variable_costs: float
    feedin_tariff: float
    label: str

# full system configuration
@dataclass
class SystemConfig:
    buses: Dict[str, str]
    technologies: Dict[str, Any]
    solver: SolverConfig