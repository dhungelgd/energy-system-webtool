"""Scenario version 2: instances, carriers and blocks."""

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.scenario_v2 import ScenarioV2
from examples.make_examples_v2 import EXAMPLES, FOLDER

EL = {"id": "electricity", "label": "Electricity"}
H2 = {"id": "hydrogen", "label": "Hydrogen", "custom": True}


def component(component_id="grid", kind="source", direction="out", carrier="electricity", **changes):
    values = {"id": component_id, "name": "A component", "kind": kind,
              "connections": [{"carrier": carrier, "direction": direction}]}
    values.update(changes)
    return values


def scenario(**changes):
    values = {"carriers": [EL], "components": [component()]}
    values.update(changes)
    return ScenarioV2(**values)


def refused(match, **changes):
    with pytest.raises(ValidationError, match=match):
        scenario(**changes)


# ---------------------------------------------------------------------------
# a valid scenario
# ---------------------------------------------------------------------------

def test_an_empty_scenario_is_valid_and_has_the_defaults():
    empty = ScenarioV2()

    assert empty.schema_version == 2
    assert empty.name == "Unnamed scenario"
    assert (empty.carriers, empty.components, empty.series, empty.constraints) == ([], [], {}, [])
    assert empty.time.steps == 8760 and empty.solver.name == "cbc"


def test_a_minimal_scenario():
    minimal = scenario()

    assert minimal.component_ids() == ["grid"]
    assert minimal.carrier_ids() == ["electricity"]
    assert minimal.component("grid").kind == "source"


def test_an_unknown_component_is_named():
    with pytest.raises(KeyError, match="unknown component 'ghost'"):
        scenario().component("ghost")


def test_a_second_instance_of_the_same_template_is_fine():
    two = scenario(components=[
        component("pv_south", template="pv"), component("pv_east", template="pv"),
    ])

    assert two.component_ids() == ["pv_south", "pv_east"]


# ---------------------------------------------------------------------------
# ids, names, carriers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["PV", "pv system", "1pv", "pv-east", "", "a" * 41, "ä"])
def test_a_component_id_must_be_lower_case_letters_digits_and_underscores(bad):
    refused("pattern", components=[component(bad)])


def test_a_component_id_may_not_be_used_twice():
    refused("component id 'grid' is used twice", components=[component(), component()])


def test_a_carrier_may_not_be_listed_twice():
    refused("carrier 'electricity' is listed twice", carriers=[EL, EL])


def test_a_connection_needs_a_defined_carrier():
    refused("the carrier 'hydrogen' is not defined", components=[component(carrier="hydrogen")])


def test_a_user_defined_carrier_must_be_marked_and_a_built_in_one_must_not():
    refused("'hydrogen' is not built in; mark it as custom",
            carriers=[EL, {"id": "hydrogen", "label": "Hydrogen"}])
    refused("'heat' is built in and cannot be marked as custom",
            carriers=[EL, {"id": "heat", "label": "Heat", "custom": True}])


def test_names_are_trimmed_and_must_not_be_empty():
    assert scenario(name="  My system  ").name == "My system"
    assert scenario(components=[component(name="  Roof  ")]).components[0].name == "Roof"
    with pytest.raises(ValidationError):
        scenario(name="   ")


# ---------------------------------------------------------------------------
# connections and kinds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind, connections, text", [
    ("source", [("electricity", "in")], "a source only gives energy out"),
    ("source", [("electricity", "out"), ("heat", "in")], "a source only gives energy out"),
    ("sink", [("electricity", "out")], "a sink only takes energy in"),
    ("storage", [("electricity", "in")], "a storage has exactly one connection"),
    ("storage", [("electricity", "both"), ("heat", "both")], "a storage has exactly one connection"),
    ("converter", [("electricity", "in"), ("heat", "in")], "exactly one carrier and gives it to at least one"),
    ("converter", [("electricity", "in")], "exactly one carrier and gives it to at least one"),
    ("converter", [("electricity", "out"), ("heat", "out")], "exactly one carrier and gives it to at least one"),
    ("converter", [("electricity", "both"), ("heat", "out")], "exactly one carrier and gives it to at least one"),
    ("source", [("electricity", "out"), ("electricity", "out")], "connected twice in the same direction"),
])
def test_the_connections_must_fit_the_kind(kind, connections, text):
    refused(text, carriers=[EL, {"id": "heat", "label": "Heat"}],
            components=[{"id": "x", "name": "X", "kind": kind,
                         "connections": [{"carrier": c, "direction": d} for c, d in connections]}])


@pytest.mark.parametrize("kind, connections", [
    ("source", [("electricity", "out")]),
    ("sink", [("electricity", "in"), ("heat", "in")]),
    ("storage", [("heat", "both")]),
    ("converter", [("electricity", "in"), ("heat", "out")]),
    ("converter", [("gas", "in"), ("electricity", "out"), ("heat", "out")]),
])
def test_connections_that_fit_the_kind_are_accepted(kind, connections):
    scenario(carriers=[EL, {"id": "heat", "label": "Heat"}, {"id": "gas", "label": "Gas"}],
             components=[{"id": "x", "name": "X", "kind": kind,
                          "connections": [{"carrier": c, "direction": d} for c, d in connections]}])


