"""The decisions behind the NiceGUI scenario page (no NiceGUI needed)."""

import json
from pathlib import Path

import pytest

from backend.scenario import Scenario
from frontend_nicegui.scenario_view import (
    ScenarioFileError,
    component_labels,
    component_rows,
    describe_period,
    load_scenario,
    series_rows,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios"


def example(name):
    return Scenario.load(EXAMPLES / f"{name}.json")


# ---------------------------------------------------------------------------
# opening a file
# ---------------------------------------------------------------------------

def test_a_scenario_file_is_read():
    content = (EXAMPLES / "grid_only_24h.json").read_bytes()

    assert load_scenario(content).name == "Grid only, 24 hours"


def test_text_that_is_not_json_is_explained():
    with pytest.raises(ScenarioFileError, match="not valid JSON"):
        load_scenario(b"this is not json")


def test_json_that_is_not_a_scenario_is_explained_with_the_place_of_the_problem():
    with pytest.raises(ScenarioFileError, match="not a scenario.*components"):
        load_scenario(json.dumps({"components": ["demand", "ufo"]}).encode())


def test_a_saved_result_is_recognised_and_the_user_is_told_where_to_open_it():
    result_like = json.dumps({"objective": 72.0, "buses": {}, "horizon_hours": 24}).encode()

    with pytest.raises(ScenarioFileError, match="saved result.*Open a saved result"):
        load_scenario(result_like)


def test_a_scenario_from_a_newer_version_is_explained():
    newer = json.dumps({"schema_version": 99}).encode()

    with pytest.raises(ScenarioFileError, match="newer version"):
        load_scenario(newer)


def test_the_error_is_a_value_error():
    assert issubclass(ScenarioFileError, ValueError)


# ---------------------------------------------------------------------------
# what is shown
# ---------------------------------------------------------------------------

def test_readable_component_names_come_from_the_ui_registry():
    labels = component_labels()

    assert labels["pv"] == "PV System"
    assert labels["demand"] == "Electricity Demand"
    assert set(labels) >= {"grid", "battery", "heat_pump"}


@pytest.mark.parametrize("name, expected", [
    ("grid_only_24h", "24 hourly steps (1 days) from 01.01.2021 00:00"),
    ("pv_battery_week", "168 hourly steps (7 days) from 01.06.2021 00:00"),
])
def test_the_period_is_described(name, expected):
    assert describe_period(example(name)) == expected


def test_a_period_that_is_not_whole_days():
    assert describe_period(Scenario(time={"steps": 36})) == (
        "36 hourly steps (1.5 days) from 01.01.2021 00:00"
    )


def test_component_rows_show_name_mode_and_size():
    rows = component_rows(example("pv_battery_week"))
    by_name = {row["component"]: row for row in rows}

    assert [row["component"] for row in rows] == [
        "Electricity Demand", "Electricity Grid", "Grid Feed-in", "PV System", "Battery Storage",
    ]
    assert by_name["PV System"] == {"component": "PV System", "mode": "fixed", "size": "30"}
    assert by_name["Battery Storage"]["size"] == "40"
    assert by_name["Electricity Grid"] == {"component": "Electricity Grid", "mode": "-", "size": "-"}


def test_the_size_of_invest_and_unset_components():
    scenario = Scenario(
        components=["pv", "wind", "battery"],
        settings={
            "pv": {"mode": "invest", "maximum": 80.0},
            "wind": {"mode": "invest", "maximum": None},
            "battery": {"mode": "fixed", "capacity": None},
        },
    )
    sizes = {row["component"]: row["size"] for row in component_rows(scenario)}

    assert sizes == {
        "PV System": "up to 80",
        "Wind Turbine": "no upper limit",
        "Battery Storage": "not set",
    }


def test_a_component_without_settings_is_still_listed():
    rows = component_rows(Scenario(components=["demand"]))

    assert rows == [{"component": "Electricity Demand", "mode": "-", "size": "-"}]


def test_an_unknown_label_falls_back_to_the_key(monkeypatch):
    import frontend_nicegui.scenario_view as view

    monkeypatch.setattr(view, "component_labels", lambda: {})

    assert component_rows(Scenario(components=["demand"]))[0]["component"] == "demand"


def test_series_rows_count_values_and_empty_cells():
    scenario = Scenario(series={"electricity_demand": [1.0, None, 3.0, 0.25], "pv": []})
    rows = {row["series"]: row for row in series_rows(scenario)}

    assert rows["electricity_demand"] == {
        "series": "electricity_demand", "values": 4, "empty": 1, "min": "0.25", "max": "3",
    }
    assert rows["pv"] == {"series": "pv", "values": 0, "empty": 0, "min": "-", "max": "-"}