"""Golden tests: the same system, run directly and run through layout 2, gives the same result."""

import pandas as pd
import pytest

from backend.scenario import Scenario
from backend.scenario_convert import scenario_to_v1
from backend.service import run
from examples.make_examples import day_shape, sun_shape
from examples.make_examples_v2 import EXAMPLES
from tests.helpers import needs_cbc
from tests.v1_support import scenario_from_v1

pytestmark = needs_cbc


def shares(steps):
    """Daily shares that add up to 1 over a year of equal days (10 kW on average for 87,600 kWh)."""

    shape = [day_shape(h % 24) for h in range(steps)]
    day = sum(day_shape(h) for h in range(24))
    return [value / (day * 365) for value in shape]


def sun(steps, shift=0):
    return [sun_shape((h + shift) % 24) for h in range(steps)]


def invest(capex, maximum=None, opex=1.0, lifetime=20.0):
    values = {"mode": "invest", "capex": capex, "opex": opex, "lifetime": lifetime, "interest_rate": 3.0}
    if maximum is not None:
        values["maximum"] = maximum
    return values


def fixed(capacity):
    return {"mode": "fixed", "capacity": capacity}


def storage(base, c_rate):
    return {**base, "efficiency_charge": 0.95, "efficiency_discharge": 0.95, "loss_rate": 0.001, "c_rate": c_rate}


STEPS = 72


def pv_and_battery():
    # a price in ct/kWh, so that the unit conversion is part of the test
    price = [25.0 if h % 24 < 8 else 45.0 for h in range(STEPS)]
    return Scenario(
        name="PV and battery",
        components=["demand", "grid", "grid_feedin", "pv", "battery"],
        settings={
            "demand": {"scaling_factor": 87600.0},
            "grid": {"price_mode": "timeseries", "price_unit": "ct/kWh", "variable_costs": 0.3},
            "grid_feedin": {"feedin_tariff": 0.05},
            "pv": invest(1.0, maximum=50.0, opex=2.0, lifetime=25.0),
            "battery": storage(invest(1.0, maximum=30.0, lifetime=15.0), 0.5),
        },
        time={"steps": STEPS},
        series={"electricity_demand": shares(STEPS), "grid_price": price, "pv": sun(STEPS)},
    )


def heat_system():
    cop = [3.0 + 1.0 * sun_shape(h % 24) for h in range(STEPS)]
    price = [250.0 if h % 24 < 8 else 450.0 for h in range(STEPS)]          # EUR per MWh
    return Scenario(
        name="Heat",
        components=["demand", "heat_demand", "grid", "gas_import", "gas_boiler", "heat_pump", "heating_rod",
                    "heat_storage"],
        settings={
            "demand": {"scaling_factor": 87600.0},
            "heat_demand": {"scaling_factor": 87600.0},
            "grid": {"price_mode": "timeseries", "price_unit": "€/MWh", "variable_costs": 0.3},
            "gas_import": {"variable_costs": 0.08},
            "gas_boiler": {**fixed(5.0), "efficiency": 0.9},
            "heat_pump": {**fixed(4.0), "cop_mode": "timeseries", "cop_value": 3.5},
            "heating_rod": {**fixed(10.0), "efficiency": 0.99},
            "heat_storage": storage(invest(1.0, maximum=40.0, lifetime=15.0), 0.25),
        },
        time={"steps": STEPS},
        series={"electricity_demand": shares(STEPS), "heat_demand": shares(STEPS), "cop_series": cop,
                "grid_price": price},
    )


def chp_system():
    return Scenario(
        name="CHP",
        components=["demand", "heat_demand", "grid", "grid_feedin", "gas_import", "chp", "gas_boiler"],
        settings={
            "demand": {"scaling_factor": 87600.0},
            "heat_demand": {"scaling_factor": 87600.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.3},
            "grid_feedin": {"feedin_tariff": 0.05},
            "gas_import": {"variable_costs": 0.08},
            "chp": {**fixed(8.0), "efficiency_el": 0.35, "efficiency_th": 0.5},
            "gas_boiler": {**fixed(30.0), "efficiency": 0.9},
        },
        time={"steps": STEPS},
        series={"electricity_demand": shares(STEPS), "heat_demand": shares(STEPS)},
    )


