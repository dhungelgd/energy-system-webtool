"""
Data models for the energy system webtool.
Defines the structure of configurations and inputs.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd

from .constants import BusType, TechnologyType, InvestmentMode, COPMode


@dataclass
class SolverConfig:
    """Configuration for the optimization solver."""
    name: str = "cbc"
    tee: bool = False


@dataclass
class TimeConfig:
    """Time configuration for the energy system."""
    start_date: datetime = None
    periods: int = 365 * 24  # Default: 365 days at hourly resolution
    frequency: str = "1h"
    
    @property
    def timeindex(self) -> pd.DatetimeIndex:
        """Generate pandas DatetimeIndex from configuration."""
        if self.start_date is None:
            self.start_date = pd.to_datetime("2021-01-01")
        return pd.date_range(
            start=self.start_date,
            periods=self.periods,
            freq=self.frequency
        )


@dataclass
class BusConfig:
    """Configuration for an energy bus."""
    label: str
    type: Optional[BusType] = None


@dataclass
class InvestmentConfig:
    """Configuration for investment parameters."""
    mode: InvestmentMode = InvestmentMode.FIXED
    capacity: Optional[float] = None
    capex: Optional[float] = None  # Capital expenditure (€/kW)
    opex: Optional[float] = None  # Operational expenditure (% of CAPEX)
    lifetime: Optional[float] = None  # years
    interest_rate: Optional[float] = None  # %
    maximum: Optional[float] = None  # Maximum capacity


@dataclass
class TechnologyConfig:
    """Base configuration for a technology."""
    type: TechnologyType
    label: Optional[str] = None
    bus: Optional[str] = None
    
    # Investment parameters
    investment: InvestmentConfig = field(default_factory=InvestmentConfig)
    
    # Common parameters
    variable_costs: Optional[float] = None
    
    # For components with profiles
    profile_key: Optional[str] = None
    scaling_factor: Optional[float] = None


@dataclass
class DemandConfig(TechnologyConfig):
    """Configuration for electricity demand."""
    type: TechnologyType = TechnologyType.DEMAND
    bus: str = "electricity_bus"
    profile_key: str = "electricity_demand"
    scaling_factor: float = 1.0


@dataclass
class HeatDemandConfig(TechnologyConfig):
    """Configuration for heat demand."""
    type: TechnologyType = TechnologyType.HEAT_DEMAND
    bus: str = "heat_bus"
    profile_key: str = "heat_demand"
    scaling_factor: float = 1.0


@dataclass
class GridConfig(TechnologyConfig):
    """Configuration for grid connection."""
    type: TechnologyType = TechnologyType.GRID
    bus: str = "electricity_bus"
    variable_costs: float = 0.3


@dataclass
class GridFeedinConfig(TechnologyConfig):
    """Configuration for grid feed-in."""
    type: TechnologyType = TechnologyType.GRID_FEEDIN
    bus: str = "electricity_bus"
    feedin_tariff: float = 0.08


@dataclass
class PVConfig(TechnologyConfig):
    """Configuration for PV system."""
    type: TechnologyType = TechnologyType.PV
    bus: str = "electricity_bus"
    profile_key: str = "pv"
    efficiency: Optional[float] = None


@dataclass
class BatteryConfig(TechnologyConfig):
    """Configuration for battery storage."""
    type: TechnologyType = TechnologyType.BATTERY
    bus: str = "electricity_bus"
    loss_rate: float = 0.001
    efficiency_charge: float = 0.95
    efficiency_discharge: float = 0.95


@dataclass
class HeatStorageConfig(TechnologyConfig):
    """Configuration for heat storage."""
    type: TechnologyType = TechnologyType.HEAT_STORAGE
    bus: str = "heat_bus"
    loss_rate: float = 0.001
    efficiency_charge: float = 0.95
    efficiency_discharge: float = 0.95


@dataclass
class GasImportConfig(TechnologyConfig):
    """Configuration for gas import."""
    type: TechnologyType = TechnologyType.GAS_IMPORT
    bus: str = "gas_bus"
    variable_costs: float = 0.10


@dataclass
class GasBoilerConfig(TechnologyConfig):
    """Configuration for gas boiler."""
    type: TechnologyType = TechnologyType.GAS_BOILER
    fuel_bus: str = "gas_bus"
    heat_bus: str = "heat_bus"
    efficiency: float = 0.9


@dataclass
class HeatPumpConfig(TechnologyConfig):
    """Configuration for heat pump."""
    type: TechnologyType = TechnologyType.HEAT_PUMP
    electricity_bus: str = "electricity_bus"
    heat_bus: str = "heat_bus"
    cop_mode: COPMode = COPMode.CONSTANT
    cop_value: float = 3.5
    cop_series: Optional[List[float]] = None


@dataclass
class SystemConfig:
    """Complete system configuration."""
    buses: Dict[str, BusConfig] = field(default_factory=dict)
    technologies: Dict[str, TechnologyConfig] = field(default_factory=dict)
    solver: SolverConfig = field(default_factory=SolverConfig)
    time: Optional[TimeConfig] = None


@dataclass
class InputData:
    """Container for input data (time series, profiles, etc.)."""
    timeindex: Optional[pd.DatetimeIndex] = None
    electricity_demand: Optional[List[float]] = None
    heat_demand: Optional[List[float]] = None
    pv: Optional[List[float]] = None
    cop_series: Optional[List[float]] = None
    
    def get(self, key: str, default=None):
        """Get input data by key."""
        return getattr(self, key, default)
    
    def __getitem__(self, key: str):
        """Allow dictionary-style access."""
        return getattr(self, key)
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists."""
        return hasattr(self, key)


@dataclass
class SimulationResults:
    """Container for simulation results."""
    energy_system: Any = None  # oemof EnergySystem
    results: Any = None  # oemof processing results
    meta_results: Dict[str, Any] = field(default_factory=dict)
    investment_capacities: Dict[str, float] = field(default_factory=dict)
    flows: Dict[str, pd.DataFrame] = field(default_factory=dict)
