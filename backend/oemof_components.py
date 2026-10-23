import pandas as pd
from oemof import solph
from oemof.tools import economics
from backend.price_units import price_series_in_eur_per_kwh, DEFAULT_PRICE_UNIT


# function to calculate epc
def calculate_epc(capex, opex, lifetime, interest_rate):
    epc_capex = economics.annuity(capex=capex, n=lifetime, wacc=interest_rate / 100)
    fixed_opex_per_year = opex * capex / 100
    return epc_capex + fixed_opex_per_year


# create a function to distinguish dispatch or investment mode
def get_investment(cfg):
    mode = cfg.get("mode", "fixed")

    if mode == "fixed":
        capacity = cfg.get("capacity")

        # ensure that fixed mode needs a capacity input from user
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
        raise ValueError(
            f"Invalid mode '{mode}'. Allowed: 'fixed', 'invest'"
        )


def add_demand(es, buses, cfg, input_data):
    timeindex = input_data["timeindex"]

    profile_key = cfg.get("profile_key", "electricity_demand")
    profile_data = input_data.get(profile_key)

    if profile_data is None:
        raise ValueError(f"Missing demand profile: {profile_key}")

    demand_series = align_timeseries(profile_data, timeindex, profile_key)

    es.add(
        solph.components.Sink(
            label=cfg.get("label", "demand"),
            inputs={
                buses[cfg["bus"]]: solph.Flow(
                    fix=demand_series,
                    nominal_capacity=cfg.get("scaling_factor")
                )
            }
        )
    )


def add_heat_demand(es, buses, cfg, input_data):
    timeindex = input_data["timeindex"]

    profile_key = cfg.get("profile_key", "heat_demand")
    profile_data = input_data.get(profile_key)

    if profile_data is None:
        raise ValueError(f"Missing demand profile: {profile_key}")

    heat_series = align_timeseries(profile_data, timeindex, profile_key)

    es.add(
        solph.components.Sink(
            label=cfg.get("label", "heat_demand"),
            inputs={
                buses[cfg["bus"]]: solph.Flow(
                    fix=heat_series,
                    nominal_capacity=cfg.get("scaling_factor")
                )
            }
        )
    )


