from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from backend.solving import DEFAULT_SOLVER

# solver configuration
@dataclass
class SolverConfig:
    name: str = DEFAULT_SOLVER
    tee: bool =False