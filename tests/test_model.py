"""Model tests with results that can be checked by hand (need the CBC solver).

All tests use a 24 hour system with a constant electricity demand of 10 kW
(demand profile 1.0, scaling factor 10), i.e. 240 kWh per day.
"""

import pytest
from oemof.solph import views

from backend.config_builder import build_config
from backend.input_schema import SolverConfig
from backend.model_builder import build_model
from backend.postprocessing import get_investment_capacities
from tests.helpers import needs_cbc, solve, timeindex

pytestmark = needs_cbc

HOURS = 24


def base_data(**extra):
    data = {"timeindex": timeindex(HOURS), "electricity_demand": [1.0] * HOURS}
    data.update(extra)
    return data


def battery_power(results):
    """Highest charge and discharge power of the battery in kW."""

    sequences = views.node(results, "battery")["sequences"]
    charge = discharge = 0.0
    for (source, target), kind in sequences.columns:
        if kind != "flow":
            continue
        if target == "battery":
            charge = max(charge, sequences[((source, target), kind)].max())
        if source == "battery":
            discharge = max(discharge, sequences[((source, target), kind)].max())
    return charge, discharge


def test_every_hour_of_the_time_index_is_simulated():
    # oemof reads N timestamps as N-1 steps unless the last interval is inferred
    tech = {
        "demand": {"scaling_factor": 10},
        "grid": {"price_mode": "constant", "variable_costs": 0.30},
    }
    data = base_data()
    config = build_config(
        ["demand", "grid"], tech, data, SolverConfig(name="cbc")
    )
    es = build_model(config, data)

    assert len(es.timeincrement) == HOURS
    assert es.timeincrement.sum() == HOURS


def test_grid_only_cost_is_energy_times_price():
    tech = {
        "demand": {"scaling_factor": 10},
        "grid": {"price_mode": "constant", "variable_costs": 0.30},
    }
    _, meta, _ = solve(["demand", "grid"], tech, base_data())

    # 10 kW * 24 h * 0.30 EUR/kWh
    assert meta["objective"] == pytest.approx(72.0)


def test_price_series_in_ct_per_kwh_is_converted():
    tech = {
        "demand": {"scaling_factor": 10},
        "grid": {"price_mode": "timeseries", "price_unit": "ct/kWh"},
    }
    data = base_data(grid_price=[30.0] * HOURS)
    _, meta, _ = solve(["demand", "grid"], tech, data)

    assert meta["objective"] == pytest.approx(72.0)


def test_pv_that_covers_the_demand_removes_all_cost():
    tech = {
        "demand": {"scaling_factor": 10},
        "grid": {"price_mode": "constant", "variable_costs": 0.30},
        "grid_feedin": {"feedin_tariff": 0.08},
        "pv": {"mode": "fixed", "capacity": 10},
    }
    data = base_data(pv=[1.0] * HOURS)
    _, meta, _ = solve(["demand", "grid", "grid_feedin", "pv"], tech, data)

    assert meta["objective"] == pytest.approx(0.0, abs=1e-6)


def storage_tech(**battery):
    return {
        "demand": {"scaling_factor": 10},
        "grid": {"price_mode": "timeseries", "price_unit": "€/kWh"},
        "battery": {
            "loss_rate": 0.0,
            "efficiency_charge": 1.0,
            "efficiency_discharge": 1.0,
            **battery,
        },
    }


# 12 cheap hours (0.10 EUR/kWh), then 12 expensive hours (0.50 EUR/kWh)
PRICES = [0.10] * 12 + [0.50] * 12


def test_battery_power_is_limited_by_the_c_rate():
    # 100 kWh * 0.05 = 5 kW, however attractive the price difference is
    tech = storage_tech(mode="fixed", capacity=100, c_rate=0.05)
    results, _, _ = solve(
        ["demand", "grid", "battery"], tech, base_data(grid_price=PRICES)
    )

    charge, discharge = battery_power(results)
    assert charge == pytest.approx(5.0)
    assert discharge == pytest.approx(5.0)


def test_c_rate_limited_battery_saves_the_expected_amount():
    # Charging 5 kW for 12 cheap hours stores 60 kWh; discharging it in the
    # expensive hours saves 60 * (0.50 - 0.10) = 24 EUR.
    # Without the battery: 12*10*0.10 + 12*10*0.50 = 72 EUR -> 48 EUR.
    tech = storage_tech(mode="fixed", capacity=100, c_rate=0.05)
    _, meta, _ = solve(["demand", "grid", "battery"], tech, base_data(grid_price=PRICES))

    assert meta["objective"] == pytest.approx(48.0)


def test_higher_c_rate_allows_more_shifting():
    # with 10 kW the full 100 kWh can be shifted: 72 - 100*0.50 + 100*0.10 = 32 EUR
    tech = storage_tech(mode="fixed", capacity=100, c_rate=0.10)
    _, meta, _ = solve(["demand", "grid", "battery"], tech, base_data(grid_price=PRICES))

    assert meta["objective"] == pytest.approx(32.0)


def test_invested_storage_reports_energy_capacity_and_respects_c_rate():
    tech = storage_tech(
        mode="invest", c_rate=0.05,
        capex=1.0, opex=0.0, lifetime=10.0, interest_rate=3.0,
    )
    results, _, _ = solve(
        ["demand", "grid", "battery"], tech, base_data(grid_price=PRICES)
    )

    capacity = get_investment_capacities(results)["battery"]
    charge, discharge = battery_power(results)

    assert capacity > 0
    # the reported number is the energy capacity (kWh), not the power (kW)
    assert charge <= 0.05 * capacity + 1e-6
    assert discharge <= 0.05 * capacity + 1e-6


def test_missing_c_rate_raises_a_clear_error():
    tech = storage_tech(mode="fixed", capacity=100)
    with pytest.raises(ValueError, match="C-rate"):
        solve(["demand", "grid", "battery"], tech, base_data(grid_price=PRICES))


def test_short_profile_raises_a_clear_error():
    tech = {
        "demand": {"scaling_factor": 10},
        "grid": {"price_mode": "constant", "variable_costs": 0.30},
    }
    data = base_data(electricity_demand=[1.0] * 10)
    with pytest.raises(ValueError, match="needs 24"):
        solve(["demand", "grid"], tech, data)