"""The decisions behind the NiceGUI scenario page (no NiceGUI needed)."""

import json
from pathlib import Path

import pytest

from backend.scenario_v2 import ScenarioV2
from examples.make_examples_v2 import EXAMPLES
from frontend_nicegui.scenario_view import (
    ScenarioFileError,
    component_rows,
    describe_period,
    load_scenario,
    series_rows,
)

FOLDER = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"


def example(name):
    return EXAMPLES[name]()


def scenario(components=(), series=None, **changes):
    return ScenarioV2(
        carriers=[{"id": "electricity", "label": "Electricity"}],
        components=list(components),
        series=series or {},
        **changes,
    )


def capacity_component(kind, blocks, template=None, name="Thing"):
    connections = {"source": "out", "sink": "in", "storage": "both"}[kind]
    return {"id": "thing", "name": name, "template": template, "kind": kind,
            "connections": [{"carrier": "electricity", "direction": connections}], "blocks": blocks}


# ---------------------------------------------------------------------------
# opening a file
# ---------------------------------------------------------------------------

def test_a_scenario_file_is_read():
    content = (FOLDER / "pv_and_grid.json").read_bytes()

    assert load_scenario(content).name == "PV and grid, one day"


def test_every_example_file_can_be_opened():
    for path in sorted(FOLDER.glob("*.json")):
        assert load_scenario(path.read_bytes()).name


def test_text_that_is_not_json_is_explained():
    with pytest.raises(ScenarioFileError, match="not valid JSON"):
        load_scenario(b"this is not json")


def test_json_that_is_not_a_scenario_is_explained_with_the_place_of_the_problem():
    with pytest.raises(ScenarioFileError, match="not a scenario.*components"):
        load_scenario(json.dumps({"components": ["demand", "ufo"]}).encode())


def test_a_problem_in_the_whole_file_is_explained_in_plain_words():
    broken = example("pv_and_grid").model_dump(mode="json")
    broken["components"][0]["connections"][0]["carrier"] = "ghost"

    with pytest.raises(ScenarioFileError, match=r"\(file: .*carrier 'ghost' is not defined\)") as error:
        load_scenario(json.dumps(broken).encode())

    assert "Value error" not in str(error.value)


def test_a_saved_result_is_recognised_and_the_user_is_told_where_to_open_it():
    result_like = json.dumps({"objective": 72.0, "buses": {}, "horizon_hours": 24}).encode()

    with pytest.raises(ScenarioFileError, match="saved result.*Open a saved result"):
        load_scenario(result_like)


def test_a_scenario_from_a_newer_version_is_explained():
    newer = json.dumps({"schema_version": 99}).encode()

    with pytest.raises(ScenarioFileError, match="newer version.*update the tool"):
        load_scenario(newer)


def test_a_scenario_in_the_old_format_is_explained_without_technical_words():
    from backend.scenario import Scenario

    old = Scenario(components=["demand"]).model_dump_json().encode()

    with pytest.raises(ScenarioFileError, match="old format that this version cannot open") as error:
        load_scenario(old)

    assert "layout" not in str(error.value)


def test_the_error_is_a_value_error():
    assert issubclass(ScenarioFileError, ValueError)


# ---------------------------------------------------------------------------
# the period
# ---------------------------------------------------------------------------

def test_the_period_is_described():
    assert describe_period(example("pv_and_grid")) == "24 hourly steps (1 days) from 01.01.2021 00:00"


def test_a_period_that_is_not_whole_days():
    assert describe_period(scenario(time={"steps": 36})) == "36 hourly steps (1.5 days) from 01.01.2021 00:00"


def test_a_period_with_another_start():
    start = scenario(time={"start": "2022-03-01T06:00:00", "steps": 168})

    assert describe_period(start) == "168 hourly steps (7 days) from 01.03.2022 06:00"


# ---------------------------------------------------------------------------
# the components
# ---------------------------------------------------------------------------

def test_component_rows_show_name_type_mode_and_size():
    rows = component_rows(example("pv_and_grid"))

    assert rows == [
        {"component": "Electricity demand", "type": "Electricity demand", "mode": "-", "size": "-"},
        {"component": "Electricity grid", "type": "Electricity grid", "mode": "-", "size": "-"},
        {"component": "PV system", "type": "PV system", "mode": "invest", "size": "up to 100 kW"},
    ]


def test_two_systems_of_one_template_are_two_rows_with_their_own_names():
    rows = component_rows(example("two_pv_systems"))
    by_name = {row["component"]: row for row in rows}

    assert [row["component"] for row in rows] == [
        "Electricity demand", "Electricity grid", "PV south roof", "PV east roof",
    ]
    assert by_name["PV south roof"] == {
        "component": "PV south roof", "type": "PV system", "mode": "fixed", "size": "60 kW"}
    assert by_name["PV east roof"]["size"] == "up to 40 kW"


