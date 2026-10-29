"""The scenario that a user builds in the page (no NiceGUI needed)."""

from datetime import date, datetime

import pytest

from backend.scenario_v2 import ScenarioV2
from backend.system_check import Finding
from backend.system_templates import SYSTEM_TEMPLATES
from frontend_nicegui.draft import (
    DEFAULT_NAME,
    MAX_STEPS,
    START_HINT,
    STEPS_HINT,
    ScenarioDraft,
    parse_start,
    parse_steps,
)


def keys(draft):
    return [component.id for component in draft.components()]


def messages(draft):
    return [finding.message for finding in draft.findings()]


# ---------------------------------------------------------------------------
# the start
# ---------------------------------------------------------------------------

def test_a_new_draft_is_empty_and_has_the_defaults_of_a_scenario():
    draft = ScenarioDraft()

    assert (draft.name, draft.start, draft.steps) == (DEFAULT_NAME, date(2021, 1, 1), 8760)
    assert len(draft) == 0 and draft.components() == []


# ---------------------------------------------------------------------------
# the name
# ---------------------------------------------------------------------------

def test_the_name_is_trimmed():
    draft = ScenarioDraft(name="  Bakery Meier  ")

    assert draft.name == "Bakery Meier"


def test_a_blank_name_becomes_the_default_name():
    draft = ScenarioDraft()
    draft.name = "   "

    assert draft.name == DEFAULT_NAME
    draft.name = None
    assert draft.name == DEFAULT_NAME


def test_a_name_that_is_too_long_is_refused_and_the_old_one_stays():
    draft = ScenarioDraft(name="Short")

    with pytest.raises(ValueError, match="at most 200 characters"):
        draft.name = "x" * 201

    assert draft.name == "Short"
    draft.name = "x" * 200
    assert len(draft.name) == 200


def test_a_name_that_is_not_text_is_refused():
    with pytest.raises(ValueError, match="has to be text"):
        ScenarioDraft().name = 5


# ---------------------------------------------------------------------------
# the number of steps
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [(1, 1), (24, 24), (8760, 8760), (MAX_STEPS, 8784), (48.0, 48)])
def test_steps_are_whole_numbers_from_1_to_a_leap_year(value, expected):
    assert parse_steps(value) == expected
    assert isinstance(parse_steps(value), int)


@pytest.mark.parametrize("value", [0, -1, 8785, 2.5, float("nan"), float("inf"), None, "24", True, [24]])
def test_other_steps_are_refused_with_a_sentence(value):
    with pytest.raises(ValueError) as error:
        parse_steps(value)

    assert str(error.value) == STEPS_HINT == "Enter a whole number from 1 to 8,784."


def test_steps_that_are_refused_leave_the_old_value():
    draft = ScenarioDraft(steps=168)

    with pytest.raises(ValueError):
        draft.steps = 0

    assert draft.steps == 168
    draft.steps = 24.0
    assert draft.steps == 24


# ---------------------------------------------------------------------------
# the start date
# ---------------------------------------------------------------------------

def test_a_start_can_be_a_date_a_datetime_or_text():
    assert parse_start(date(2022, 3, 1)) == date(2022, 3, 1)
    assert parse_start(datetime(2022, 3, 1, 15, 30)) == date(2022, 3, 1)
    assert parse_start("2022-03-01") == date(2022, 3, 1)
    assert parse_start("  2022-03-01 ") == date(2022, 3, 1)


@pytest.mark.parametrize("value", ["2022-13-01", "2022-02-30", "01.03.2022", "2022/03/01", "20220301", "", None, 2022])
def test_other_starts_are_refused_with_a_sentence(value):
    with pytest.raises(ValueError) as error:
        parse_start(value)

    assert str(error.value) == START_HINT
    assert "YYYY-MM-DD" in START_HINT


def test_the_years_are_limited_to_what_the_weather_data_covers():
    assert parse_start("1980-01-01") == date(1980, 1, 1)
    assert parse_start("2100-12-31") == date(2100, 12, 31)

    for text in ("1979-12-31", "2101-01-01", "0001-01-01"):
        with pytest.raises(ValueError, match="1980 to 2100"):
            parse_start(text)


