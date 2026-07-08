"""
Configuration builder for backward compatibility.
Uses the new config_factory under the hood.
"""

from typing import Dict, Any
from .config_factory import build_system_config, convert_config_to_dict
from .models import SystemConfig, InputData, SolverConfig


def build_config(
    selected_techs: list,
    tech_inputs: Dict[str, Any],
    input_data: Dict[str, Any],
    solver_cfg: SolverConfig
) -> Dict[str, Any]:
    """
    Build configuration dictionary from user inputs (backward compatible).
    
    Args:
        selected_techs: List of selected technology types
        tech_inputs: Dictionary of technology inputs from UI
        input_data: Input data dictionary
        solver_cfg: Solver configuration
        
    Returns:
        Dictionary configuration for the energy system
    """
    # Convert input_data dict to InputData object
    input_data_obj = InputData(
        timeindex=input_data.get("timeindex"),
        electricity_demand=input_data.get("electricity_demand"),
        heat_demand=input_data.get("heat_demand"),
        pv=input_data.get("pv"),
        cop_series=input_data.get("cop_series")
    )
    
    # Build system config using new factory
    system_config = build_system_config(
        selected_techs=selected_techs,
        tech_inputs=tech_inputs,
        input_data=input_data_obj,
        solver_cfg=solver_cfg
    )
    
    # Convert to dictionary for backward compatibility
    return convert_config_to_dict(system_config)


# Also provide the new function for forward compatibility
def build_system_config_new(
    selected_techs: list,
    tech_inputs: Dict[str, Any],
    input_data: Dict[str, Any],
    solver_cfg: SolverConfig
) -> SystemConfig:
    """
    Build SystemConfig object (new interface).
    
    Args:
        selected_techs: List of selected technology types
        tech_inputs: Dictionary of technology inputs from UI
        input_data: Input data dictionary
        solver_cfg: Solver configuration
        
    Returns:
        SystemConfig: Structured system configuration
    """
    input_data_obj = InputData(
        timeindex=input_data.get("timeindex"),
        electricity_demand=input_data.get("electricity_demand"),
        heat_demand=input_data.get("heat_demand"),
        pv=input_data.get("pv"),
        cop_series=input_data.get("cop_series")
    )
    
    return build_system_config(
        selected_techs=selected_techs,
        tech_inputs=tech_inputs,
        input_data=input_data_obj,
        solver_cfg=solver_cfg
    )