def test_a_custom_component_says_so_and_its_size_has_the_unit_of_its_kind():
    rows = {row["component"]: row for row in component_rows(example("hydrogen_chain"))}

    assert rows["Electrolyser"]["type"] == "Custom component"
    assert rows["Electrolyser"]["size"] == "up to 300 kW"
    assert rows["Hydrogen tank"]["size"] == "up to 2000 kWh"            # a storage: kWh, not kW


def test_the_size_of_a_fixed_component_and_of_one_that_is_not_filled_in():
    found = scenario([
        {**capacity_component("source", {"capacity": {"mode": "fixed", "capacity": 12.5}}), "id": "a", "name": "A"},
        {**capacity_component("source", {"capacity": {"mode": "fixed"}}), "id": "b", "name": "B"},
        {**capacity_component("source", {"capacity": {"mode": "invest"}}), "id": "c", "name": "C"},
    ])

    assert [row["size"] for row in component_rows(found)] == ["12.5 kW", "not set", "no upper limit"]


def test_a_capacity_block_without_a_mode_is_a_fixed_one():
    found = scenario([capacity_component("source", {"capacity": {"capacity": 7.0}})])

    assert component_rows(found)[0]["mode"] == "fixed"
    assert component_rows(found)[0]["size"] == "7 kW"


def test_a_component_without_a_capacity_block_has_no_mode_and_no_size():
    found = scenario([capacity_component("source", {"costs": {"variable_costs": 0.3}})])

    assert component_rows(found)[0]["mode"] == "-" and component_rows(found)[0]["size"] == "-"


# ---------------------------------------------------------------------------
# the time series
# ---------------------------------------------------------------------------

def test_series_rows_count_values_and_empty_cells():
    found = scenario(series={"load": {"values": [1.0, None, 3.0, 0.25]}, "sun": {"values": []}})
    rows = {row["series"]: row for row in series_rows(found)}

    assert rows["load"] == {
        "series": "load", "unit": "-", "used_by": "nothing", "values": 4, "empty": 1, "min": "0.25", "max": "3",
    }
    assert rows["sun"]["values"] == 0 and rows["sun"]["min"] == "-" and rows["sun"]["max"] == "-"


def test_series_rows_say_which_component_uses_the_series_and_its_unit():
    rows = {row["series"]: row for row in series_rows(example("pv_and_grid"))}

    assert rows["electricity_demand"]["unit"] == "share of the annual demand"
    assert rows["electricity_demand"]["used_by"] == "Electricity demand"
    assert rows["pv_profile"]["used_by"] == "PV system"
    assert rows["pv_profile"]["values"] == 24


def test_each_pv_system_has_its_own_series():
    rows = {row["series"]: row for row in series_rows(example("two_pv_systems"))}

    assert rows["pv_south_profile"]["used_by"] == "PV south roof"
    assert rows["pv_east_profile"]["used_by"] == "PV east roof"


def test_a_series_that_several_components_use_names_them_all():
    shared = scenario(
        [
            {**capacity_component("source", {"profile": {"series": "sun"}}), "id": "a", "name": "Roof A"},
            {**capacity_component("source", {"profile": {"series": "sun"}}), "id": "b", "name": "Roof B"},
        ],
        series={"sun": {"values": [0.5]}},
    )

    assert series_rows(shared)[0]["used_by"] == "Roof A, Roof B"


def test_a_series_that_nothing_refers_to_says_so():
    assert series_rows(scenario(series={"spare": {"values": [1.0]}}))[0]["used_by"] == "nothing"


def test_the_series_of_a_demand_in_a_user_defined_chain_is_found():
    rows = {row["series"]: row for row in series_rows(example("hydrogen_chain"))}

    assert rows["h2_profile"]["used_by"] == "Hydrogen demand"


def test_a_cop_series_in_the_conversion_of_a_heat_pump_is_found():
    heat_pump = {
        "id": "hp", "name": "Heat pump", "template": "heat_pump", "kind": "converter",
        "connections": [{"carrier": "electricity", "direction": "in"}, {"carrier": "heat", "direction": "out"}],
        "blocks": {"conversion": {"outputs": {"heat": {"ratio_series": "cop"}}}},
    }
    found = ScenarioV2(
        carriers=[{"id": "electricity", "label": "Electricity"}, {"id": "heat", "label": "Heat"}],
        components=[heat_pump],
        series={"cop": {"unit": "ratio", "values": [3.0, 4.0]}},
    )

    assert series_rows(found)[0]["used_by"] == "Heat pump"