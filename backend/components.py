"""
Component creation functions for the energy system.
Separates the creation of oemof components from configuration logic.
"""

import pandas as pd
from oemof import solph
from oemof.tools import economics
from typing import Dict, Any, Optional, Callable

from .constants import TechnologyType, InvestmentMode
from .models import InputData


# Type alias for component creator functions
ComponentCreator = Callable[[solph.EnergySystem, Dict[str, solph.Bus], Dict[str, Any], InputData], None]


def calculate_epc(capex: float, opex: float, lifetime: float, interest_rate: float) -> float:
    """
    Calculate equivalent periodic costs (EPC) for investment.
    
    Args:
        capex: Capital expenditure (€/kW)
        opex: Fixed operational expenditure (% of CAPEX)
        lifetime: Lifetime in years
        interest_rate: Interest rate (%)
        
    Returns:
        Equivalent periodic costs (€/kW/year)
    """
    epc_capex = economics.annuity(capex=capex, n=lifetime, wacc=interest_rate / 100)
    fixed_opex_per_year = opex * capex / 100
    return epc_capex + fixed_opex_per_year


def get_investment(cfg: Dict[str, Any]) -> Any:
    """
    Get investment configuration (fixed capacity or Investment object).
    
    Args:
        cfg: Technology configuration dictionary
        
    Returns:
        float (fixed capacity) or solph.Investment object
        
    Raises:
        ValueError: If mode is invalid or fixed mode lacks capacity
    """
    mode = cfg.get("mode", "fixed")
    
    if mode == "fixed":
        capacity = cfg.get("capacity")
        
        if capacity is None or capacity <= 0:
            raise ValueError(
                f"[{cfg.get('type')}] fixed mode requires capacity > 0. "
                f"Please set a value in the UI."
            )
        
        return float(capacity)
    
    elif mode == "invest":
        ep_costs = calculate_epc(
            capex=cfg.get("capex"),
            opex=cfg.get("opex"),
            lifetime=cfg.get("lifetime"),
            interest_rate=cfg.get("interest_rate")
        )
        
        return solph.Investment(
            ep_costs=ep_costs,
            maximum=cfg.get("maximum", None)
        )
    
    else:
        raise ValueError(f"Invalid mode '{mode}'. Allowed: 'fixed', 'invest'")


def get_timeseries(
    cfg: Dict[str, Any], 
    input_data: InputData,
    timeindex: pd.DatetimeIndex,
    profile_key: Optional[str] = None
) -> pd.Series:
    """
    Get time series data and align it with the model timeindex.
    
    Args:
        cfg: Technology configuration
        input_data: Input data container
        timeindex: Model timeindex
        profile_key: Key to use for profile data (defaults to cfg.get("profile_key"))
        
    Returns:
        pandas Series aligned with timeindex
        
    Raises:
        ValueError: If profile data is missing
    """
    key = profile_key or cfg.get("profile_key")
    
    if key is None:
        raise ValueError(f"No profile_key specified in config for {cfg.get('type')}")
    
    profile_data = input_data.get(key)
    
    if profile_data is None:
        raise ValueError(f"Missing profile data: {key}")
    
    # Create series and align with timeindex
    series = pd.Series(profile_data)
    
    if len(series) != len(timeindex):
        # Try to align by reindexing
        aligned = series.reindex(timeindex)
        aligned = aligned.interpolate(limit_direction="both").fillna(0)
        return aligned
    
    return pd.Series(profile_data, index=timeindex[:len(profile_data)])


def create_sink(
    es: solph.EnergySystem,
    label: str,
    bus: solph.Bus,
    cfg: Dict[str, Any],
    input_data: InputData
) -> None:
    """Create a sink component (demand)."""
    timeindex = es.timeindex
    
    profile_key = cfg.get("profile_key", "electricity_demand")
    demand_series = get_timeseries(cfg, input_data, timeindex, profile_key)
    
    scaling_factor = cfg.get("scaling_factor", 1.0)
    
    es.add(
        solph.components.Sink(
            label=label,
            inputs={
                bus: solph.Flow(
                    fix=demand_series,
                    nominal_capacity=scaling_factor
                )
            }
        )
    )


def create_source(
    es: solph.EnergySystem,
    label: str,
    bus: solph.Bus,
    cfg: Dict[str, Any],
    input_data: InputData
) -> None:
    """Create a source component (grid import, PV, etc.)."""
    timeindex = es.timeindex
    
    # Check if it has a profile (like PV)
    if cfg.get("profile_key") and cfg.get("profile_key") in input_data:
        profile_series = get_timeseries(cfg, input_data, timeindex)
        nominal_capacity = get_investment(cfg)
        
        es.add(
            solph.components.Source(
                label=label,
                outputs={
                    bus: solph.Flow(
                        fix=profile_series,
                        nominal_capacity=nominal_capacity
                    )
                }
            )
        )
    else:
        # Simple source without profile (grid import)
        variable_costs = cfg.get("variable_costs", 0.0)
        
        es.add(
            solph.components.Source(
                label=label,
                outputs={
                    bus: solph.Flow(
                        variable_costs=variable_costs
                    )
                }
            )
        )


