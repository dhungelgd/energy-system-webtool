"""
Configuration factory for building technology configurations.
Separates configuration building logic from component creation.
"""

from typing import Dict, Any, Optional, Callable
from dataclasses import asdict

from .constants import (
    TechnologyType, 
    InvestmentMode, 
    COPMode,
    DEFAULT_BUSES,
    TECH_TYPE_TO_BUS
)
from .models import (
    SystemConfig, 
    SolverConfig, 
    BusConfig,
    TechnologyConfig,
    DemandConfig,
    HeatDemandConfig,
    GridConfig,
    GridFeedinConfig,
    PVConfig,
    BatteryConfig,
    HeatStorageConfig,
    GasImportConfig,
    GasBoilerConfig,
    HeatPumpConfig,
    InvestmentConfig,
    InputData
)


# Type alias for config builder functions
ConfigBuilder = Callable[[Dict[str, Any], InputData], TechnologyConfig]


def build_investment_config(tech_inputs: Dict[str, Any]) -> InvestmentConfig:
    """Build investment configuration from tech inputs."""
    inputs = tech_inputs or {}
    
    mode_str = inputs.get("mode", "fixed")
    mode = InvestmentMode.FIXED if mode_str == "fixed" else InvestmentMode.INVEST
    
    return InvestmentConfig(
        mode=mode,
        capacity=inputs.get("capacity"),
        capex=inputs.get("capex"),
        opex=inputs.get("opex"),
        lifetime=inputs.get("lifetime"),
        interest_rate=inputs.get("interest_rate"),
        maximum=inputs.get("maximum")
    )


def build_demand_config(tech_inputs: Dict[str, Any], input_data: InputData) -> DemandConfig:
    """Build demand configuration."""
    demand_inputs = tech_inputs.get("demand", {}) if tech_inputs else {}
    
    return DemandConfig(
        type=TechnologyType.DEMAND,
        bus="electricity_bus",
        scaling_factor=demand_inputs.get("scaling_factor", 30000.0),
        profile_key="electricity_demand"
    )


def build_heat_demand_config(tech_inputs: Dict[str, Any], input_data: InputData) -> HeatDemandConfig:
    """Build heat demand configuration."""
    heat_inputs = tech_inputs.get("heat_demand", {}) if tech_inputs else {}
    
    return HeatDemandConfig(
        type=TechnologyType.HEAT_DEMAND,
        bus="heat_bus",
        scaling_factor=heat_inputs.get("scaling_factor", 90000.0),
        profile_key="heat_demand"
    )


def build_grid_config(tech_inputs: Dict[str, Any], input_data: InputData) -> GridConfig:
    """Build grid configuration."""
    grid_inputs = tech_inputs.get("grid", {}) if tech_inputs else {}
    
    return GridConfig(
        type=TechnologyType.GRID,
        bus="electricity_bus",
        variable_costs=grid_inputs.get("variable_costs", 0.3)
    )


def build_grid_feedin_config(tech_inputs: Dict[str, Any], input_data: InputData) -> GridFeedinConfig:
    """Build grid feed-in configuration."""
    feedin_inputs = tech_inputs.get("grid_feedin", {}) if tech_inputs else {}
    
    return GridFeedinConfig(
        type=TechnologyType.GRID_FEEDIN,
        bus="electricity_bus",
        feedin_tariff=feedin_inputs.get("feedin_tariff", 0.078)
    )


def build_pv_config(tech_inputs: Dict[str, Any], input_data: InputData) -> PVConfig:
    """Build PV configuration."""
    pv_inputs = tech_inputs.get("pv", {}) if tech_inputs else {}
    investment = build_investment_config(pv_inputs)
    
    return PVConfig(
        type=TechnologyType.PV,
        bus="electricity_bus",
        investment=investment,
        profile_key=pv_inputs.get("profile_key", "pv")
    )


