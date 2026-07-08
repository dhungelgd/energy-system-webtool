"""
Legacy component functions - DEPRECATED.

This module is deprecated. Use backend.components instead.
The functions in this module are kept for backward compatibility only.
"""

import warnings
from typing import Dict, Any

from oemof import solph
from oemof.tools import economics
import pandas as pd

from .components import (
    calculate_epc,
    get_investment,
    add_demand,
    add_heat_demand,
    add_grid_import,
    add_grid_feedin,
    add_pv,
    add_gas_import,
    add_gas_boiler,
    add_heat_pump,
    add_battery,
    add_heat_storage,
    TECH_MAPPING
)

# Deprecation warning
warnings.warn(
    "backend.oemof_components is deprecated. Use backend.components instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export for backward compatibility
__all__ = [
    'calculate_epc',
    'get_investment',
    'add_demand',
    'add_heat_demand',
    'add_grid_import',
    'add_grid_feedin',
    'add_pv',
    'add_gas_import',
    'add_gas_boiler',
    'add_heat_pump',
    'add_battery',
    'add_heat_storage',
    'TECH_MAPPING'
]