def test_a_component_needs_at_least_one_connection_and_a_known_kind():
    with pytest.raises(ValidationError):
        scenario(components=[{"id": "x", "name": "X", "kind": "source", "connections": []}])
    with pytest.raises(ValidationError):
        scenario(components=[component(kind="link")])


# ---------------------------------------------------------------------------
# blocks
# ---------------------------------------------------------------------------

def test_an_unknown_block_is_named():
    refused("grid: unknown block 'magic'", components=[component(blocks={"magic": {}})])


def test_a_kind_cannot_have_a_block_that_is_not_for_it():
    refused("a source cannot have the block 'storage'", components=[component(blocks={"storage": {}})])
    refused("a sink cannot have the block 'profile'",
            components=[component(kind="sink", direction="in", blocks={"profile": {}})])


def test_the_settings_of_a_block_are_checked_and_reported_together():
    with pytest.raises(ValidationError) as error:
        scenario(components=[component(blocks={
            "capacity": {"mode": "invest", "capex": -1, "lifetime": 0},
            "costs": {"variable_costs": -2},
        })])

    text = str(error.value)
    assert "Investment cost must be at least 0" in text
    assert "Lifetime must be at least 1" in text
    assert "Variable costs must be at least 0" in text


def test_a_block_with_empty_values_is_fine():
    scenario(components=[component(blocks={"capacity": {"mode": "invest", "capex": None, "maximum": None}})])


def test_a_value_that_is_not_a_finite_number_is_refused():
    refused("not a finite number", components=[component(blocks={"costs": {"variable_costs": math.nan}})])
    refused("not a finite number", components=[component(blocks={"costs": {"variable_costs": math.inf}})])


def converter(blocks):
    return {"id": "conv", "name": "Converter", "kind": "converter",
            "connections": [{"carrier": "electricity", "direction": "in"},
                            {"carrier": "hydrogen", "direction": "out"}],
            "blocks": blocks}


def test_the_rated_flow_of_a_converter_must_be_one_of_its_connections():
    scenario(carriers=[EL, H2], components=[converter({"capacity": {"rated_flow": "hydrogen"}})])
    scenario(carriers=[EL, H2], components=[converter({"capacity": {"rated_flow": "electricity"}})])
    refused("the rated flow 'heat' is not one of its connections", carriers=[EL, H2],
            components=[converter({"capacity": {"rated_flow": "heat"}})])


def test_only_a_converter_has_a_rated_flow():
    refused("only a converter has a rated flow",
            components=[component(blocks={"capacity": {"rated_flow": "electricity"}})])


def test_the_conversion_outputs_must_be_carriers_the_converter_gives_to():
    scenario(carriers=[EL, H2], components=[converter({"conversion": {"outputs": {"hydrogen": {"efficiency": 65}}}})])
    refused("does not give energy to 'electricity'", carriers=[EL, H2],
            components=[converter({"conversion": {"outputs": {"electricity": {"efficiency": 65}}}})])


# ---------------------------------------------------------------------------
# time series
# ---------------------------------------------------------------------------

def test_a_block_may_only_refer_to_a_series_that_exists():
    refused("the time series 'pv_profile' does not exist",
            components=[component(blocks={"profile": {"series": "pv_profile"}})])
    refused("the time series 'cop' does not exist", carriers=[EL, H2],
            components=[converter({"conversion": {"outputs": {"hydrogen": {"ratio_series": "cop"}}}})])

    scenario(components=[component(blocks={"profile": {"series": "pv_profile"}})],
             series={"pv_profile": {"unit": "capacity factor", "values": [0.0, 0.5]}})


def test_a_series_that_nothing_uses_is_fine():
    assert "spare" in scenario(series={"spare": {"values": [1.0]}}).series


def test_series_ids_follow_the_same_rule_as_other_ids():
    with pytest.raises(ValidationError, match="lower case letters"):
        scenario(series={"Strom Bedarf": {"values": [1.0]}})


def test_empty_values_in_a_series_stay_visible_and_infinite_ones_are_refused():
    values = scenario(series={"s": {"values": [1, math.nan, None, 2.5]}}).series["s"].values

    assert values == [1.0, None, None, 2.5]
    with pytest.raises(ValidationError, match="infinite"):
        scenario(series={"s": {"values": [1.0, math.inf]}})


def test_a_series_remembers_where_it_came_from():
    kept = scenario(series={"s": {"unit": "kW", "source": {"file": "load.csv", "column": "Strom"},
                                  "values": [1.0]}}).series["s"]

    assert kept.source.file == "load.csv" and kept.source.column == "Strom"


# ---------------------------------------------------------------------------
# the file as a whole
# ---------------------------------------------------------------------------

