"""Tests for the Scenario model: checks, JSON round trip and the way into the backend."""

import json
import math
import time

import pandas as pd
import pytest
from pydantic import ValidationError

from backend.config_builder import build_config
from backend.input_schema import SolverConfig
from backend.scenario import SCHEMA_VERSION, SERIES_KEYS, Scenario
from backend.scenario_runner import run_scenario
from backend.system_check import check_system
from tests.helpers import needs_cbc


def small_scenario(**changes):
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


def error_text(excinfo):
    return str(excinfo.value)


# ---------------------------------------------------------------------------
# defaults and checks
# ---------------------------------------------------------------------------

def test_defaults():
    scenario = Scenario()

    assert scenario.name == "Unnamed scenario"
    assert scenario.components == []
    assert scenario.time.steps == 8760
    assert scenario.time.resolution == "1h"
    assert scenario.solver.name == "highs"
    assert scenario.schema_version == SCHEMA_VERSION


def test_name_is_trimmed_and_cannot_be_empty():
    assert small_scenario(name="  Halle 2  ").name == "Halle 2"

    with pytest.raises(ValidationError):
        small_scenario(name="   ")


def test_unknown_component_is_rejected_with_the_known_ones_listed():
    with pytest.raises(ValidationError) as error:
        small_scenario(components=["demand", "fusion_reactor"], settings={})

    assert "fusion_reactor" in error_text(error)
    assert "gas_boiler" in error_text(error)


def test_component_listed_twice_is_rejected():
    with pytest.raises(ValidationError, match="listed twice: grid"):
        small_scenario(components=["demand", "grid", "grid"], settings={})


def test_settings_for_a_component_that_is_not_selected_are_rejected():
    with pytest.raises(ValidationError, match="'pv'.*not selected"):
        small_scenario(settings={"pv": {"mode": "fixed", "capacity": 5.0}})


@pytest.mark.parametrize("key", ["mode", "price_mode", "cop_mode"])
def test_choice_settings_only_accept_known_values(key):
    with pytest.raises(ValidationError, match=key):
        small_scenario(
            components=["grid"],
            settings={"grid": {key: "sometimes"}},
        )


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_settings_must_be_finite_numbers(bad):
    with pytest.raises(ValidationError, match="finite"):
        small_scenario(settings={"demand": {"scaling_factor": bad}})


def test_empty_settings_are_allowed():
    scenario = small_scenario(settings={"demand": {"scaling_factor": None}})

    assert scenario.settings["demand"]["scaling_factor"] is None


def test_unknown_series_is_rejected():
    with pytest.raises(ValidationError, match="unknown time series 'solar'"):
        small_scenario(series={"solar": [1.0]})


def test_infinite_values_in_a_series_are_rejected():
    with pytest.raises(ValidationError, match="infinite"):
        small_scenario(series={"electricity_demand": [1.0, math.inf]})


def test_empty_values_in_a_series_are_kept_as_empty():
    scenario = small_scenario(series={"electricity_demand": [1.0, math.nan, None, 2]})

    assert scenario.series["electricity_demand"] == [1.0, None, None, 2.0]


def test_typos_in_field_names_are_rejected():
    with pytest.raises(ValidationError, match="Extra inputs"):
        Scenario(componnents=["demand"])


def test_wrong_time_settings_are_rejected():
    with pytest.raises(ValidationError):
        small_scenario(time={"steps": 0})
    with pytest.raises(ValidationError):
        small_scenario(time={"resolution": "15min"})


def test_changing_a_scenario_afterwards_is_checked_too():
    scenario = small_scenario()

    with pytest.raises(ValidationError, match="unknown components"):
        scenario.components = ["nope"]


def test_a_scenario_saved_by_a_newer_version_is_refused():
    with pytest.raises(ValidationError, match="newer version"):
        Scenario(schema_version=SCHEMA_VERSION + 1)


# ---------------------------------------------------------------------------
# the way into the backend and back
# ---------------------------------------------------------------------------

def test_to_inputs_gives_what_the_backend_functions_expect():
    selected, tech_inputs, input_data, solver = small_scenario().to_inputs()

    assert selected == ["demand", "grid"]
    assert tech_inputs["grid"] == {"price_mode": "constant", "variable_costs": 0.30}

    assert len(input_data["timeindex"]) == 24
    assert input_data["timeindex"][0] == pd.Timestamp("2021-01-01 00:00")
    assert input_data["timeindex"].freqstr == "h"
    assert input_data["electricity_demand"] == [1.0] * 24

    assert isinstance(solver, SolverConfig) and solver.name == "highs"


def test_to_inputs_restores_empty_values_as_nan():
    scenario = small_scenario(series={"electricity_demand": [1.0, None, 3.0]})
    _, _, input_data, _ = scenario.to_inputs()

    assert input_data["electricity_demand"][0] == 1.0
    assert math.isnan(input_data["electricity_demand"][1])


