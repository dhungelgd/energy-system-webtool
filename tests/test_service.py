"""Tests for the two functions a frontend calls: check() and run()."""

import pytest

from backend.config_builder import build_config
from backend.results import ScenarioResult
from backend.results_summary import collect_results
from backend.scenario import Scenario
from backend.scenario_runner import run_scenario
from backend.service import ScenarioError, ScenarioNotReady, check, run
from tests.helpers import needs_cbc


def grid_only(**changes):
    values = dict(
        name="Grid only",
        components=["demand", "grid"],
        settings={
            "demand": {"scaling_factor": 10.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
        },
        time={"steps": 24},
        series={"electricity_demand": [1.0] * 24},
    )
    values.update(changes)
    return Scenario(**values)


def too_much_pv():
    # 50 kW of PV all day for a 10 kW demand, and nowhere to put the surplus
    return Scenario(
        components=["demand", "grid", "pv"],
        settings={
            "demand": {"scaling_factor": 10.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
            "pv": {"mode": "fixed", "capacity": 50.0},
        },
        time={"steps": 24},
        series={"electricity_demand": [1.0] * 24, "pv": [1.0] * 24},
    )


# ---------------------------------------------------------------------------
# check (no solver needed)
# ---------------------------------------------------------------------------

def test_check_of_a_good_scenario_has_no_errors():
    findings = check(grid_only())

    assert [f.message for f in findings if f.level == "error"] == []


def test_check_finds_a_series_that_is_too_short():
    findings = check(grid_only(series={"electricity_demand": [1.0] * 10}))

    assert any("10 values" in f.message for f in findings if f.level == "error")


def test_check_uses_readable_names():
    findings = check(Scenario(), labels={})
    assert any("No demand" in f.message for f in findings)

    findings = check(
        Scenario(components=["demand"], series={"electricity_demand": [1.0] * 8760}),
        labels={"demand": "Electricity Demand"},
    )
    assert any("Electricity Demand" in f.message for f in findings)


def test_run_does_not_start_when_the_check_finds_errors():
    scenario = grid_only(series={"electricity_demand": [1.0] * 10})

    with pytest.raises(ScenarioNotReady) as error:
        run(scenario)

    assert error.value.findings
    assert all(f.level == "error" for f in error.value.findings)
    assert "10 values" in str(error.value)


def test_not_ready_is_a_scenario_error():
    assert issubclass(ScenarioNotReady, ScenarioError)


def test_without_the_check_the_model_reports_the_problem():
    scenario = grid_only(series={"electricity_demand": [1.0] * 10})

    with pytest.raises(ScenarioError, match="needs 24"):
        run(scenario, check_first=False)


# ---------------------------------------------------------------------------
# run (needs the CBC solver)
# ---------------------------------------------------------------------------

@needs_cbc
def test_run_gives_the_hand_calculated_result():
    result = run(grid_only())

    # 10 kW * 24 h * 0.30 EUR/kWh
    assert isinstance(result, ScenarioResult)
    assert result.objective == pytest.approx(72.0)
    assert result.horizon_hours == pytest.approx(24.0)
    assert result.solver.status == "ok"
    assert result.buses["electricity"].flows.n_steps == 24


@needs_cbc
def test_run_gives_the_same_numbers_as_the_steps_one_by_one():
    scenario = grid_only()
    selected, tech_inputs, input_data, solver = scenario.to_inputs()
    config = build_config(selected, tech_inputs, input_data, solver)
    _, results, meta, _ = run_scenario(config, input_data, selected_techs=selected)
    by_hand = ScenarioResult.from_output(collect_results(results, meta, config, selected), meta)

    result = run(scenario)

    # the solver time differs from run to run, everything else is the same
    assert result.model_dump(exclude={"solver"}) == by_hand.model_dump(exclude={"solver"})
    assert result.solver.termination == by_hand.solver.termination


@needs_cbc
def test_run_without_flows():
    result = run(grid_only(), include_flows=False)

    assert all(bus.flows is None for bus in result.buses.values())


@needs_cbc
def test_a_system_that_cannot_be_balanced_gives_a_clear_error():
    # the system check only warns here; the solver finds no solution
    assert [f for f in check(too_much_pv()) if f.level == "error"] == []

    with pytest.raises(ScenarioError) as error:
        run(too_much_pv())

    assert not isinstance(error.value, ScenarioNotReady)
    assert str(error.value)


@needs_cbc
def test_the_whole_way_from_a_scenario_file_to_a_result_file(tmp_path):
    grid_only().save(tmp_path / "scenario.json")

    result = run(Scenario.load(tmp_path / "scenario.json"))
    result.save(tmp_path / "result.json")

    again = ScenarioResult.load(tmp_path / "result.json")

    assert again == result
    assert again.objective == pytest.approx(72.0)
    assert again.to_output()["objective"] == pytest.approx(72.0)