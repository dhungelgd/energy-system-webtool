"""Tests for the ScenarioResult model: the numbers of a run as plain, saveable data."""

import json
import math

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from backend.config_builder import build_config
from backend.results import RESULT_SCHEMA_VERSION, ScenarioResult, Table
from backend.results_summary import collect_results
from backend.scenario import Scenario
from backend.scenario_runner import run_scenario
from tests.helpers import needs_cbc


def run(scenario):
    """Run a scenario the way the app does. Returns (output, meta_results)."""

    selected, tech_inputs, input_data, solver = scenario.to_inputs()
    config = build_config(selected, tech_inputs, input_data, solver)
    _, results, meta, _ = run_scenario(config, input_data, selected_techs=selected)

    return collect_results(results, meta, config, selected), meta


def grid_only():
    return Scenario(
        components=["demand", "grid"],
        settings={
            "demand": {"scaling_factor": 10.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
        },
        time={"steps": 24},
        series={"electricity_demand": [1.0] * 24},
    )


def with_fixed_pv():
    return Scenario(
        components=["demand", "grid", "pv"],
        settings={
            "demand": {"scaling_factor": 10.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
            "pv": {"mode": "fixed", "capacity": 5.0},
        },
        time={"steps": 24},
        series={"electricity_demand": [1.0] * 24, "pv": [1.0] * 24},
    )


@pytest.fixture(scope="module")
def small_run():
    output, meta = run(grid_only())
    return output, meta, ScenarioResult.from_output(output, meta)


@pytest.fixture(scope="module")
def pv_run():
    output, meta = run(with_fixed_pv())
    return output, meta, ScenarioResult.from_output(output, meta)


# ---------------------------------------------------------------------------
# Table (no solver needed)
# ---------------------------------------------------------------------------

def test_table_from_frame_makes_plain_values():
    frame = pd.DataFrame({
        "Item": ["PV", "Battery"],
        "Cost": [np.float64(10.5), np.nan],
        "Count": [np.int64(2), np.int64(3)],
    })

    table = Table.from_frame(frame)

    assert table.columns == ["Item", "Cost", "Count"]
    assert table.rows == [["PV", 10.5, 2.0], ["Battery", None, 3.0]]
    assert type(table.rows[0][1]) is float


def test_table_gives_the_frame_back():
    frame = pd.DataFrame({"Item": ["PV", "Battery"], "Cost": [10.5, np.nan]})

    again = Table.from_frame(frame).to_frame()

    pd.testing.assert_frame_equal(again, frame)


def test_a_column_with_only_empty_cells_comes_back_as_nan():
    frame = pd.DataFrame({"Item": ["PV"], "Cost": [np.nan]})

    again = Table.from_frame(frame).to_frame()

    assert again["Cost"].dtype == float
    assert math.isnan(again["Cost"].iloc[0])
    pd.testing.assert_frame_equal(again, frame)


def test_text_columns_stay_text():
    frame = pd.DataFrame({"Item": ["PV", "Wind"], "Cost": [1.5, 2.5]})

    assert Table.from_frame(frame).to_frame()["Item"].tolist() == ["PV", "Wind"]


def test_an_empty_table_works():
    table = Table.from_frame(pd.DataFrame(columns=["a", "b"]))

    assert table.rows == []
    assert list(table.to_frame().columns) == ["a", "b"]


def test_a_row_with_the_wrong_number_of_cells_is_refused():
    with pytest.raises(ValidationError, match="row 2 has 1 cells"):
        Table(columns=["a", "b"], rows=[[1.0, 2.0], [3.0]])


def test_infinite_values_become_empty():
    table = Table.from_frame(pd.DataFrame({"x": [1.0, np.inf]}))

    assert table.rows == [[1.0], [None]]


def test_a_result_saved_by_a_newer_version_is_refused():
    with pytest.raises(ValidationError, match="newer version"):
        ScenarioResult(
            schema_version=RESULT_SCHEMA_VERSION + 1, objective=1, horizon_hours=1,
            cost_breakdown=Table(columns=[]), capacities=Table(columns=[]),
        )


def test_typos_in_field_names_are_refused():
    with pytest.raises(ValidationError, match="Extra inputs"):
        Table(columns=["a"], rowz=[])


# ---------------------------------------------------------------------------
# a real run (hand-calculated: 10 kW * 24 h * 0.30 EUR/kWh = 72 EUR)
# ---------------------------------------------------------------------------

@needs_cbc
def test_objective_and_period(small_run):
    _, _, result = small_run

    assert result.objective == pytest.approx(72.0)
    assert result.horizon_hours == pytest.approx(24.0)


@needs_cbc
def test_headline_figures_use_the_wording_for_a_short_period(small_run):
    _, _, result = small_run

    first = result.key_figures[0]
    assert first.label == "System cost (simulated period)"
    assert first.value == pytest.approx(72.0)
    assert first.unit == "€"
    assert first.help


@needs_cbc
def test_cost_breakdown_has_the_grid_purchase(small_run):
    _, _, result = small_run

    frame = result.cost_breakdown.to_frame()
    row = frame[frame["Item"] == "Grid import"].iloc[0]

    assert row["Category"] == "Energy purchase"
    assert row["Cost (€)"] == pytest.approx(72.0)


@needs_cbc
def test_energy_of_the_electricity_bus(small_run):
    _, _, result = small_run

    bus = result.buses["electricity"]

    assert bus.energy_sums["grid_import-->electricity"] == pytest.approx(240.0)
    assert bus.supply.to_frame()["Share (%)"].tolist() == pytest.approx([100.0])


@needs_cbc
def test_solver_information(small_run):
    _, _, result = small_run

    assert result.solver.status == "ok"
    assert result.solver.termination == "optimal"
    assert result.solver.seconds is not None and result.solver.seconds >= 0


@needs_cbc
def test_solver_information_is_optional():
    output, _ = run(grid_only())

    assert ScenarioResult.from_output(output).solver is None


@needs_cbc
def test_empty_cells_of_a_real_table_are_saved_as_null(pv_run):
    _, _, result = pv_run

    frame = result.capacities.to_frame()
    pv = frame[frame["Component"] == "PV"].iloc[0]

    # a fixed capacity has no investment cost: NaN in the DataFrame, null in JSON
    assert pv["Mode"] == "fixed (input)"
    assert result.capacities.rows[0][-1] is None
    assert math.isnan(pv["Annualised cost (€/a)"])


@needs_cbc
def test_json_round_trip_keeps_everything(small_run):
    _, _, result = small_run

    again = ScenarioResult.model_validate_json(result.model_dump_json())

    assert again == result


@needs_cbc
def test_saved_json_is_strict_json_without_nan(pv_run):
    _, _, result = pv_run
    text = result.model_dump_json()

    json.loads(text, parse_constant=lambda token: pytest.fail(f"{token} in JSON"))
    assert "NaN" not in text


@needs_cbc
def test_save_and_load_a_file(small_run, tmp_path):
    _, _, result = small_run
    path = tmp_path / "result.json"

    result.save(path)

    assert ScenarioResult.load(path) == result
    assert json.loads(path.read_text(encoding="utf-8"))["objective"] == pytest.approx(72.0)


@needs_cbc
def test_the_tables_equal_the_ones_of_the_run(small_run):
    output, _, result = small_run

    pd.testing.assert_frame_equal(
        result.cost_breakdown.to_frame(), output["cost_breakdown"], check_dtype=False
    )
    pd.testing.assert_frame_equal(
        result.capacities.to_frame(), output["capacities"], check_dtype=False
    )
    for bus, data in output["buses"].items():
        pd.testing.assert_frame_equal(
            result.buses[bus].supply.to_frame(), data["supply"], check_dtype=False
        )


@needs_cbc
def test_every_key_figure_of_the_run_is_kept(small_run):
    output, _, result = small_run

    assert [f.label for f in result.key_figures] == [f["label"] for f in output["key_figures"]]
    for kept, original in zip(result.key_figures, output["key_figures"]):
        assert kept.value == pytest.approx(original["value"])
