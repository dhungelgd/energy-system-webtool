"""The component specifications: settings, visibility rules, checks and topology."""

import pytest
from pydantic import ValidationError

from backend.component_specs import (
    PV,
    SPECS,
    ComponentSpec,
    Connection,
    FieldSpec,
    get_spec,
)
from backend.scenario import Scenario

FIXED = {"mode": "fixed", "capacity": 30.0}
INVEST = {"mode": "invest", "capex": 1200.0, "opex": 2.0, "lifetime": 25.0,
          "interest_rate": 3.0, "maximum": 100.0}


def visible_keys(settings):
    return [f.key for f in PV.visible_fields(settings)]


# ---------------------------------------------------------------------------
# what the PV specification says
# ---------------------------------------------------------------------------

def test_the_pv_system_is_a_source_that_feeds_the_electricity_bus():
    assert PV.role == "source"
    assert PV.connections == (Connection(bus="electricity", direction="out"),)
    assert get_spec("pv") is PV
    assert get_spec("wind") is None            # not specified yet


def test_every_setting_has_a_label_and_a_help_text_and_labels_are_in_sentence_case():
    for field in PV.fields:
        assert field.label and field.help, field.key

        first, *rest = field.label.split()
        assert first[0].isupper(), field.key
        # no Title Case: later words are lower case, or an abbreviation such as PV
        assert all(word.islower() or word.isupper() for word in rest), field.label


def test_every_number_has_a_unit_and_a_range():
    for field in PV.fields:
        if field.kind == "number":
            assert field.unit, f"{field.key} has no unit"
            assert field.minimum is not None, f"{field.key} has no minimum"


def test_the_pv_profile_is_a_capacity_factor_between_zero_and_one():
    (profile,) = PV.series

    assert profile.key == "pv"
    assert profile.profile == "capacity_factor"
    assert profile.expected_range == (0.0, 1.0)


def test_the_defaults():
    assert PV.defaults() == {
        "mode": "fixed", "capex": 1200.0, "opex": 2.0, "lifetime": 25.0, "interest_rate": 3.0,
    }


def test_the_sections():
    sections = {f.key: f.section for f in PV.fields}

    assert sections["mode"] == sections["capacity"] == "basic"
    assert {sections[k] for k in ("maximum", "capex", "opex", "lifetime", "interest_rate")} == {"investment"}


# ---------------------------------------------------------------------------
# which fields are shown
# ---------------------------------------------------------------------------

def test_a_fixed_size_shows_only_the_size():
    assert visible_keys(FIXED) == ["mode", "capacity"]


def test_an_optimizer_chosen_size_shows_the_cost_fields_and_the_limit():
    assert visible_keys(INVEST) == ["mode", "maximum", "capex", "opex", "lifetime", "interest_rate"]


def test_without_a_mode_the_default_mode_decides():
    assert visible_keys({}) == ["mode", "capacity"]


def test_every_field_is_shown_in_one_of_the_two_modes_and_none_in_both_by_accident():
    for field in PV.fields:
        shown = [mode for mode in ("fixed", "invest") if PV.is_visible(field, {"mode": mode})]
        assert shown, f"{field.key} is never shown"
    assert PV.field("capacity").visible_if != PV.field("capex").visible_if


# ---------------------------------------------------------------------------
# what is refused
# ---------------------------------------------------------------------------

def test_good_settings_have_no_problems():
    assert PV.problems(FIXED) == []
    assert PV.problems(INVEST) == []
    assert PV.problems({}) == []


def test_empty_values_are_not_wrong_the_form_is_just_not_filled_in_yet():
    assert PV.problems({"mode": "fixed", "capacity": None}) == []
    assert PV.problems({"mode": "invest", "capex": None, "maximum": None}) == []