def test_to_inputs_does_not_share_data_with_the_scenario():
    scenario = small_scenario()
    _, tech_inputs, input_data, _ = scenario.to_inputs()

    tech_inputs["grid"]["variable_costs"] = 99.0
    input_data["electricity_demand"][0] = 99.0

    assert scenario.settings["grid"]["variable_costs"] == 0.30
    assert scenario.series["electricity_demand"][0] == 1.0


def test_from_inputs_is_the_reverse_of_to_inputs():
    original = small_scenario(
        series={"electricity_demand": [1.0, None] + [2.0] * 22},
        solver={"name": "cbc", "tee": True},
    )
    again = Scenario.from_inputs(*original.to_inputs(), name=original.name)

    assert again == original


def test_from_inputs_accepts_numpy_values():
    import numpy as np

    index = pd.date_range("2021-06-01", periods=3, freq="1h")
    scenario = Scenario.from_inputs(
        ["demand", "grid"],
        {"demand": {"scaling_factor": np.float64(5)},
         "grid": {"price_mode": "constant", "variable_costs": np.float64(0.3)}},
        {"timeindex": index, "electricity_demand": np.array([1.0, 2.0, np.nan])},
    )

    assert scenario.time.start.month == 6
    assert scenario.series["electricity_demand"] == [1.0, 2.0, None]
    assert type(scenario.settings["demand"]["scaling_factor"]) is float


def test_from_inputs_refuses_a_time_step_other_than_one_hour():
    index = pd.date_range("2021-01-01", periods=4, freq="15min")

    with pytest.raises(ValueError, match="hourly"):
        Scenario.from_inputs(["demand"], {}, {"timeindex": index})


def test_from_inputs_needs_a_time_index():
    with pytest.raises(ValueError, match="time index"):
        Scenario.from_inputs(["demand"], {}, {})


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def test_json_round_trip_keeps_everything():
    original = small_scenario(series={"electricity_demand": [1.0, None] + [2.5] * 22})

    again = Scenario.model_validate_json(original.model_dump_json())

    assert again == original


def test_saved_json_is_strict_json_without_nan():
    text = small_scenario(series={"electricity_demand": [1.0, math.nan] + [1.0] * 22}).model_dump_json()

    # parse_constant is called for NaN / Infinity, which are not valid JSON
    json.loads(text, parse_constant=lambda token: pytest.fail(f"{token} in JSON"))
    assert "NaN" not in text


def test_save_and_load_a_file(tmp_path):
    original = small_scenario()
    path = tmp_path / "scenario.json"

    original.save(path)

    assert Scenario.load(path) == original
    assert json.loads(path.read_text(encoding="utf-8"))["name"] == "Grid only"


def test_a_damaged_file_gives_a_validation_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"components": ["demand", "ufo"]}', encoding="utf-8")

    with pytest.raises(ValidationError, match="ufo"):
        Scenario.load(path)


def test_the_json_schema_can_be_published():
    schema = Scenario.model_json_schema()

    assert {"components", "settings", "series", "time", "solver"} <= set(schema["properties"])


def test_a_full_year_scenario_is_saved_and_loaded_quickly(tmp_path):
    series = {key: [(i % 97) / 100 for i in range(8760)] for key in SERIES_KEYS}
    scenario = Scenario(components=["demand"], series=series)
    path = tmp_path / "year.json"

    started = time.perf_counter()
    scenario.save(path)
    loaded = Scenario.load(path)
    seconds = time.perf_counter() - started

    assert loaded == scenario
    assert seconds < 3
    assert path.stat().st_size < 5_000_000


# ---------------------------------------------------------------------------
# with the real backend
# ---------------------------------------------------------------------------

def test_the_backend_check_works_on_a_scenario():
    selected, tech_inputs, input_data, _ = small_scenario().to_inputs()

    findings = check_system(selected, tech_inputs, input_data)

    assert [f.message for f in findings if f.level == "error"] == []


def test_the_backend_check_still_finds_problems_in_a_scenario():
    scenario = small_scenario(series={"electricity_demand": [1.0] * 10})
    selected, tech_inputs, input_data, _ = scenario.to_inputs()

    findings = check_system(selected, tech_inputs, input_data)

    assert any("10 values" in f.message for f in findings if f.level == "error")


@needs_cbc
def test_a_scenario_runs_and_gives_the_hand_calculated_cost():
    selected, tech_inputs, input_data, solver = small_scenario().to_inputs()

    config = build_config(selected, tech_inputs, input_data, solver)
    _, _, meta, _ = run_scenario(config, input_data, selected_techs=selected)

    # 10 kW * 24 h * 0.30 EUR/kWh
    assert meta["objective"] == pytest.approx(72.0)


@needs_cbc
def test_a_scenario_gives_the_same_result_after_saving_and_loading(tmp_path):
    path = tmp_path / "scenario.json"
    small_scenario().save(path)

    selected, tech_inputs, input_data, solver = Scenario.load(path).to_inputs()
    config = build_config(selected, tech_inputs, input_data, solver)
    _, _, meta, _ = run_scenario(config, input_data, selected_techs=selected)

    assert meta["objective"] == pytest.approx(72.0)
