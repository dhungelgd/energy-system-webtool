"""A draft from a scenario (a file that was opened): what it holds, and why some scenarios are refused."""

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from backend.blocks import put_path
from backend.component_specs import INFO
from backend.scenario_v2 import Carrier, ScenarioV2, SeriesData, SeriesSource
from backend.series_input import has_series, slot_of
from backend.system_templates import SYSTEM_TEMPLATES
from frontend_nicegui.draft import EDIT_REASONS, NotEditable, ScenarioDraft
from frontend_nicegui.names import EDIT_PROBLEM_TEXTS

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"
DAY = [float(i) for i in range(24)]


def example(name):
    return ScenarioV2.model_validate_json((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def with_series(draft):
    """Give every component that has a time series one (with the file and the column it came from)."""

    for component in draft.components():
        if has_series(component):
            draft.set_series(component.id, SeriesData(
                unit="kW", source=SeriesSource(file=f"{component.id}.csv", column="Last"),
                values=[1.0 + hour + len(component.id) for hour in range(24)]))

    return draft


def full_draft():
    draft = ScenarioDraft(name="Full system", steps=24)
    draft.apply_template("Full system")

    return with_series(draft)


def dumped(draft):
    return draft.scenario().model_dump()


def refused(scenario):
    with pytest.raises(NotEditable) as problem:
        ScenarioDraft.from_scenario(scenario)

    return problem.value


# ---------------------------------------------------------------------------
# what is saved comes back as it was
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(INFO))
def test_each_kind_of_component_comes_back_from_its_own_file(key):
    draft = ScenarioDraft(name="Only one", steps=48)
    draft.set(key)

    again = ScenarioDraft.from_scenario(draft.scenario())

    assert dumped(again) == dumped(draft)


@pytest.mark.parametrize("template", sorted(SYSTEM_TEMPLATES))
def test_each_system_template_comes_back_with_its_time_series(template):
    draft = ScenarioDraft(name=template, steps=24)
    draft.apply_template(template)
    with_series(draft)

    again = ScenarioDraft.from_scenario(draft.scenario())

    assert dumped(again) == dumped(draft)


def test_what_was_typed_into_a_component_comes_back_too():
    draft = ScenarioDraft(name="Typed", steps=24)
    draft.apply_template("PV + battery")
    draft.component("battery").blocks["capacity"]["capacity"] = 12.5
    draft.component("pv").blocks["capacity"]["capacity"] = 7.25

    again = ScenarioDraft.from_scenario(draft.scenario())

    assert again.component("battery").blocks["capacity"]["capacity"] == 12.5
    assert again.component("pv").blocks["capacity"]["capacity"] == 7.25


def test_the_name_the_start_and_the_number_of_hours_come_back():
    draft = ScenarioDraft(name="  Mein Szenario äöü  ", start="2022-06-15", steps=168)
    draft.set("demand")

    again = ScenarioDraft.from_scenario(draft.scenario())

    assert (again.name, str(again.start), again.steps) == ("Mein Szenario äöü", "2022-06-15", 168)


def test_the_time_series_come_back_with_their_values_and_where_they_came_from():
    draft = full_draft()

    again = ScenarioDraft.from_scenario(draft.scenario())

    for component in draft.components():
        if has_series(component):
            before, after = draft.series_of(component.id), again.series_of(component.id)
            assert after.values == before.values and after.unit == "kW"
            assert (after.source.file, after.source.column) == (f"{component.id}.csv", "Last")
    assert again.uses_series("grid") and again.uses_series("heat_pump")


def test_a_series_that_is_empty_in_places_keeps_its_gaps():
    draft = ScenarioDraft(steps=24)
    draft.set("demand")
    draft.set_series("demand", SeriesData(values=[1.0, None, 3.0] + [2.0] * 21))

    again = ScenarioDraft.from_scenario(draft.scenario())

    assert again.series_of("demand").values[:3] == [1.0, None, 3.0]


def test_the_heat_pump_without_a_series_keeps_its_constant_and_with_one_goes_back_to_the_standard_one():
    draft = ScenarioDraft(steps=24)
    draft.set("heat_pump")
    standard = draft.component("heat_pump").blocks["conversion"]["outputs"]["heat"]["ratio"]
    draft.component("heat_pump").blocks["conversion"]["outputs"]["heat"]["ratio"] = 3.7

    assert ScenarioDraft.from_scenario(draft.scenario()).component("heat_pump").blocks["conversion"]["outputs"]["heat"]["ratio"] == 3.7

    with_series(draft)                                                     # the constant is replaced by the series ...
    again = ScenarioDraft.from_scenario(draft.scenario())
    again.clear_series("heat_pump")                                        # ... and the file does not hold it any more

    assert again.component("heat_pump").blocks["conversion"]["outputs"]["heat"]["ratio"] == standard


def test_the_draft_does_not_share_anything_with_the_scenario_it_was_made_from():
    scenario = full_draft().scenario()
    again = ScenarioDraft.from_scenario(scenario)

    scenario.components[0].blocks["capacity"] = {"capacity": 999.0}
    scenario.series[next(iter(scenario.series))].values[0] = -5.0

    assert dumped(again) != scenario.model_dump()
    assert again.components()[0].blocks.get("capacity") != {"capacity": 999.0}
    assert all(data.values[0] != -5.0 for data in (again.series_of(c.id) for c in again.components() if has_series(c)))


# ---------------------------------------------------------------------------
# the example files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["pv_and_grid", "with_problems"])
def test_an_example_that_a_draft_can_hold_comes_back_exactly(name):
    scenario = example(name)

    draft = ScenarioDraft.from_scenario(scenario)

    assert draft.scenario(scenario.name).model_dump() == scenario.model_dump()


def test_an_example_with_two_pv_systems_is_refused_with_the_kind_that_is_there_twice():
    problem = refused(example("two_pv_systems"))

    assert (problem.reason, problem.detail) == ("many", "pv")


def test_an_example_with_a_carrier_of_its_own_is_refused_with_the_carrier():
    problem = refused(example("hydrogen_chain"))

    assert (problem.reason, problem.detail) == ("carriers", "hydrogen")


# ---------------------------------------------------------------------------
# what is refused, and why
# ---------------------------------------------------------------------------

def plain():
    draft = ScenarioDraft(name="Plain", steps=24)
    draft.apply_template("PV system")

    return with_series(draft).scenario()


def test_a_start_that_is_not_midnight_is_refused():
    scenario = plain()
    scenario.time.start = datetime(2021, 1, 1, 6)

    assert refused(scenario).reason == "start_time"


def test_a_time_step_that_is_not_an_hour_is_refused_with_the_step():
    scenario = plain()
    scenario = scenario.model_copy(update={"time": scenario.time.model_copy(update={"resolution": "15min"})})

    problem = refused(scenario)

    assert (problem.reason, problem.detail) == ("resolution", "15min")


@pytest.mark.parametrize("steps", [0, 9000])
def test_a_period_outside_what_a_draft_allows_is_refused(steps):
    scenario = plain()
    scenario = scenario.model_copy(update={"time": scenario.time.model_copy(update={"steps": steps})})

    assert refused(scenario).reason == "period"


def test_a_start_in_a_year_a_draft_does_not_know_is_refused():
    scenario = plain()
    scenario.time.start = datetime(1900, 1, 1)

    assert refused(scenario).reason == "period"


def test_extra_constraints_are_refused():
    scenario = plain().model_copy(update={"constraints": [{"kind": "minimum", "value": 1}]})   # a scenario cannot hold them yet

    assert refused(scenario).reason == "constraints"


def test_a_carrier_that_the_user_defined_is_refused():
    scenario = plain()
    scenario.carriers = [*scenario.carriers, Carrier(id="hydrogen", label="Hydrogen", custom=True)]

    problem = refused(scenario)

    assert (problem.reason, problem.detail) == ("carriers", "hydrogen")


def test_a_component_of_a_kind_that_is_not_known_is_refused_with_its_name():
    scenario = plain()
    scenario.components[0].template = None

    problem = refused(scenario)

    assert (problem.reason, problem.detail) == ("no_template", scenario.components[0].name)


def test_a_template_that_does_not_exist_is_refused():
    scenario = plain()
    scenario.components[0].template = "fusion_reactor"

    assert refused(scenario).reason == "no_template"


def test_a_component_with_an_id_of_its_own_is_refused_with_its_name():
    data = plain().model_dump()
    pv = next(component for component in data["components"] if component["template"] == "pv")
    pv["id"] = "pv_roof"
    scenario = ScenarioV2.model_validate(data)

    problem = refused(scenario)

    assert (problem.reason, problem.detail) == ("own_id", pv["name"])


def test_two_components_of_one_kind_are_said_before_their_ids():
    data = plain().model_dump()
    pv = next(component for component in data["components"] if component["template"] == "pv")
    twin = copy.deepcopy(pv)
    twin["id"], twin["name"] = "pv_east", "PV east"
    slot = slot_of(next(c for c in ScenarioV2.model_validate(data).components if c.template == "pv"))
    put_path(twin["blocks"][slot.block], slot.field, "pv_east_profile")
    data["components"].append(twin)
    data["series"]["pv_east_profile"] = copy.deepcopy(data["series"][slot.series_id])

    assert refused(ScenarioV2.model_validate(data)).reason == "many"


def test_a_time_series_that_no_component_uses_is_refused_with_its_name():
    scenario = plain()
    scenario.series = {**scenario.series, "leftover": SeriesData(values=[1.0] * 24)}

    problem = refused(scenario)

    assert (problem.reason, problem.detail) == ("unused_series", "leftover")


def test_the_reason_that_is_found_first_is_the_one_that_is_given():
    scenario = plain().model_copy(update={"constraints": [{"kind": "minimum"}]})
    scenario.time.start = datetime(2021, 1, 1, 6)

    assert refused(scenario).reason == "start_time"


# ---------------------------------------------------------------------------
# every reason has a text, and the draft can be replaced in place
# ---------------------------------------------------------------------------

def test_every_reason_has_a_text_for_the_user_and_there_is_no_text_without_a_reason():
    assert set(EDIT_REASONS) == set(EDIT_PROBLEM_TEXTS)


def test_every_text_for_a_reason_is_in_both_catalogs():
    folder = Path(__file__).resolve().parent.parent / "backend" / "i18n"
    for language in ("en", "de"):
        catalog = json.loads((folder / f"{language}.json").read_text(encoding="utf-8"))
        assert all(key in catalog for key in EDIT_PROBLEM_TEXTS.values()), language


def test_a_reason_that_does_not_exist_cannot_be_raised():
    with pytest.raises(ValueError, match="unknown reason"):
        NotEditable("made_up")


def test_replacing_a_draft_changes_it_in_place_for_everyone_who_holds_it():
    mine = ScenarioDraft(name="Old", steps=24)
    mine.set("demand")
    held = mine                                                            # what the page keeps
    other = full_draft()

    mine.replace_with(other)

    assert held is mine and dumped(held) == dumped(other) and len(held) == len(other)
    assert held.uses_series("grid")


def test_a_draft_that_was_replaced_goes_on_working():
    mine = ScenarioDraft(steps=24)
    mine.set("demand")
    mine.replace_with(ScenarioDraft.from_scenario(example("pv_and_grid")))

    mine.set("battery")
    mine.set("pv", False)

    assert mine.is_selected("battery") and not mine.is_selected("pv") and not mine.uses_series("pv")