@pytest.mark.parametrize("settings, text", [
    ({"mode": "fixed", "capacity": -1}, "PV system: Installed size must be at least 0 kW"),
    ({"mode": "invest", "maximum": -5}, "Maximum size must be at least 0 kW"),
    ({"mode": "invest", "capex": -100}, "Investment cost must be at least 0 € per kW"),
    ({"mode": "invest", "opex": 101}, "Running cost must be at most 100"),
    ({"mode": "invest", "lifetime": 0}, "Lifetime must be at least 1 years"),
    ({"mode": "invest", "lifetime": 500}, "Lifetime must be at most 100 years"),
    ({"mode": "invest", "interest_rate": -1}, "Interest rate must be at least 0"),
    ({"mode": "invest", "interest_rate": 250}, "Interest rate must be at most 100"),
])
def test_values_outside_the_range_are_named(settings, text):
    problems = PV.problems(settings)

    assert len(problems) == 1
    assert text in problems[0]


def test_an_interest_rate_of_zero_is_allowed():
    assert PV.problems({"mode": "invest", "interest_rate": 0.0}) == []


def test_text_and_yes_no_are_not_numbers():
    assert "must be a number" in PV.problems({"mode": "fixed", "capacity": "ten"})[0]
    assert "must be a number" in PV.problems({"mode": "fixed", "capacity": True})[0]


def test_a_mode_that_does_not_exist_is_named_with_the_allowed_ones():
    problems = PV.problems({"mode": "sometimes"})

    assert problems == ["PV system: How is the size decided? must be one of: fixed, invest"]


def test_an_unknown_setting_is_refused():
    assert PV.problems({"mode": "fixed", "colour": "blue"}) == ["PV system: unknown setting 'colour'"]


def test_the_column_name_of_the_profile_is_allowed_but_must_be_text():
    assert PV.problems({"mode": "fixed", "pv": "Erzeugung PV"}) == []
    assert "must be text" in PV.problems({"mode": "fixed", "pv": 5})[0]


def test_hidden_settings_are_not_checked():
    # a stale cost value from an earlier choice does not block a fixed size
    assert PV.problems({"mode": "fixed", "capacity": 10.0, "capex": -50}) == []
    # but the same value is refused as soon as it is visible
    assert PV.problems({"mode": "invest", "capex": -50})


def test_all_problems_are_reported_together():
    problems = PV.problems({"mode": "invest", "capex": -1, "lifetime": 0, "interest_rate": 300, "colour": 1})

    assert len(problems) == 4


# ---------------------------------------------------------------------------
# in a scenario
# ---------------------------------------------------------------------------

def scenario_with(pv_settings):
    return Scenario(components=["demand", "pv"], settings={"pv": pv_settings})


def test_a_scenario_accepts_good_pv_settings():
    assert scenario_with(INVEST).settings["pv"]["maximum"] == 100.0


def test_a_scenario_refuses_a_negative_size_and_says_what_is_wrong():
    with pytest.raises(ValidationError, match="PV system: Installed size must be at least 0 kW"):
        scenario_with({"mode": "fixed", "capacity": -5})


def test_a_scenario_reports_every_problem_at_once():
    with pytest.raises(ValidationError) as error:
        scenario_with({"mode": "invest", "capex": -1, "lifetime": 0})

    assert "Investment cost" in str(error.value) and "Lifetime" in str(error.value)


def test_a_scenario_with_an_incomplete_form_is_fine():
    assert scenario_with({"mode": "invest", "capex": None}).components == ["demand", "pv"]


def test_other_components_are_not_checked_by_a_specification_yet():
    scenario = Scenario(components=["wind"], settings={"wind": {"mode": "fixed", "capacity": -5.0}})

    assert scenario.settings["wind"]["capacity"] == -5.0


# ---------------------------------------------------------------------------
# the specification checks itself
# ---------------------------------------------------------------------------

def spec(**changes):
    values = dict(
        key="x", label="X", group="G", role="source",
        connections=(Connection(bus="electricity", direction="out"),),
    )
    values.update(changes)
    return ComponentSpec(**values)


def test_a_specification_cannot_be_changed_afterwards():
    with pytest.raises(ValidationError):
        PV.label = "Solar"