def create_converter(
    es: solph.EnergySystem,
    label: str,
    inputs: Dict[solph.Bus, solph.Flow],
    outputs: Dict[solph.Bus, solph.Flow],
    conversion_factors: Optional[Dict] = None
) -> None:
    """Create a converter component (gas boiler, heat pump)."""
    es.add(
        solph.components.Converter(
            label=label,
            inputs=inputs,
            outputs=outputs,
            conversion_factors=conversion_factors
        )
    )


def create_storage(
    es: solph.EnergySystem,
    label: str,
    bus: solph.Bus,
    cfg: Dict[str, Any]
) -> None:
    """Create a storage component (battery, heat storage)."""
    nominal_capacity = get_investment(cfg)
    
    es.add(
        solph.components.GenericStorage(
            label=label,
            inputs={bus: solph.Flow()},
            outputs={bus: solph.Flow()},
            nominal_capacity=nominal_capacity,
            loss_rate=cfg.get("loss_rate", 0.0),
            inflow_conversion_factor=cfg.get("efficiency_charge", 1.0),
            outflow_conversion_factor=cfg.get("efficiency_discharge", 1.0)
        )
    )


# Technology-specific component creators

def add_demand(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add electricity demand component."""
    bus = buses[cfg["bus"]]
    create_sink(es, "demand", bus, cfg, input_data)


def add_heat_demand(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add heat demand component."""
    bus = buses[cfg["bus"]]
    create_sink(es, "heat_demand", bus, cfg, input_data)


def add_grid_import(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add grid import component."""
    bus = buses[cfg["bus"]]
    create_source(es, "grid_import", bus, cfg, input_data)


def add_grid_feedin(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add grid feed-in component."""
    bus = buses[cfg["bus"]]
    
    es.add(
        solph.components.Sink(
            label="grid_feedin",
            inputs={
                bus: solph.Flow(
                    variable_costs=-cfg.get("feedin_tariff", 0.0)
                )
            }
        )
    )


def add_pv(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add PV component."""
    bus = buses[cfg["bus"]]
    create_source(es, "pv", bus, cfg, input_data)


def add_gas_import(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add gas import component."""
    bus = buses[cfg["bus"]]
    create_source(es, "gas_import", bus, cfg, input_data)


def add_gas_boiler(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add gas boiler component."""
    fuel_bus = buses[cfg["fuel_bus"]]
    heat_bus = buses[cfg["heat_bus"]]
    nominal_capacity = get_investment(cfg)
    
    create_converter(
        es=es,
        label="gas_boiler",
        inputs={fuel_bus: solph.Flow()},
        outputs={heat_bus: solph.Flow(nominal_capacity=nominal_capacity)},
        conversion_factors={heat_bus: cfg.get("efficiency", 0.9)}
    )


def add_heat_pump(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add heat pump component."""
    electricity_bus = buses[cfg.get("electricity_bus", "electricity_bus")]
    heat_bus = buses[cfg.get("heat_bus", "heat_bus")]
    nominal_capacity = get_investment(cfg)
    
    # COP handling
    cop_mode = cfg.get("cop_mode", "constant")
    
    if cop_mode == "constant":
        cop = cfg.get("cop_value", 3.5)
    elif cop_mode == "timeseries":
        profile = cfg.get("cop_series")
        if profile is None:
            raise ValueError("Missing COP time series in config")
        
        timeindex = es.timeindex
        cop = pd.Series(profile, index=timeindex[:len(profile)])
    else:
        raise ValueError(f"Invalid COP mode: {cop_mode}")
    
    create_converter(
        es=es,
        label="heat_pump",
        inputs={electricity_bus: solph.Flow()},
        outputs={heat_bus: solph.Flow(nominal_capacity=nominal_capacity)},
        conversion_factors={electricity_bus: 1 / cop}
    )


def add_battery(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add battery component."""
    bus = buses[cfg["bus"]]
    create_storage(es, "battery", bus, cfg)


def add_heat_storage(es: solph.EnergySystem, buses: Dict[str, solph.Bus], cfg: Dict[str, Any], input_data: InputData) -> None:
    """Add heat storage component."""
    bus = buses[cfg["bus"]]
    create_storage(es, "heat_storage", bus, cfg)


# Component registry
TECH_MAPPING: Dict[str, ComponentCreator] = {
    TechnologyType.DEMAND.value: add_demand,
    TechnologyType.HEAT_DEMAND.value: add_heat_demand,
    TechnologyType.GRID.value: add_grid_import,
    TechnologyType.GRID_FEEDIN.value: add_grid_feedin,
    TechnologyType.PV.value: add_pv,
    TechnologyType.BATTERY.value: add_battery,
    TechnologyType.HEAT_STORAGE.value: add_heat_storage,
    TechnologyType.GAS_IMPORT.value: add_gas_import,
    TechnologyType.GAS_BOILER.value: add_gas_boiler,
    TechnologyType.HEAT_PUMP.value: add_heat_pump
}