def a_whole_year():
    # a profile that does NOT add up to 1: it is multiplied out to kW when it is converted
    profile = [0.5 + 0.25 * day_shape(h % 24) for h in range(8760)]
    return Scenario(
        name="A year",
        components=["demand", "grid"],
        settings={"demand": {"scaling_factor": 100.0}, "grid": {"price_mode": "constant", "variable_costs": 0.3}},
        time={"steps": 8760},
        series={"electricity_demand": profile},
    )


def same(first, second):
    assert first.solver.termination == second.solver.termination == "optimal"
    assert first.objective == pytest.approx(second.objective, rel=1e-9)

    pd.testing.assert_frame_equal(first.capacities.to_frame(), second.capacities.to_frame(),
                                  check_exact=False, rtol=1e-9)
    assert list(first.buses) == list(second.buses)
    for bus in first.buses:
        pd.testing.assert_frame_equal(first.buses[bus].flows.to_frame(), second.buses[bus].flows.to_frame(),
                                      check_exact=False, rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize("build", [pv_and_battery, heat_system, chp_system, a_whole_year],
                         ids=["pv_and_battery", "heat", "chp", "whole_year"])
def test_running_through_layout_2_gives_the_same_result(build):
    direct = build()

    through = scenario_to_v1(scenario_from_v1(direct))

    same(run(direct), run(through))


def test_the_layout_2_example_gives_the_same_result_as_the_same_system_built_by_hand():
    example = EXAMPLES["pv_and_grid"]()

    by_hand = Scenario(
        components=["demand", "grid", "pv"],
        settings={
            "demand": {"scaling_factor": 87600.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
            "pv": invest(1200.0, maximum=100.0, opex=2.0, lifetime=25.0),
        },
        time={"steps": 24},
        series={"electricity_demand": shares(24), "pv": sun(24)},
    )

    same(run(scenario_to_v1(example)), run(by_hand))


def test_the_known_cost_of_a_layout_2_scenario_with_absolute_demand():
    # 10 kW for a day at 0.30 EUR/kWh = 72 EUR, written in layout 2 with absolute values
    example = EXAMPLES["pv_and_grid"]().model_dump()
    example["components"] = [c for c in example["components"] if c["id"] != "pv"]
    example["components"][0]["blocks"]["demand"] = {"series": "electricity_demand", "profile_type": "absolute"}
    example["series"] = {"electricity_demand": {"unit": "kW", "values": [10.0] * 24}}

    from backend.scenario_v2 import ScenarioV2

    assert run(scenario_to_v1(ScenarioV2(**example))).objective == pytest.approx(72.0)


def capacities(result):
    table = result.capacities.to_frame()
    return {row["Component"]: row["Capacity"] for _, row in table.iterrows()}


def used(result):
    return {column for bus in result.buses.values()
            for column, total in bus.flows.to_frame().sum().items() if abs(total) > 1e-6}


def test_the_golden_systems_really_use_what_they_are_meant_to_test():
    # if a system built nothing, the comparison would prove very little
    first = run(pv_and_battery())
    assert capacities(first)["PV"] == pytest.approx(50.0)               # up to its maximum
    assert capacities(first)["Battery"] == pytest.approx(30.0)

    second = run(heat_system())
    assert capacities(second)["Heat storage"] == pytest.approx(40.0)
    assert {"heat_pump-->heat", "gas_boiler-->heat", "heating_rod-->heat"} <= used(second)

    third = run(chp_system())
    assert {"chp-->electricity", "chp-->heat", "gas_boiler-->heat"} <= used(third)