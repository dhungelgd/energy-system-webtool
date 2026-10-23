"""Tests for the hourly flows in a ScenarioResult."""

import json
import math

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from backend.config_builder import build_config
from backend.postprocessing import compute_energy_sums
from backend.results import BusSummary, FlowTable, ScenarioResult, Table
from backend.results_summary import collect_results
from backend.scenario import Scenario
from backend.scenario_runner import run_scenario
from tests.helpers import needs_cbc


def run_like_frame(steps=6, freq="1h", columns=("grid-->bus", "bus-->demand")):
    """A frame shaped like the flows of a run: one empty row at the end."""

    index = pd.date_range("2021-03-14 00:00", periods=steps + 1, freq=freq)
    data = {
        name: [float(i + k) for i in range(steps)] + [np.nan]
        for k, name in enumerate(columns)
    }
    return pd.DataFrame(data, index=index)


# ---------------------------------------------------------------------------
# FlowTable (no solver needed)
# ---------------------------------------------------------------------------

def test_the_empty_end_row_is_not_stored():
    table = FlowTable.from_frame(run_like_frame(steps=6))

    assert table.n_steps == 6
    assert table.columns == ["grid-->bus", "bus-->demand"]
    assert table.values[0] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    assert table.start == pd.Timestamp("2021-03-14 00:00").to_pydatetime()
    assert table.step_hours == 1.0


def test_to_frame_gives_back_exactly_the_flows_of_a_run():
    frame = run_like_frame(steps=6)

    again = FlowTable.from_frame(frame).to_frame()

    pd.testing.assert_frame_equal(again, frame, check_exact=True)
    assert again.iloc[-1].isna().all()


def test_to_frame_without_the_end_row():
    frame = run_like_frame(steps=6)

    again = FlowTable.from_frame(frame).to_frame(with_end_row=False)

    assert len(again) == 6
    pd.testing.assert_frame_equal(again, frame.iloc[:-1], check_exact=True)


def test_a_frame_without_an_end_row_works_too():
    frame = run_like_frame(steps=6).iloc[:-1]

    table = FlowTable.from_frame(frame)

    assert table.n_steps == 6
    pd.testing.assert_frame_equal(table.to_frame(with_end_row=False), frame, check_exact=True)


def test_quarter_hourly_steps():
    frame = run_like_frame(steps=8, freq="15min")

    table = FlowTable.from_frame(frame)

    assert table.step_hours == 0.25
    pd.testing.assert_frame_equal(table.to_frame(), frame, check_exact=True)


def test_values_are_stored_exactly_without_rounding(tmp_path):
    awkward = [1 / 3, 0.1 + 0.2, 12345.678901234567, 1e-9, 81.05000000000001, 0.0]
    frame = run_like_frame(steps=6)
    frame["grid-->bus"] = awkward + [np.nan]

    table = FlowTable.from_frame(frame)
    path = tmp_path / "flows.json"
    path.write_text(table.model_dump_json(), encoding="utf-8")
    again = FlowTable.model_validate_json(path.read_text(encoding="utf-8")).to_frame()

    # not close: exactly equal, also after a trip through a JSON file
    assert again["grid-->bus"].iloc[:-1].tolist() == awkward
    pd.testing.assert_frame_equal(again, frame, check_exact=True)


def test_values_are_plain_numbers_and_empty_cells_are_kept_as_empty():
    frame = run_like_frame(steps=4)
    frame.iloc[1, 0] = np.nan                       # an empty value inside the data

    table = FlowTable.from_frame(frame)

    assert table.values[0] == [0.0, None, 2.0, 3.0]
    assert type(table.values[0][0]) is float
    assert math.isnan(table.to_frame().iloc[1, 0])


def test_a_row_without_any_value_inside_the_data_is_kept():
    frame = run_like_frame(steps=4)
    frame.iloc[2] = np.nan

    table = FlowTable.from_frame(frame)

    assert table.n_steps == 4
    assert table.values[0][2] is None and table.values[1][2] is None


def test_irregular_time_steps_are_refused():
    frame = run_like_frame(steps=4)
    frame.index = pd.DatetimeIndex(
        ["2021-01-01 00:00", "2021-01-01 01:00", "2021-01-01 03:00",
         "2021-01-01 04:00", "2021-01-01 05:00"]
    )

    with pytest.raises(ValueError, match="not regular"):
        FlowTable.from_frame(frame)


def test_flows_without_a_time_index_are_refused():
    with pytest.raises(ValueError, match="time index"):
        FlowTable.from_frame(pd.DataFrame({"a": [1.0, 2.0]}))


def test_an_empty_frame_and_a_frame_without_values_are_refused():
    with pytest.raises(ValueError):
        FlowTable.from_frame(run_like_frame(steps=3).iloc[:0])

    only_empty = run_like_frame(steps=3)
    only_empty[:] = np.nan
    with pytest.raises(ValueError, match="no values"):
        FlowTable.from_frame(only_empty)