def test_unknown_fields_are_refused_everywhere():
    with pytest.raises(ValidationError):
        ScenarioV2(colour="blue")
    with pytest.raises(ValidationError):
        scenario(components=[component(colour="blue")])
    with pytest.raises(ValidationError):
        scenario(carriers=[{"id": "electricity", "label": "E", "colour": "blue"}])


def test_constraints_are_reserved_and_must_be_empty_for_now():
    refused("constraints are not available yet", constraints=[{"type": "emission_limit"}])


def test_a_newer_layout_is_refused_with_a_clear_message():
    with pytest.raises(ValidationError, match="newer version of the tool"):
        ScenarioV2(schema_version=99)


def test_an_older_layout_says_it_has_to_be_converted():
    with pytest.raises(ValidationError, match="layout 1 scenario; it has to be converted"):
        ScenarioV2(schema_version=1)


def test_a_version_1_file_is_not_taken_for_a_version_2_file():
    v1 = (Path(__file__).resolve().parent.parent / "examples" / "scenarios" / "grid_only_24h.json").read_text(encoding="utf-8")

    with pytest.raises(ValidationError, match="layout 1 scenario"):
        ScenarioV2.model_validate_json(v1)


def test_all_problems_of_a_scenario_are_reported_together():
    with pytest.raises(ValidationError) as error:
        scenario(components=[
            component("a", carrier="ghost"), component("a", blocks={"magic": {}}),
        ], constraints=[{"type": "x"}])

    text = str(error.value)
    assert "carrier 'ghost' is not defined" in text
    assert "component id 'a' is used twice" in text
    assert "unknown block 'magic'" in text
    assert "constraints are not available yet" in text


def test_save_and_load_give_back_the_same_scenario(tmp_path):
    original = EXAMPLES["hydrogen_chain"]()

    original.save(tmp_path / "s.json")
    again = ScenarioV2.load(tmp_path / "s.json")

    assert again == original
    saved = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == 2
    assert [c["id"] for c in saved["components"]] == ["grid", "electrolyser", "h2_tank", "h2_demand"]


def test_a_changed_value_is_checked_again():
    changed = scenario(components=[component(blocks={"costs": {"variable_costs": 0.3}})])

    with pytest.raises(ValidationError):
        changed.name = "   "


# ---------------------------------------------------------------------------
# the three examples of the design
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", list(EXAMPLES))
def test_the_saved_example_equals_what_the_generator_makes(name):
    # if this fails, run: python -m examples.make_examples_v2
    assert ScenarioV2.load(FOLDER / f"{name}.json") == EXAMPLES[name]()


def test_every_example_file_comes_from_the_generator_and_the_other_way_round():
    assert {p.stem for p in Path(FOLDER).glob("*.json")} == set(EXAMPLES)


def test_pv_and_grid():
    example = EXAMPLES["pv_and_grid"]()

    assert example.component_ids() == ["demand", "grid", "pv"]
    assert example.carrier_ids() == ["electricity"]
    assert example.time.steps == 24
    assert all(len(s.values) == 24 for s in example.series.values())

    # the demand profile is a set of shares of the annual demand, as in the usual profiles
    demand = example.component("demand").blocks["demand"]
    shares = example.series["electricity_demand"].values
    assert demand == {"series": "electricity_demand", "profile_type": "annual_share", "annual_demand": 87600.0}
    assert sum(shares) * 365 == pytest.approx(1.0)                      # one day of a year of equal days
    assert sum(shares) * demand["annual_demand"] == pytest.approx(240.0)   # 87,600 kWh / 365 days


def test_two_pv_systems_are_two_instances_with_their_own_profile():
    example = EXAMPLES["two_pv_systems"]()
    south, east = example.component("pv_south"), example.component("pv_east")

    assert south.template == east.template == "pv"
    assert south.blocks["profile"]["series"] != east.blocks["profile"]["series"]
    assert south.blocks["capacity"]["mode"] == "fixed" and east.blocks["capacity"]["mode"] == "invest"
    assert example.series["pv_south_profile"].values != example.series["pv_east_profile"].values


def test_the_hydrogen_chain_uses_a_custom_carrier_and_percentages_as_percentages():
    from backend.blocks import BLOCKS

    example = EXAMPLES["hydrogen_chain"]()
    electrolyser, tank = example.component("electrolyser"), example.component("h2_tank")

    assert [c.id for c in example.carriers if c.custom] == ["hydrogen"]
    assert electrolyser.template is None and tank.template is None
    assert electrolyser.blocks["conversion"]["outputs"]["hydrogen"] == {"efficiency": 65.0}
    assert example.component("h2_demand").blocks["demand"]["profile_type"] == "absolute"
    assert tank.blocks["storage"]["efficiency_charge"] == 98.0
    # stored in the file, but not run by the engine yet
    assert "on_off" in electrolyser.blocks and not BLOCKS["on_off"].engine_supported