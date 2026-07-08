"""
Constants and enums for the energy system webtool.
Centralizes magic strings and configuration values.
"""

from enum import Enum
from typing import Dict, Any


class BusType(Enum):
    """Standard bus types in the energy system."""
    ELECTRICITY = "electricity"
    HEAT = "heat"
    GAS = "gas"


class TechnologyType(Enum):
    """Supported technology types."""
    DEMAND = "demand"
    HEAT_DEMAND = "heat_demand"
    GRID = "grid"
    GRID_FEEDIN = "grid_feedin"
    PV = "pv"
    BATTERY = "battery"
    HEAT_STORAGE = "heat_storage"
    GAS_IMPORT = "gas_import"
    GAS_BOILER = "gas_boiler"
    HEAT_PUMP = "heat_pump"


class InvestmentMode(Enum):
    """Investment modes for technologies."""
    FIXED = "fixed"
    INVEST = "invest"


class COPMode(Enum):
    """COP (Coefficient of Performance) modes for heat pumps."""
    CONSTANT = "constant"
    TIMESERIES = "timeseries"


# Default bus configuration
DEFAULT_BUSES: Dict[str, Dict[str, str]] = {
    "electricity_bus": {"label": BusType.ELECTRICITY.value},
    "heat_bus": {"label": BusType.HEAT.value},
    "gas_bus": {"label": BusType.GAS.value}
}

# Bus ID to label mapping
BUS_ID_TO_LABEL: Dict[str, str] = {
    "electricity_bus": BusType.ELECTRICITY.value,
    "heat_bus": BusType.HEAT.value,
    "gas_bus": BusType.GAS.value
}

# Label to bus ID mapping
BUS_LABEL_TO_ID: Dict[str, str] = {
    BusType.ELECTRICITY.value: "electricity_bus",
    BusType.HEAT.value: "heat_bus",
    BusType.GAS.value: "gas_bus"
}

# Technology type to bus mapping (default assignments)
TECH_TYPE_TO_BUS: Dict[str, str] = {
    TechnologyType.DEMAND.value: "electricity_bus",
    TechnologyType.HEAT_DEMAND.value: "heat_bus",
    TechnologyType.GRID.value: "electricity_bus",
    TechnologyType.GRID_FEEDIN.value: "electricity_bus",
    TechnologyType.PV.value: "electricity_bus",
    TechnologyType.BATTERY.value: "electricity_bus",
    TechnologyType.GAS_IMPORT.value: "gas_bus",
    TechnologyType.GAS_BOILER.value: "gas_bus",
    TechnologyType.HEAT_STORAGE.value: "heat_bus",
    TechnologyType.HEAT_PUMP.value: "electricity_bus"
}

# Solver configuration defaults
DEFAULT_SOLVER_CONFIG: Dict[str, Any] = {
    "name": "cbc",
    "tee": False
}

# Time configuration defaults
DEFAULT_TIME_CONFIG: Dict[str, Any] = {
    "start_date": "2021-01-01",
    "days": 365,
    "resolution": "1h"
}

# Frequency mapping for time resolution
FREQUENCY_MAP: Dict[str, int] = {
    "1h": 24,
    "15min": 96
}