def build_battery_config(tech_inputs: Dict[str, Any], input_data: InputData) -> BatteryConfig:
    """Build battery configuration."""
    bat_inputs = tech_inputs.get("battery", {}) if tech_inputs else {}
    investment = build_investment_config(bat_inputs)
    
    return BatteryConfig(
        type=TechnologyType.BATTERY,
        bus="electricity_bus",
        investment=investment,
        loss_rate=bat_inputs.get("loss_rate", 0.001),
        efficiency_charge=bat_inputs.get("efficiency_charge", 0.95),
        efficiency_discharge=bat_inputs.get("efficiency_discharge", 0.95)
    )


def build_heat_storage_config(tech_inputs: Dict[str, Any], input_data: InputData) -> HeatStorageConfig:
    """Build heat storage configuration."""
    hs_inputs = tech_inputs.get("heat_storage", {}) if tech_inputs else {}
    investment = build_investment_config(hs_inputs)
    
    return HeatStorageConfig(
        type=TechnologyType.HEAT_STORAGE,
        bus="heat_bus",
        investment=investment,
        loss_rate=hs_inputs.get("loss_rate", 0.001),
        efficiency_charge=hs_inputs.get("efficiency_charge", 0.95),
        efficiency_discharge=hs_inputs.get("efficiency_discharge", 0.95)
    )


def build_gas_import_config(tech_inputs: Dict[str, Any], input_data: InputData) -> GasImportConfig:
    """Build gas import configuration."""
    gi_inputs = tech_inputs.get("gas_import", {}) if tech_inputs else {}
    
    return GasImportConfig(
        type=TechnologyType.GAS_IMPORT,
        bus="gas_bus",
        variable_costs=gi_inputs.get("variable_costs", 0.10)
    )


def build_gas_boiler_config(tech_inputs: Dict[str, Any], input_data: InputData) -> GasBoilerConfig:
    """Build gas boiler configuration."""
    gb_inputs = tech_inputs.get("gas_boiler", {}) if tech_inputs else {}
    investment = build_investment_config(gb_inputs)
    
    return GasBoilerConfig(
        type=TechnologyType.GAS_BOILER,
        fuel_bus="gas_bus",
        heat_bus="heat_bus",
        investment=investment,
        efficiency=gb_inputs.get("efficiency", 0.9),
        variable_costs=gb_inputs.get("variable_costs")
    )


def build_heat_pump_config(tech_inputs: Dict[str, Any], input_data: InputData) -> HeatPumpConfig:
    """Build heat pump configuration."""
    hp_inputs = tech_inputs.get("heat_pump", {}) if tech_inputs else {}
    investment = build_investment_config(hp_inputs)
    
    cop_mode_str = hp_inputs.get("cop_mode", "constant")
    cop_mode = COPMode.CONSTANT if cop_mode_str == "constant" else COPMode.TIMESERIES
    
    return HeatPumpConfig(
        type=TechnologyType.HEAT_PUMP,
        electricity_bus="electricity_bus",
        heat_bus="heat_bus",
        investment=investment,
        cop_mode=cop_mode,
        cop_value=hp_inputs.get("cop_value", 3.5),
        cop_series=input_data.get("cop_series") if cop_mode == COPMode.TIMESERIES else None,
        variable_costs=hp_inputs.get("variable_costs")
    )


# Registry of configuration builders
CONFIG_BUILDER_REGISTRY: Dict[str, ConfigBuilder] = {
    TechnologyType.DEMAND.value: build_demand_config,
    TechnologyType.HEAT_DEMAND.value: build_heat_demand_config,
    TechnologyType.GRID.value: build_grid_config,
    TechnologyType.GRID_FEEDIN.value: build_grid_feedin_config,
    TechnologyType.PV.value: build_pv_config,
    TechnologyType.BATTERY.value: build_battery_config,
    TechnologyType.HEAT_STORAGE.value: build_heat_storage_config,
    TechnologyType.GAS_IMPORT.value: build_gas_import_config,
    TechnologyType.GAS_BOILER.value: build_gas_boiler_config,
    TechnologyType.HEAT_PUMP.value: build_heat_pump_config
}


def build_bus_configs() -> Dict[str, BusConfig]:
    """Build default bus configurations."""
    return {
        bus_id: BusConfig(label=bus_data["label"])
        for bus_id, bus_data in DEFAULT_BUSES.items()
    }