def test_a_start_that_is_refused_leaves_the_old_value():
    draft = ScenarioDraft(start="2022-03-01")

    with pytest.raises(ValueError):
        draft.start = "tomorrow"

    assert draft.start == date(2022, 3, 1)


# ---------------------------------------------------------------------------
# the components
# ---------------------------------------------------------------------------

def test_components_can_be_added_and_removed():
    draft = ScenarioDraft()

    draft.set("pv")
    draft.set("demand", True)

    assert draft.is_selected("pv") and draft.is_selected("demand") and not draft.is_selected("wind")
    assert len(draft) == 2

    draft.set("pv", False)

    assert not draft.is_selected("pv") and len(draft) == 1


def test_adding_twice_keeps_the_component_and_removing_what_is_not_there_does_no_harm():
    draft = ScenarioDraft()
    draft.set("pv")
    first = draft.component("pv")

    draft.set("pv")
    draft.set("wind", False)

    assert draft.component("pv") is first
    assert len(draft) == 1


def test_an_unknown_component_is_refused_and_changes_nothing():
    draft = ScenarioDraft()
    draft.set("pv")

    with pytest.raises(KeyError, match="unknown component 'ufo'"):
        draft.set("ufo")

    assert keys(draft) == ["pv"]


def test_the_order_is_by_group_whatever_order_the_components_were_added_in():
    draft = ScenarioDraft()
    for key in ("battery", "pv", "grid", "demand"):
        draft.set(key)

    assert keys(draft) == ["demand", "grid", "pv", "battery"]


def test_a_new_component_has_its_default_settings():
    draft = ScenarioDraft()
    draft.set("pv")

    capacity = draft.component("pv").blocks["capacity"]

    assert capacity["capex"] == 1200.0 and capacity["mode"] == "fixed"


def test_a_component_that_is_not_part_of_the_draft_cannot_be_asked_for():
    with pytest.raises(KeyError):
        ScenarioDraft().component("pv")


# ---------------------------------------------------------------------------
# system templates
# ---------------------------------------------------------------------------

def test_a_template_chooses_exactly_its_components():
    draft = ScenarioDraft()

    draft.apply_template("PV + battery")

    assert keys(draft) == ["demand", "grid", "grid_feedin", "pv", "battery"]


def test_another_template_replaces_the_first():
    draft = ScenarioDraft()
    draft.apply_template("PV + battery")

    draft.apply_template("Electricity only")

    assert keys(draft) == ["demand", "grid"]


def test_what_was_typed_into_a_component_stays_when_a_template_keeps_it():
    draft = ScenarioDraft()
    draft.apply_template("PV + battery")
    pv = draft.component("pv")
    pv.blocks["capacity"]["capex"] = 999.0

    draft.apply_template("PV system")

    assert draft.component("pv") is pv
    assert draft.component("pv").blocks["capacity"]["capex"] == 999.0


def test_a_component_that_was_removed_starts_again_with_its_defaults():
    draft = ScenarioDraft()
    draft.apply_template("PV system")
    draft.component("pv").blocks["capacity"]["capex"] = 999.0

    draft.apply_template("Electricity only")
    draft.apply_template("PV system")

    assert draft.component("pv").blocks["capacity"]["capex"] == 1200.0


def test_the_full_system_has_every_component():
    draft = ScenarioDraft()

    draft.apply_template("Full system")

    assert len(draft) == 13


def test_an_unknown_template_is_refused_and_changes_nothing():
    draft = ScenarioDraft()
    draft.apply_template("Electricity only")

    with pytest.raises(KeyError, match="unknown template 'Nonsense'"):
        draft.apply_template("Nonsense")

    assert keys(draft) == ["demand", "grid"]


def test_clearing():
    draft = ScenarioDraft()
    draft.apply_template("Full system")

    draft.clear()

    assert len(draft) == 0 and draft.components() == []


# ---------------------------------------------------------------------------
# the scenario it makes
# ---------------------------------------------------------------------------

