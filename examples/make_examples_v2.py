"""Creates the example scenarios of layout 2 in examples/scenarios_v2 (synthetic data only).

Run it from the repository folder:

    python -m examples.make_examples_v2

The examples: PV and grid, two PV systems, a hydrogen chain that the user defined,
and a scenario with problems, to see what the system check says. The numbers are invented.
"""

from pathlib import Path

from backend.scenario_v2 import ScenarioV2
from examples.shapes import day_shape, sun_shape

FOLDER = Path(__file__).resolve().parent / "scenarios_v2"

ELECTRICITY = {"id": "electricity", "label": "Electricity"}
HOURS = range(24)
INVEST = {"mode": "invest", "capex": 1200.0, "opex": 2.0, "lifetime": 25.0, "interest_rate": 3.0}


def source(component_id, name, template, carrier, blocks):
    return {"id": component_id, "name": name, "template": template, "kind": "source",
            "connections": [{"carrier": carrier, "direction": "out"}], "blocks": blocks}


def demand(component_id, name, template, carrier, series_id, **settings):
    return {"id": component_id, "name": name, "template": template, "kind": "sink",
            "connections": [{"carrier": carrier, "direction": "in"}],
            "blocks": {"demand": {"series": series_id, **settings}}}


def daily_shares():
    """A daily shape as shares that add up to 1 over a year of 365 equal days."""

    shape = [day_shape(h) for h in HOURS]
    return [value / (sum(shape) * 365) for value in shape]


def pv_and_grid():
    """A day: a demand of 87,600 kWh per year (10 kW on average), the grid, and a PV system
    that the optimizer sizes."""

    return ScenarioV2(
        name="PV and grid, one day",
        time={"steps": 24},
        carriers=[ELECTRICITY],
        components=[
            demand("demand", "Electricity demand", "demand", "electricity", "electricity_demand",
                   profile_type="annual_share", annual_demand=87600.0),
            source("grid", "Electricity grid", "grid", "electricity", {"costs": {"variable_costs": 0.30}}),
            source("pv", "PV system", "pv", "electricity", {
                "capacity": {**INVEST, "maximum": 100.0},
                "profile": {"series": "pv_profile"},
            }),
        ],
        series={
            "electricity_demand": {"unit": "share of the annual demand", "values": daily_shares()},
            "pv_profile": {"unit": "capacity factor", "values": [sun_shape(h) for h in HOURS]},
        },
    )


def two_pv_systems():
    """The same, with two PV systems: a fixed one on the south roof and one on the east roof."""

    scenario = pv_and_grid().model_dump()
    scenario["name"] = "Two PV systems, one day"
    scenario["components"] = [c for c in scenario["components"] if c["id"] != "pv"] + [
        source("pv_south", "PV south roof", "pv", "electricity", {
            "capacity": {"mode": "fixed", "capacity": 60.0},
            "profile": {"series": "pv_south_profile"},
        }),
        source("pv_east", "PV east roof", "pv", "electricity", {
            "capacity": {**INVEST, "maximum": 40.0},
            "profile": {"series": "pv_east_profile"},
        }),
    ]
    scenario["series"].pop("pv_profile")
    scenario["series"]["pv_south_profile"] = {"unit": "capacity factor", "values": [sun_shape(h) for h in HOURS]}
    scenario["series"]["pv_east_profile"] = {"unit": "capacity factor",
                                             "values": [sun_shape((h + 3) % 24) for h in HOURS]}
    return ScenarioV2(**scenario)


def with_problems():
    """The same system with mistakes: to see what the system check says.

    The demand series is too short (an error), the PV system is fixed and nothing can
    take its surplus (a warning), and its profile is above 1 (a warning).
    """

    scenario = pv_and_grid().model_dump()
    scenario["name"] = "With problems, one day"

    pv = next(c for c in scenario["components"] if c["id"] == "pv")
    pv["blocks"]["capacity"] = {"mode": "fixed", "capacity": 5.0}

    scenario["series"]["electricity_demand"]["values"] = daily_shares()[:10]
    scenario["series"]["pv_profile"]["values"] = [3 * sun_shape(h) for h in HOURS]
    return ScenarioV2(**scenario)


def hydrogen_chain():
    """A chain that the user defined: electrolyser, hydrogen tank and a hydrogen demand."""

    return ScenarioV2(
        name="Hydrogen chain, one day",
        time={"steps": 24},
        carriers=[ELECTRICITY, {"id": "hydrogen", "label": "Hydrogen", "custom": True}],
        components=[
            source("grid", "Electricity grid", "grid", "electricity", {"costs": {"variable_costs": 0.30}}),
            {
                "id": "electrolyser", "name": "Electrolyser", "template": None, "kind": "converter",
                "connections": [{"carrier": "electricity", "direction": "in"},
                                {"carrier": "hydrogen", "direction": "out"}],
                "blocks": {
                    "capacity": {**INVEST, "rated_flow": "hydrogen", "maximum": 300.0,
                                 "capex": 900.0, "opex": 3.0, "lifetime": 15.0},
                    "conversion": {"outputs": {"hydrogen": {"efficiency": 65.0}}},
                    "on_off": {"minimum_load": 20.0, "startup_cost": 5.0},
                },
            },
            {
                "id": "h2_tank", "name": "Hydrogen tank", "template": None, "kind": "storage",
                "connections": [{"carrier": "hydrogen", "direction": "both"}],
                "blocks": {
                    "capacity": {**INVEST, "maximum": 2000.0, "capex": 30.0, "opex": 1.0},
                    "storage": {"c_rate": 0.25, "efficiency_charge": 98.0, "efficiency_discharge": 98.0,
                                "loss_rate": 0.05, "initial_level": 50.0},
                },
            },
            demand("h2_demand", "Hydrogen demand", None, "hydrogen", "h2_profile", profile_type="absolute"),
        ],
        series={"h2_profile": {"unit": "kW", "values": [10.0] * 24}},
    )


EXAMPLES = {
    "pv_and_grid": pv_and_grid,
    "two_pv_systems": two_pv_systems,
    "hydrogen_chain": hydrogen_chain,
    "with_problems": with_problems,
}


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)

    for name, build in EXAMPLES.items():
        path = FOLDER / f"{name}.json"
        build().save(path)
        print(f"{path.name:22s} {path.stat().st_size / 1000:6.1f} KB")


if __name__ == "__main__":
    main()