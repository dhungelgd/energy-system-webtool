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
    timeindex = es.timeindex

    profile_key = cfg.get("profile_key", "electricity_demand")
    profile_data = input_data.get(profile_key)

    if profile_data is None:
        raise ValueError(f"Missing demand profile: {profile_key}")

    demand_series = pd.Series(
        profile_data,
        index=timeindex[:len(profile_data)]
    )

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
    timeindex = es.timeindex

    profile_key = cfg.get("profile_key", "heat_demand")
    profile_data = input_data.get(profile_key)

    if profile_data is None:
        raise ValueError(f"Missing demand profile: {profile_key}")

    heat_series = pd.Series(
        profile_data,
        index=timeindex[:len(profile_data)]
    )

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


def align_timeseries(series, timeindex, strict=True):
    series = pd.Series(series)

    if len(series) != len(timeindex):

        if strict:
            raise ValueError(
                f"Time series length {len(series)} != model horizon {len(timeindex)}"
            )

        aligned = series.reindex(timeindex)
        aligned = aligned.interpolate(limit_direction="both").fillna(0)

        return aligned


# grid import
def add_grid_import(es, buses, cfg, input_data):
    # electricity price: constant (EUR/kWh) or time series in the chosen unit
    if cfg.get("price_mode", "constant") == "timeseries":

        series = cfg.get("price_series")
        if series is None:
            raise ValueError("[grid] price mode is 'timeseries', but no price series was uploaded.")

        prices = price_series_in_eur_per_kwh(series, cfg.get("price_unit", DEFAULT_PRICE_UNIT))

        horizon = len(es.timeindex)
        if len(prices) < horizon:
            raise ValueError(
                f"[grid] the price series has {len(prices)} values, but the model "
                f"needs {horizon}. Upload a longer series or shorten the time range."
            )
        if any(p != p for p in prices):  # NaN check
            raise ValueError("[grid] the price series contains empty values (NaN).")

        variable_costs = prices[:horizon]

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

    timeindex = es.timeindex

    profile = pd.Series(input_data[profile_key])

    series = pd.Series(
        profile.values,
        index=timeindex[:len(profile)]
    )

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

        timeindex = es.timeindex

        cop = pd.Series(
            profile,
            index=timeindex[:len(profile)]
        )

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


# add battery
def add_battery(es, buses, cfg, input_data):
    battery = solph.components.GenericStorage(
        label="battery",
        inputs={buses[cfg["bus"]]: solph.Flow()},
        outputs={buses[cfg["bus"]]: solph.Flow()},
        nominal_capacity=get_investment(cfg),
        loss_rate=cfg.get("loss_rate"),
        inflow_conversion_factor=cfg.get("efficiency_charge"),
        outflow_conversion_factor=cfg.get("efficiency_discharge")
    )

    es.add(battery)


# add heat storage
def add_heat_storage(es, buses, cfg, input_data):
    heat_storage = solph.components.GenericStorage(
        label="heat_storage",
        inputs={buses[cfg["bus"]]: solph.Flow()},
        outputs={buses[cfg["bus"]]: solph.Flow()},
        nominal_capacity=get_investment(cfg),
        loss_rate=cfg.get("loss_rate"),
        inflow_conversion_factor=cfg.get("efficiency_charge"),
        outflow_conversion_factor=cfg.get("efficiency_discharge")
    )

    es.add(heat_storage)


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