def test_the_scenario_has_the_name_the_period_and_the_components_in_order():
    draft = ScenarioDraft(name="Bakery", start="2022-03-01", steps=168)
    draft.apply_template("CHP system")

    scenario = draft.scenario()

    assert isinstance(scenario, ScenarioV2)
    assert scenario.name == "Bakery"
    assert scenario.time.start == datetime(2022, 3, 1, 0, 0) and scenario.time.steps == 168
    assert scenario.component_ids() == ["demand", "heat_demand", "grid", "grid_feedin", "gas_import",
                                        "gas_boiler", "chp"]
    assert scenario.series == {}


def test_the_carriers_follow_the_components():
    draft = ScenarioDraft()
    draft.apply_template("Gas heating")

    assert draft.scenario().carrier_ids() == ["heat", "gas"]


def test_an_empty_draft_gives_a_valid_empty_scenario():
    scenario = ScenarioDraft().scenario()

    assert scenario.components == [] and scenario.carriers == []


@pytest.mark.parametrize("name", list(SYSTEM_TEMPLATES))
def test_every_template_gives_a_valid_scenario_with_all_its_components(name):
    draft = ScenarioDraft()
    draft.apply_template(name)

    scenario = draft.scenario()

    assert sorted(scenario.component_ids()) == sorted(SYSTEM_TEMPLATES[name])


def test_the_scenario_is_a_copy_in_both_directions():
    draft = ScenarioDraft()
    draft.apply_template("PV system")

    scenario = draft.scenario()
    scenario.component("pv").blocks["capacity"]["capex"] = 1.0
    assert draft.component("pv").blocks["capacity"]["capex"] == 1200.0

    draft.component("pv").blocks["capacity"]["capex"] = 5.0
    assert scenario.component("pv").blocks["capacity"]["capex"] == 1.0


# ---------------------------------------------------------------------------
# the system check of the draft
# ---------------------------------------------------------------------------

def test_an_empty_draft_is_told_that_a_demand_is_missing():
    assert messages(ScenarioDraft()) == ["No demand selected. Add an electricity demand or a heat demand."]


def test_the_findings_are_findings_with_a_level():
    draft = ScenarioDraft()
    draft.apply_template("PV + battery")

    found = draft.findings()

    assert found and all(isinstance(finding, Finding) for finding in found)
    assert {finding.level for finding in found} <= {"error", "warning"}


def test_a_draft_with_defaults_says_what_is_still_missing():
    draft = ScenarioDraft()
    draft.apply_template("Gas heating")

    found = messages(draft)

    assert any(m.startswith("Heat demand: no time series") for m in found)
    assert any(m.startswith("Gas boiler: fixed mode needs a capacity") for m in found)
    assert len(found) == 2


def test_the_findings_follow_the_components():
    draft = ScenarioDraft()
    draft.apply_template("Gas heating")

    draft.set("demand")
    assert any(m.startswith("Electricity demand: no time series") for m in messages(draft))

    draft.set("demand", False)
    draft.set("gas_boiler", False)
    assert not any(m.startswith("Gas boiler") for m in messages(draft))


def test_what_is_typed_into_a_component_is_part_of_the_next_check():
    draft = ScenarioDraft()
    draft.apply_template("PV system")
    assert any(m.startswith("PV system: fixed mode needs a capacity") for m in messages(draft))

    draft.component("pv").blocks["capacity"]["capacity"] = 50.0

    assert not any(m.startswith("PV system: fixed mode needs a capacity") for m in messages(draft))


@pytest.mark.parametrize("name", list(SYSTEM_TEMPLATES))
def test_the_check_runs_for_every_template(name):
    draft = ScenarioDraft()
    draft.apply_template(name)

    found = draft.findings()

    assert any(finding.level == "error" for finding in found)      # no data yet
    assert all(finding.message for finding in found)


def test_the_period_is_part_of_the_check():
    draft = ScenarioDraft(steps=24)
    draft.apply_template("Electricity only")
    scenario = draft.scenario()
    assert scenario.time.steps == 24

    draft.steps = 8760

    assert draft.scenario().time.steps == 8760