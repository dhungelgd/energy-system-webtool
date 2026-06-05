import pandas as pd
from oemof import solph
from oemof.tools import economics

# function to calculate epc
def calculate_epc(capex, opex, lifetime, interest_rate):

    epc_capex = economics.annuity(capex=capex, n=lifetime, wacc=interest_rate / 100)
    fixed_opex_per_year = opex * capex / 100
    return epc_capex + fixed_opex_per_year


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
                    nominal_capacity=cfg.get("scaling_factor", 1.0)
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
    grid = solph.components.Source(
        label="grid_import",
        outputs={
            buses[cfg["bus"]]: solph.Flow(
                variable_costs=cfg.get("variable_costs", 0.3)
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
                variable_costs=-cfg.get("feedin_tariff", 0.078)
            )
        }
    )

    es.add(feedin)


# add pv
def add_pv(es, buses, cfg, input_data):
    # pv time series
    profile_key = cfg.get("profile_key", "pv")

    if profile_key not in input_data:
        raise ValueError(
            f"PV profile '{profile_key}' not found in input_data"
        )

    timeindex = es.timeindex

    pv_profile = pd.Series(input_data[profile_key])

    pv_series = pd.Series(
        pv_profile.values,
        index=timeindex[:len(pv_profile)]
    )

    # dispatch optimization (fixed pv size)
    if cfg.get("mode", "fixed") == "fixed":

        pv = solph.components.Source(
            label="pv",
            outputs={
                buses[cfg["bus"]]: solph.Flow(
                    fix=pv_series,
                    nominal_capacity=cfg.get("capacity", 10)
                )
            }
        )

    # investment optimization
    elif cfg.get("mode") == "invest":

        ep_costs = calculate_epc(
            capex=cfg.get("capex", 1000),
            opex=cfg.get("opex", 2.0),
            lifetime=cfg.get("lifetime", 25),
            interest_rate=cfg.get("interest_rate", 3),
        )

        pv = solph.components.Source(
            label="pv",
            outputs={
                buses[cfg["bus"]]: solph.Flow(
                    fix=pv_series,
                    nominal_capacity=solph.Investment(
                        ep_costs=ep_costs, maximum=cfg.get("maximum", 100)
                    )
                )
            }
        )

    else:
        raise ValueError(
            f"Unknown PV mode: {cfg.get('mode')}"
        )

    es.add(pv)


# component registry
TECH_MAPPING = {
    "demand": add_demand,
    "grid": add_grid_import,
    "grid_feedin": add_grid_feedin,
    "pv": add_pv
}
