"""Tests for the pre-run system check (no solver needed)."""

from backend.system_check import check_system
from tests.helpers import timeindex

HOURS = 8760


def run_check(selected, tech_inputs=None, **series):
    data = {"timeindex": timeindex(HOURS)}
    data.update(series)
    return check_system(selected, tech_inputs or {}, data)


def errors(findings):
    return [f.message for f in findings if f.level == "error"]


def warnings(findings):
    return [f.message for f in findings if f.level == "warning"]


GRID = {"grid": {"price_mode": "constant", "variable_costs": 0.30}}


# ---- structure -------------------------------------------------------------

def test_valid_minimal_system_has_no_findings():
    findings = run_check(["demand", "grid"], GRID, electricity_demand=[1.0] * HOURS)
    assert findings == []


def test_no_demand_is_an_error():
    assert any("No demand" in m for m in errors(run_check(["grid"], GRID)))


def test_demand_without_supply_is_an_error():
    findings = run_check(["demand"], electricity_demand=[1.0] * HOURS)
    assert any("no supply" in m for m in errors(findings))


def test_heat_demand_without_heat_source_is_an_error():
    findings = run_check(["heat_demand", "grid"], GRID, heat_demand=[1.0] * HOURS)
    assert any("cannot be supplied" in m for m in errors(findings))


def test_feedin_tariff_above_price_is_an_error():
    tech = {**GRID, "grid_feedin": {"feedin_tariff": 0.50}}
    findings = run_check(
        ["demand", "grid", "grid_feedin"], tech, electricity_demand=[1.0] * HOURS
    )
    assert any("feed-in tariff" in m for m in errors(findings))


# ---- time series -----------------------------------------------------------

def test_missing_upload_is_an_error():
    findings = run_check(["demand", "grid"], GRID)
    assert any("no time series uploaded" in m for m in errors(findings))


def test_series_too_short_is_an_error():
    findings = run_check(["demand", "grid"], GRID, electricity_demand=[1.0] * 8000)
    assert any("8000 values" in m for m in errors(findings))


def test_series_too_long_is_only_a_warning():
    findings = run_check(["demand", "grid"], GRID, electricity_demand=[1.0] * 8784)
    assert errors(findings) == []
    assert any("first 8760" in m for m in warnings(findings))


def test_nan_in_series_is_an_error():
    values = [1.0] * HOURS
    values[10] = float("nan")
    findings = run_check(["demand", "grid"], GRID, electricity_demand=values)
    assert any("empty or non-numeric" in m for m in errors(findings))


def test_text_in_series_is_an_error():
    values = [1.0] * HOURS
    values[10] = "abc"
    findings = run_check(["demand", "grid"], GRID, electricity_demand=values)
    assert any("empty or non-numeric" in m for m in errors(findings))


def test_price_series_in_wrong_length_is_an_error():
    tech = {"grid": {"price_mode": "timeseries", "price_unit": "€/kWh"}}
    findings = run_check(
        ["demand", "grid"], tech,
        electricity_demand=[1.0] * HOURS, grid_price=[0.3] * 100,
    )
    assert any("price series has 100 values" in m for m in errors(findings))


# ---- component inputs ------------------------------------------------------

def test_fixed_mode_needs_a_capacity():
    tech = {**GRID, "pv": {"mode": "fixed", "capacity": 0}}
    findings = run_check(
        ["demand", "grid", "pv"], tech,
        electricity_demand=[1.0] * HOURS, pv=[0.5] * HOURS,
    )
    assert any("fixed mode needs a capacity" in m for m in errors(findings))


def test_invest_mode_needs_cost_data():
    tech = {**GRID, "pv": {"mode": "invest", "capex": 1000.0}}
    findings = run_check(
        ["demand", "grid", "pv"], tech,
        electricity_demand=[1.0] * HOURS, pv=[0.5] * HOURS,
    )
    assert any("invest mode needs values" in m for m in errors(findings))


def test_chp_efficiencies_cannot_exceed_one():
    tech = {
        **GRID,
        "chp": {"mode": "fixed", "capacity": 10, "efficiency_el": 0.6, "efficiency_th": 0.6},
    }
    findings = run_check(
        ["demand", "heat_demand", "grid", "gas_import", "chp"], tech,
        electricity_demand=[1.0] * HOURS, heat_demand=[1.0] * HOURS,
    )
    assert any("cannot be greater than 1" in m for m in errors(findings))


def test_storage_needs_a_positive_c_rate():
    base = {"mode": "fixed", "capacity": 10, "loss_rate": 0.0}
    for bad in (None, 0, -1):
        tech = {**GRID, "battery": {**base, "c_rate": bad}}
        findings = run_check(
            ["demand", "grid", "battery"], tech, electricity_demand=[1.0] * HOURS
        )
        assert any("C-rate" in m for m in errors(findings)), f"c_rate={bad}"


def test_valid_c_rate_gives_no_error():
    tech = {**GRID, "battery": {"mode": "fixed", "capacity": 10, "c_rate": 0.5}}
    findings = run_check(
        ["demand", "grid", "battery"], tech, electricity_demand=[1.0] * HOURS
    )
    assert errors(findings) == []