def test_a_minimum_above_the_maximum_is_refused():
    with pytest.raises(ValidationError, match="minimum is above the maximum"):
        FieldSpec(key="a", label="A", kind="number", minimum=5, maximum=1)


def test_a_choice_needs_options_and_a_default_among_them():
    with pytest.raises(ValidationError, match="needs options"):
        FieldSpec(key="a", label="A", kind="choice")
    with pytest.raises(ValidationError, match="default is not one of the options"):
        FieldSpec(key="a", label="A", kind="choice", options=("x", "y"), default="z")


def test_a_visibility_rule_must_refer_to_a_choice_with_those_values():
    mode = FieldSpec(key="mode", label="Mode", kind="choice", options=("a", "b"))

    with pytest.raises(ValidationError, match="not a choice"):
        spec(fields=(FieldSpec(key="n", label="N", kind="number", visible_if={"ghost": ("a",)}),))
    with pytest.raises(ValidationError, match="unknown values"):
        spec(fields=(mode, FieldSpec(key="n", label="N", kind="number", visible_if={"mode": ("c",)})))


def test_a_setting_cannot_be_listed_twice():
    field = FieldSpec(key="n", label="N", kind="number")

    with pytest.raises(ValidationError, match="listed twice"):
        spec(fields=(field, field))


@pytest.mark.parametrize("role, direction", [
    ("source", "in"), ("sink", "out"), ("storage", "in"), ("converter", "out"),
])
def test_the_role_and_the_connections_must_agree(role, direction):
    with pytest.raises(ValidationError):
        spec(role=role, connections=(Connection(bus="heat", direction=direction),))


def test_a_converter_needs_an_input_and_an_output():
    converter = spec(role="converter", connections=(
        Connection(bus="gas", direction="in"), Connection(bus="heat", direction="out"),
    ))

    assert converter.role == "converter"


def test_every_registered_specification_is_stored_under_its_own_key():
    assert all(key == s.key for key, s in SPECS.items())


# ---------------------------------------------------------------------------
# guards: stay in step with the Streamlit interface and the model while both exist
# ---------------------------------------------------------------------------

def test_the_specification_knows_every_setting_the_streamlit_interface_has():
    from frontend.ui_registry import UI_REGISTRY

    registry_keys = {f["key"] for f in UI_REGISTRY["pv"]["inputs"]}

    assert registry_keys <= PV.allowed_keys()


def test_the_defaults_are_the_same_as_in_the_streamlit_interface():
    from frontend.ui_defaults import TECH_DEFAULTS
    from frontend.ui_registry import UI_REGISTRY

    shown = dict(TECH_DEFAULTS["pv"])
    for field in UI_REGISTRY["pv"]["inputs"]:
        if "default" in field:
            shown.setdefault(field["key"], field["default"])

    for key, default in shown.items():
        if default is not None:
            assert PV.defaults().get(key) == default, key


def test_the_modes_and_the_profile_key_are_the_same_as_in_the_streamlit_interface():
    from frontend.ui_registry import UI_REGISTRY

    registry_mode = next(f for f in UI_REGISTRY["pv"]["inputs"] if f["key"] == "mode")

    assert PV.field("mode").options == tuple(registry_mode["options"])
    assert PV.series[0].key == UI_REGISTRY["pv"]["timeseries"]["key"]


def test_the_connections_are_the_buses_the_model_really_uses():
    from backend.tech_config_registry import TECH_CONFIG_REGISTRY

    config = TECH_CONFIG_REGISTRY["pv"](tech_inputs={"pv": {}}, input_data={})

    assert {f"{c.bus}_bus" for c in PV.connections} == {config["bus"]}


def test_a_minimum_that_is_excluded_needs_a_minimum():
    with pytest.raises(ValueError, match="needs a minimum"):
        FieldSpec(key="a", label="A", kind="number", minimum_exclusive=True)

    assert FieldSpec(key="a", label="A", kind="number", minimum=0, minimum_exclusive=True).minimum_exclusive
    assert not FieldSpec(key="a", label="A", kind="number", minimum=0).minimum_exclusive