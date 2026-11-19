"""Taking a scenario that was opened from a file into the draft (the state of the page, without NiceGUI)."""

import pytest

from frontend_nicegui.draft import NotEditable, ScenarioDraft
from frontend_nicegui.page_state import PageState
from tests.test_draft_from_scenario import EXAMPLES, full_draft


def opened(name="pv_and_grid"):
    state = PageState()
    state.open_file((EXAMPLES / f"{name}.json").read_bytes(), f"{name}.json")

    return state


def test_nothing_is_wrong_with_the_edit_of_nothing():
    state = PageState()

    assert state.edit_problem() is None and state.edit_opened() is False


def test_a_scenario_that_the_draft_can_hold_has_no_problem():
    assert opened("pv_and_grid").edit_problem() is None
    assert opened("with_problems").edit_problem() is None


@pytest.mark.parametrize("name, reason", [("two_pv_systems", "many"), ("hydrogen_chain", "carriers")])
def test_a_scenario_that_the_draft_cannot_hold_says_why(name, reason):
    problem = opened(name).edit_problem()

    assert isinstance(problem, NotEditable) and problem.reason == reason


def test_taking_the_scenario_in_replaces_what_was_built_in_place_and_closes_the_file():
    state = opened()
    state.draft.apply_template("Full system")
    held = state.draft                                                     # what the page keeps

    assert state.edit_opened() is True

    assert state.draft is held
    assert sorted(c.id for c in held.components()) == ["demand", "grid", "pv"] and held.steps == 24
    assert held.uses_series("demand") and held.uses_series("pv")
    assert state.opened is None and state.result is None and state.run_error is None and state.file_error is None


def test_what_belonged_to_the_old_scenario_is_forgotten():
    state = opened()
    state.draft.apply_template("Full system")
    state.draft_run = object()
    state.selected = "heat_pump"
    state.uploads["heat_pump"] = object()
    state.series_wanted.add("heat_pump")
    state.bulk_done = (3, "old.csv")

    state.edit_opened()

    assert state.draft_run is None and state.selected is None
    assert state.uploads == {} and state.series_wanted == set() and state.bulk_done is None


def test_a_file_that_the_draft_cannot_hold_changes_nothing():
    state = opened("two_pv_systems")
    state.draft.apply_template("PV system")
    before = state.draft.scenario().model_dump()
    state.selected = "pv"

    with pytest.raises(NotEditable):
        state.edit_opened()

    assert state.draft.scenario().model_dump() == before and state.opened is not None and state.selected == "pv"


def test_nothing_is_taken_in_while_a_run_is_going_on():
    state = opened()
    state.draft.set("demand")
    state.running = True

    assert state.edit_opened() is False

    assert [c.id for c in state.draft.components()] == ["demand"] and state.opened is not None


def test_the_draft_is_what_it_was_made_from_after_a_file_comes_back():
    saved = full_draft()
    state = PageState()
    state.open_file(saved.scenario().model_dump_json().encode(), "full.json")

    state.edit_opened()

    assert state.draft.scenario().model_dump() == saved.scenario().model_dump()


def test_the_draft_of_a_state_is_still_a_draft_that_goes_on_working_after_the_file_was_taken_in():
    state = opened()

    state.edit_opened()
    state.draft.set("battery")

    assert isinstance(state.draft, ScenarioDraft) and state.draft.is_selected("battery")