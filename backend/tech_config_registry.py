"""
Legacy technology configuration registry - DEPRECATED.

This module is deprecated. Use backend.config_factory instead.
The functions in this module are kept for backward compatibility only.
"""

import warnings
from typing import Dict, Any, Callable

from .config_factory import (
    build_demand_config,
    build_heat_demand_config,
    build_grid_config,
    build_grid_feedin_config,
    build_pv_config,
    build_battery_config,
    build_heat_storage_config,
    build_gas_import_config,
    build_gas_boiler_config,
    build_heat_pump_config,
    CONFIG_BUILDER_REGISTRY
)

# Deprecation warning
warnings.warn(
    "backend.tech_config_registry is deprecated. Use backend.config_factory instead.",
    DeprecationWarning,
    stacklevel=2
)

# Legacy function names for backward compatibility

def demand_config(tech_inputs=None, input_data=None, **kwargs):
    """Legacy demand config - use build_demand_config instead."""
    from .models import InputData
    input_data_obj = InputData(**input_data) if input_data else InputData()
    config = build_demand_config(tech_inputs, input_data_obj)
    return config.__dict__


def heat_demand_config(tech_inputs=None, input_data=None, **kwargs):
    """Legacy heat demand config - use build_heat_demand_config instead."""
    from .models import InputData
    input_data_obj = InputData(**input_data) if input_data else InputData()
    config = build_heat_demand_config(tech_inputs, input_data_obj)
    return config.__dict__


def grid_config(tech_inputs=None, **kwargs):
    """Legacy grid config - use build_grid_config instead."""
    from .models import InputData
    config = build_grid_config(tech_inputs, InputData())
    return config.__dict__


def grid_feedin_config(tech_inputs=None, input_data=None, **kwargs):
    """Legacy grid feedin config - use build_grid_feedin_config instead."""
    from .models import InputData
    input_data_obj = InputData(**input_data) if input_data else InputData()
    config = build_grid_feedin_config(tech_inputs, input_data_obj)
    return config.__dict__


def pv_config(tech_inputs=None, input_data=None, **kwargs):
    """Legacy PV config - use build_pv_config instead."""
    from .models import InputData
    input_data_obj = InputData(**input_data) if input_data else InputData()
    config = build_pv_config(tech_inputs, input_data_obj)
    return config.__dict__


def battery_config(tech_inputs=None, **kwargs):
    """Legacy battery config - use build_battery_config instead."""
    from .models import InputData
    config = build_battery_config(tech_inputs, InputData())
    return config.__dict__


def heat_storage_config(tech_inputs=None, **kwargs):
    """Legacy heat storage config - use build_heat_storage_config instead."""
    from .models import InputData
    config = build_heat_storage_config(tech_inputs, InputData())
    return config.__dict__


def gas_import_config(tech_inputs=None, input_data=None, **kwargs):
    """Legacy gas import config - use build_gas_import_config instead."""
    from .models import InputData
    input_data_obj = InputData(**input_data) if input_data else InputData()
    config = build_gas_import_config(tech_inputs, input_data_obj)
    return config.__dict__


def gas_boiler_config(tech_inputs=None, input_data=None, **kwargs):
    """Legacy gas boiler config - use build_gas_boiler_config instead."""
    from .models import InputData
    input_data_obj = InputData(**input_data) if input_data else InputData()
    config = build_gas_boiler_config(tech_inputs, input_data_obj)
    return config.__dict__


def heat_pump_config(tech_inputs=None, input_data=None, **kwargs):
    """Legacy heat pump config - use build_heat_pump_config instead."""
    from .models import InputData
    input_data_obj = InputData(**input_data) if input_data else InputData()
    config = build_heat_pump_config(tech_inputs, input_data_obj)
    return config.__dict__


# Legacy registry
TECH_CONFIG_REGISTRY = {
    "demand": demand_config,
    "heat_demand": heat_demand_config,
    "grid": grid_config,
    "grid_feedin": grid_feedin_config,
    "pv": pv_config,
    "battery": battery_config,
    "gas_import": gas_import_config,
    "gas_boiler": gas_boiler_config,
    "heat_pump": heat_pump_config,
    "heat_storage": heat_storage_config
}