def test_inconsistent_tables_are_refused():
    start = pd.Timestamp("2021-01-01").to_pydatetime()

    with pytest.raises(ValidationError, match="2 column names, but 1 lists"):
        FlowTable(start=start, step_hours=1, columns=["a", "b"], values=[[1.0]])

    with pytest.raises(ValidationError, match="used twice: a"):
        FlowTable(start=start, step_hours=1, columns=["a", "a"], values=[[1.0], [2.0]])

    with pytest.raises(ValidationError, match="different lengths"):
        FlowTable(start=start, step_hours=1, columns=["a", "b"], values=[[1.0], [2.0, 3.0]])

    with pytest.raises(ValidationError):
        FlowTable(start=start, step_hours=0, columns=["a"], values=[[1.0]])


def test_json_round_trip_and_strict_json():
    frame = run_like_frame(steps=5)
    frame.iloc[1, 0] = np.nan
    table = FlowTable.from_frame(frame)

    text = table.model_dump_json()

    json.loads(text, parse_constant=lambda token: pytest.fail(f"{token} in JSON"))
    assert FlowTable.model_validate_json(text) == table


def test_a_bus_without_flows_is_still_valid():
    bus = BusSummary(
        energy_sums={"a-->b": 1.0},
        supply=Table(columns=["x"]),
        use=Table(columns=["x"]),
    )

    assert bus.flows is None


# ---------------------------------------------------------------------------
# a real run: 10 kW for 24 hours, 5 kW of it from PV
# ---------------------------------------------------------------------------

def small_scenario():
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
def run():
    selected, tech_inputs, input_data, solver = small_scenario().to_inputs()
    config = build_config(selected, tech_inputs, input_data, solver)
    _, results, meta, _ = run_scenario(config, input_data, selected_techs=selected)
    output = collect_results(results, meta, config, selected)

    return output, meta, ScenarioResult.from_output(output, meta)


@needs_cbc
def test_the_result_holds_the_flows_of_every_bus(run):
    output, _, result = run

    assert set(result.buses) == set(output["buses"])
    flows = result.buses["electricity"].flows

    assert flows.n_steps == 24
    assert flows.step_hours == 1.0
    assert flows.start == pd.Timestamp("2021-01-01").to_pydatetime()


@needs_cbc
def test_the_flows_come_back_exactly_as_the_run_made_them(run):
    output, _, result = run

    for bus, data in output["buses"].items():
        pd.testing.assert_frame_equal(
            result.buses[bus].flows.to_frame(), data["flows"], check_exact=True
        )


@needs_cbc
def test_flows_and_energy_sums_agree(run):
    output, _, result = run
    bus = result.buses["electricity"]

    sums = compute_energy_sums(bus.flows.to_frame())

    for name, energy in bus.energy_sums.items():
        assert sums[name] == pytest.approx(energy)

    # hand-calculated: 10 kW * 24 h = 240 kWh demand, half of it from PV
    assert bus.energy_sums["pv-->electricity"] == pytest.approx(120.0)
    assert bus.energy_sums["grid_import-->electricity"] == pytest.approx(120.0)


@needs_cbc
def test_the_hourly_values_are_what_was_calculated(run):
    _, _, result = run
    frame = result.buses["electricity"].flows.to_frame(with_end_row=False)

    assert frame["pv-->electricity"].tolist() == pytest.approx([5.0] * 24)
    assert frame["grid_import-->electricity"].tolist() == pytest.approx([5.0] * 24)
    assert frame["electricity-->demand"].tolist() == pytest.approx([10.0] * 24)


@needs_cbc
def test_a_result_without_flows_is_smaller(run):
    output, meta, with_flows = run

    light = ScenarioResult.from_output(output, meta, include_flows=False)

    assert all(bus.flows is None for bus in light.buses.values())
    assert len(light.model_dump_json()) < len(with_flows.model_dump_json())


@needs_cbc
def test_the_flows_survive_saving_and_loading(run, tmp_path):
    output, _, result = run
    path = tmp_path / "result.json"

    result.save(path)
    loaded = ScenarioResult.load(path)

    assert loaded == result
    pd.testing.assert_frame_equal(
        loaded.buses["electricity"].flows.to_frame(),
        output["buses"]["electricity"]["flows"],
        check_exact=True,
    )


@needs_cbc
def test_a_result_saved_without_the_flows_field_can_still_be_read(run):
    _, _, result = run
    data = json.loads(result.model_dump_json())
    for bus in data["buses"].values():
        del bus["flows"]

    old = ScenarioResult.model_validate(data)

    assert all(bus.flows is None for bus in old.buses.values())
    assert old.objective == pytest.approx(result.objective)
