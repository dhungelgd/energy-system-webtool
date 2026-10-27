"""The maximum size typed in for a storage must limit what the optimizer builds."""

import pytest

from backend.scenario import Scenario
from backend.service import run
from backend.tech_config_registry import TECH_CONFIG_REGISTRY
from tests.helpers import needs_cbc

STEPS = 48
PRICE = [0.05 if (hour % 24) < 8 else 0.50 for hour in range(STEPS)]     # cheap at night, dear by day


def storage_scenario(maximum):
    # a battery that costs next to nothing: it is built as large as it is allowed to be
    battery = {"mode": "invest", "capex": 1.0, "opex": 0.0, "lifetime": 100.0, "interest_rate": 0.0,
               "efficiency_charge": 1.0, "efficiency_discharge": 1.0, "loss_rate": 0.0, "c_rate": 0.5}
    if maximum is not None:
        battery["maximum"] = maximum

    return Scenario(
        components=["demand", "grid", "battery"],
        settings={
            "demand": {"scaling_factor": 100.0},
            "grid": {"price_mode": "timeseries", "price_unit": "€/kWh", "variable_costs": 0.3},
            "battery": battery,
        },
        time={"steps": STEPS},
        series={"electricity_demand": [1.0] * STEPS, "grid_price": PRICE},
    )


def built(result, name):
    table = result.capacities.to_frame()
    return float(table[table["Component"].str.contains(name, case=False)]["Capacity"].iloc[0])


@pytest.mark.parametrize("component", ["battery", "heat_storage"])
def test_the_maximum_reaches_the_engine_for_both_storages(component):
    config = TECH_CONFIG_REGISTRY[component](tech_inputs={component: {"mode": "invest", "maximum": 5.0}})

    assert config["maximum"] == 5.0


@needs_cbc
def test_without_a_maximum_the_battery_grows_as_large_as_it_pays():
    assert built(run(storage_scenario(None)), "battery") > 1000


@needs_cbc
def test_a_maximum_limits_the_battery():
    assert built(run(storage_scenario(5.0)), "battery") == pytest.approx(5.0)


@needs_cbc
def test_a_larger_maximum_is_used_up_to_the_limit():
    assert built(run(storage_scenario(40.0)), "battery") == pytest.approx(40.0)