def align_timeseries(values, timeindex, name="time series"):
    """Turn a list of values into a pandas Series on the model's time index.

    - non-numeric or empty (NaN) values raise a ValueError
    - a series shorter than the time index raises a ValueError
    - a longer series is cut to the length of the time index
    """

    try:
        numeric = pd.Series(values, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(f"[{name}] the time series contains non-numeric values.")

    if numeric.isna().any():
        raise ValueError(f"[{name}] the time series contains empty values (NaN).")

    n_steps = len(timeindex)

    if len(numeric) < n_steps:
        raise ValueError(
            f"[{name}] the time series has {len(numeric)} values, but the model "
            f"needs {n_steps}. Upload a longer series or shorten the time range."
        )

    return pd.Series(numeric.values[:n_steps], index=timeindex)


# grid import
def add_grid_import(es, buses, cfg, input_data):
    # electricity price: constant (EUR/kWh) or time series in the chosen unit
    if cfg.get("price_mode", "constant") == "timeseries":

        series = cfg.get("price_series")
        if series is None:
            raise ValueError("[grid] price mode is 'timeseries', but no price series was uploaded.")

        prices = price_series_in_eur_per_kwh(series, cfg.get("price_unit", DEFAULT_PRICE_UNIT))
        variable_costs = align_timeseries(prices, input_data["timeindex"], "grid price")

    else:
        variable_costs = cfg.get("variable_costs")

    grid = solph.components.Source(
        label="grid_import",
        outputs={
            buses[cfg["bus"]]: solph.Flow(
                variable_costs=variable_costs
            )
        }
    )

    es.add(grid)


# grid feed-in
def add_grid_feedin(es, buses, cfg, input_data):
    feedin = solph.components.Sink(
        label="grid_feedin",
        inputs={
            buses[cfg["bus"]]: solph.Flow(
                variable_costs=-cfg.get("feedin_tariff")
            )
        }
    )

    es.add(feedin)


# source with a fixed time profile: output = profile * installed capacity
# (shared by pv and wind)
def add_profile_source(es, buses, cfg, input_data, label, display_name, default_profile_key):
    profile_key = cfg.get("profile_key", default_profile_key)

    if profile_key not in input_data:
        raise ValueError(
            f"{display_name} profile '{profile_key}' not found in input_data"
        )

    series = align_timeseries(input_data[profile_key], input_data["timeindex"], display_name)

    nominal_capacity = get_investment(cfg)

    source = solph.components.Source(
        label=label,
        outputs={
            buses[cfg["bus"]]: solph.Flow(
                fix=series,
                nominal_capacity=nominal_capacity
            )
        }
    )

    es.add(source)


# add pv
def add_pv(es, buses, cfg, input_data):
    add_profile_source(
        es, buses, cfg, input_data,
        label="pv", display_name="PV", default_profile_key="pv"
    )


# add wind turbine
def add_wind(es, buses, cfg, input_data):
    add_profile_source(
        es, buses, cfg, input_data,
        label="wind", display_name="Wind", default_profile_key="wind"
    )


# add gas import
def add_gas_import(es, buses, cfg, input_data):
    es.add(
        solph.components.Source(
            label="gas_import",
            outputs={
                buses[cfg["bus"]]: solph.Flow(
                    variable_costs=cfg.get("variable_costs")
                )
            }
        )
    )


# add gas boiler
def add_gas_boiler(es, buses, cfg, input_data):
    nominal_capacity = get_investment(cfg)

    boiler = solph.components.Converter(
        label="gas_boiler",
        inputs={
            buses[cfg["fuel_bus"]]: solph.Flow()
        },
        outputs={
            buses[cfg["heat_bus"]]: solph.Flow(
                nominal_capacity=nominal_capacity
            )
        },
        conversion_factors={
            buses[cfg["heat_bus"]]: cfg.get("efficiency")
        }
    )

    es.add(boiler)


# add heat pump
def add_heat_pump(es, buses, cfg, input_data):
    nominal_capacity = get_investment(cfg)

    # cop handling
    cop_mode = cfg.get("cop_mode", "constant")

    if cop_mode == "constant":
        cop = cfg.get("cop_value")

    elif cop_mode == "timeseries":
        profile = cfg.get("cop_series")

        if profile is None:
            raise ValueError("Missing COP time series in config")

        cop = align_timeseries(profile, input_data["timeindex"], "heat_pump COP")

        if (cop <= 0).any():
            raise ValueError("[heat_pump] the COP time series must be greater than 0.")

    else:
        raise ValueError(f"Invalid COP mode: {cop_mode}")

    heat_pump = solph.components.Converter(
        label="heat_pump",

        inputs={buses["electricity_bus"]: solph.Flow()},

        outputs={
            buses["heat_bus"]: solph.Flow(
                nominal_capacity=nominal_capacity
            )
        },
        conversion_factors={
            buses["electricity_bus"]: 1 / cop
        }
    )

    es.add(heat_pump)


# add heating rod (electric heater: electricity -> heat)
# capacity = heat output in kW; efficiency = heat out / electricity in
def add_heating_rod(es, buses, cfg, input_data):
    nominal_capacity = get_investment(cfg)

    efficiency = cfg.get("efficiency")
    if efficiency is None or efficiency <= 0:
        raise ValueError("[heating_rod] efficiency must be greater than 0.")

    heating_rod = solph.components.Converter(
        label="heating_rod",
        inputs={buses[cfg["electricity_bus"]]: solph.Flow()},
        outputs={
            buses[cfg["heat_bus"]]: solph.Flow(
                nominal_capacity=nominal_capacity
            )
        },
        conversion_factors={buses[cfg["heat_bus"]]: efficiency}
    )

    es.add(heating_rod)


# add CHP plant (combined heat and power: gas -> electricity + heat)
# capacity = ELECTRICAL output in kW; heat output follows from the efficiencies:
# heat = electricity * efficiency_th / efficiency_el
def add_chp(es, buses, cfg, input_data):
    nominal_capacity = get_investment(cfg)

    eta_el = cfg.get("efficiency_el")
    eta_th = cfg.get("efficiency_th")

    if eta_el is None or eta_th is None or eta_el <= 0 or eta_th <= 0:
        raise ValueError("[chp] electrical and thermal efficiency must be greater than 0.")
    if eta_el + eta_th > 1:
        raise ValueError("[chp] electrical + thermal efficiency cannot be greater than 1.")

    chp = solph.components.Converter(
        label="chp",
        inputs={buses[cfg["fuel_bus"]]: solph.Flow()},
        outputs={
            buses[cfg["electricity_bus"]]: solph.Flow(
                nominal_capacity=nominal_capacity
            ),
            buses[cfg["heat_bus"]]: solph.Flow()
        },
        conversion_factors={
            buses[cfg["electricity_bus"]]: eta_el,
            buses[cfg["heat_bus"]]: eta_th
        }
    )

    es.add(chp)


def add_storage(es, buses, cfg, label):
    """Storage with limited charge and discharge power.

    The power is set by the C-rate (kW of power per kWh of capacity).
    With a C-rate of 0.5, a 10 kWh storage can be charged or discharged
    with at most 5 kW.
    """

    c_rate = cfg.get("c_rate")

    if c_rate is None or c_rate <= 0:
        raise ValueError(f"[{label}] the C-rate must be greater than 0.")

    capacity = get_investment(cfg)
    bus = buses[cfg["bus"]]

    if isinstance(capacity, solph.Investment):
        # invest mode: the power is linked to the invested capacity
        flow_in = solph.Flow(nominal_capacity=solph.Investment(ep_costs=0))
        flow_out = solph.Flow(nominal_capacity=solph.Investment(ep_costs=0))
        relations = {
            "invest_relation_input_capacity": c_rate,
            "invest_relation_output_capacity": c_rate,
        }
    else:
        # fixed mode: the power follows directly from the capacity
        flow_in = solph.Flow(nominal_capacity=capacity * c_rate)
        flow_out = solph.Flow(nominal_capacity=capacity * c_rate)
        relations = {}

    es.add(
        solph.components.GenericStorage(
            label=label,
            inputs={bus: flow_in},
            outputs={bus: flow_out},
            nominal_capacity=capacity,
            loss_rate=cfg.get("loss_rate"),
            inflow_conversion_factor=cfg.get("efficiency_charge"),
            outflow_conversion_factor=cfg.get("efficiency_discharge"),
            **relations,
        )
    )


# add battery
def add_battery(es, buses, cfg, input_data):
    add_storage(es, buses, cfg, "battery")


# add heat storage
def add_heat_storage(es, buses, cfg, input_data):
    add_storage(es, buses, cfg, "heat_storage")


# component registry
TECH_MAPPING = {
    "demand": add_demand,
    "heat_demand": add_heat_demand,
    "grid": add_grid_import,
    "grid_feedin": add_grid_feedin,
    "pv": add_pv,
    "wind": add_wind,
    "gas_import": add_gas_import,
    "gas_boiler": add_gas_boiler,
    "heat_pump": add_heat_pump,
    "heating_rod": add_heating_rod,
    "chp": add_chp,
    "battery": add_battery,
    "heat_storage": add_heat_storage
}