"""
Model builder for creating oemof energy system models.
Uses configuration from config_factory and components from components module.
"""

from oemof.solph import EnergySystem, Bus
from typing import Dict, Any

from .components import TECH_MAPPING
from .config_factory import convert_config_to_dict
from .models import SystemConfig, InputData


def build_energy_system(config: SystemConfig, input_data: InputData) -> EnergySystem:
    """
    Build an oemof EnergySystem from configuration.
    
    Args:
        config: System configuration (SystemConfig or dict)
        input_data: Input data container
        
    Returns:
        EnergySystem: Configured energy system
    """
    # Convert SystemConfig to dict if needed for backward compatibility
    if hasattr(config, 'buses'):
        config_dict = convert_config_to_dict(config)
    else:
        config_dict = config
    
    # Create a timeindex
    timeindex = input_data.get("timeindex")
    if timeindex is None:
        raise ValueError("timeindex is required in input_data")
    
    # Initialize the energy system
    es = EnergySystem(timeindex=timeindex)
    
    # Create buses
    bus_map = {}
    for bus_id, bus_data in config_dict["buses"].items():
        bus = Bus(label=bus_data["label"])
        es.add(bus)
        bus_map[bus_id] = bus
    
    # Add components
    for tech_id, tech in config_dict["technologies"].items():
        tech_type = tech["type"]
        
        if tech_type not in TECH_MAPPING:
            raise ValueError(f"Unknown technology type: {tech_type}")
        
        TECH_MAPPING[tech_type](
            es=es,
            buses=bus_map,
            cfg=tech,
            input_data=input_data
        )
    
    return es


# Backward compatibility function
build_model = build_energy_system
