from dataclasses import dataclass
from typing import Dict, Any, Optional, List

# solver configuration
@dataclass
class SolverConfig:
    name: str ="cbc"
    tee: bool =False