def build_system_config(
    selected_techs: list,
    tech_inputs: Dict[str, Any],
    input_data: InputData,
    solver_cfg: SolverConfig
) -> SystemConfig:
    """
    Build complete system configuration from user inputs.
    
    Args:
        selected_techs: List of selected technology types
        tech_inputs: Dictionary of technology inputs from UI
        input_data: Input data (time series, profiles, etc.)
        solver_cfg: Solver configuration
        
    Returns:
        SystemConfig: Complete system configuration
    """
    # Build buses
    buses = build_bus_configs()
    
    # Build technologies
    technologies: Dict[str, TechnologyConfig] = {}
    
    for tech_type in selected_techs:
        if tech_type not in CONFIG_BUILDER_REGISTRY:
            raise ValueError(f"Unknown technology type: {tech_type}")
        
        builder = CONFIG_BUILDER_REGISTRY[tech_type]
        config = builder(tech_inputs, input_data)
        technologies[tech_type] = config
    
    # Build system config
    return SystemConfig(
        buses=buses,
        technologies=technologies,
        solver=solver_cfg,
        time=None  # Time config is handled separately
    )


def convert_config_to_dict(config: SystemConfig) -> Dict[str, Any]:
    """
    Convert SystemConfig to dictionary format for backward compatibility.
    
    This allows the new models to work with existing code that expects dicts.
    """
    result = {
        "buses": {bus_id: {"label": bus.label} for bus_id, bus in config.buses.items()},
        "technologies": {},
        "solver": {"name": config.solver.name, "tee": config.solver.tee}
    }
    
    for tech_id, tech_config in config.technologies.items():
        tech_dict = {
            "type": tech_config.type.value,
        }
        
        # Add common fields
        if hasattr(tech_config, 'bus') and tech_config.bus:
            tech_dict["bus"] = tech_config.bus
        if hasattr(tech_config, 'label') and tech_config.label:
            tech_dict["label"] = tech_config.label
        if hasattr(tech_config, 'profile_key') and tech_config.profile_key:
            tech_dict["profile_key"] = tech_config.profile_key
        if hasattr(tech_config, 'scaling_factor') and tech_config.scaling_factor:
            tech_dict["scaling_factor"] = tech_config.scaling_factor
        if hasattr(tech_config, 'variable_costs') and tech_config.variable_costs:
            tech_dict["variable_costs"] = tech_config.variable_costs
        if hasattr(tech_config, 'feedin_tariff') and tech_config.feedin_tariff:
            tech_dict["feedin_tariff"] = tech_config.feedin_tariff
        
        # Add investment fields
        if hasattr(tech_config, 'investment'):
            inv = tech_config.investment
            tech_dict["mode"] = inv.mode.value
            if inv.capacity is not None:
                tech_dict["capacity"] = inv.capacity
            if inv.capex is not None:
                tech_dict["capex"] = inv.capex
            if inv.opex is not None:
                tech_dict["opex"] = inv.opex
            if inv.lifetime is not None:
                tech_dict["lifetime"] = inv.lifetime
            if inv.interest_rate is not None:
                tech_dict["interest_rate"] = inv.interest_rate
            if inv.maximum is not None:
                tech_dict["maximum"] = inv.maximum
        
        # Add technology-specific fields
        if isinstance(tech_config, (BatteryConfig, HeatStorageConfig)):
            tech_dict["loss_rate"] = tech_config.loss_rate
            tech_dict["efficiency_charge"] = tech_config.efficiency_charge
            tech_dict["efficiency_discharge"] = tech_config.efficiency_discharge
        
        if isinstance(tech_config, GasBoilerConfig):
            tech_dict["fuel_bus"] = tech_config.fuel_bus
            tech_dict["heat_bus"] = tech_config.heat_bus
            tech_dict["efficiency"] = tech_config.efficiency
        
        if isinstance(tech_config, HeatPumpConfig):
            tech_dict["cop_mode"] = tech_config.cop_mode.value
            if tech_config.cop_value:
                tech_dict["cop_value"] = tech_config.cop_value
            if tech_config.cop_series:
                tech_dict["cop_series"] = tech_config.cop_series
        
        result["technologies"][tech_id] = tech_dict
    
    return result
