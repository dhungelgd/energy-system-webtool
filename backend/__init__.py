"""
Backend package for the energy system webtool.

This package contains:
- models: Data models and schemas
- constants: Enums and constants
- config_factory: Configuration building logic
- config_builder: Backward-compatible configuration builder
- components: Component creation functions
- model_builder: Energy system model builder
- scenario_runner: Scenario execution logic
- plotting: Visualization functions
- postprocessing: Result processing functions
- oemof_components: Legacy component functions (deprecated)
- tech_config_registry: Legacy config registry (deprecated)
- input_schema: Legacy input schemas (deprecated)
"""

from .models import (
    SystemConfig,
    SolverConfig,
    TimeConfig,
    BusConfig,
    TechnologyConfig,
    InvestmentConfig,
    InputData,
    SimulationResults
)

from .constants import (
    BusType,
    TechnologyType,
    InvestmentMode,
    COPMode,
    DEFAULT_BUSES,
    BUS_ID_TO_LABEL,
    BUS_LABEL_TO_ID
)

from .config_factory import (
    build_system_config,
    convert_config_to_dict,
    CONFIG_BUILDER_REGISTRY
)

from .config_builder import build_config

from .components import TECH_MAPPING

from .model_builder import build_energy_system, build_model

from .scenario_runner import run_scenario

# Re-export for backward compatibility
__all__ = [
    # Models
    'SystemConfig',
    'SolverConfig',
    'TimeConfig',
    'BusConfig',
    'TechnologyConfig',
    'InvestmentConfig',
    'InputData',
    'SimulationResults',
    
    # Constants
    'BusType',
    'TechnologyType',
    'InvestmentMode',
    'COPMode',
    'DEFAULT_BUSES',
    'BUS_ID_TO_LABEL',
    'BUS_LABEL_TO_ID',
    
    # Config
    'build_system_config',
    'convert_config_to_dict',
    'build_config',
    'CONFIG_BUILDER_REGISTRY',
    
    # Components
    'TECH_MAPPING',
    
    # Model building
    'build_energy_system',
    'build_model',
    
    # Scenario running
    'run_scenario'
]
