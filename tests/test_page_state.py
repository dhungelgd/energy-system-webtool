"""What the page remembers while a visitor uses it (no NiceGUI needed)."""

import json
from pathlib import Path

import pytest

from backend.i18n import Msg
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.page_state import OpenedFile, PageState

FOLDER = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"


def good(name="pv_and_grid"):
    return (FOLDER / f"{name}.json").read_bytes()


# ---------------------------------------------------------------------------
# the language
# ---------------------------------------------------------------------------

def test_a_new_page_has_its_language_a_draft_and_nothing_else():
    state = PageState("de")

    assert state.language == "de" and state.tr.language == "de"
    assert isinstance(state.draft, ScenarioDraft)
    assert state.opened is None and state.file_error is None
    assert state.result is None and state.run_error is None and state.running is False


def test_the_default_language_is_english():
    assert PageState().language == "en"


def test_the_language_can_be_changed_and_an_unknown_one_is_refused():
    state = PageState()

    state.language = "de"
    assert state.language == "de" and state.tr("scenario.heading") == "Ihr Szenario"

    with pytest.raises(ValueError, match="unknown language 'fr'"):
        state.language = "fr"

    assert state.language == "de"


def test_changing_the_language_keeps_everything_else():
    state = PageState()
    state.draft.apply_template("PV system")
    state.draft.name = "Bakery"
    state.open_file(good(), "pv_and_grid.json")
    state.finish_run(state.start_run(), result="the result")

    state.language = "de"

    assert state.draft.name == "Bakery" and len(state.draft) == 4
    assert state.opened.file_name == "pv_and_grid.json"
    assert state.result == "the result"


# ---------------------------------------------------------------------------
# the opened file
# ---------------------------------------------------------------------------

def test_a_good_file_is_opened():
    state = PageState()

    state.open_file(good(), "pv_and_grid.json")

    assert isinstance(state.opened, OpenedFile)
    assert state.opened.scenario.name == "PV and grid, one day"
    assert state.opened.file_name == "pv_and_grid.json"
    assert state.file_error is None


def test_a_bad_file_is_explained_and_nothing_stays_opened():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")

    state.open_file(b"this is not json", "notes.json")

    assert state.opened is None
    assert state.file_error == Msg("file_error.json")


def test_a_good_file_after_a_bad_one_clears_the_explanation():
    state = PageState()
    state.open_file(b"nope", "notes.json")

    state.open_file(good(), "pv_and_grid.json")

    assert state.file_error is None and state.opened is not None


def test_opening_a_file_removes_the_old_result_and_the_old_run_error():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")
    state.finish_run(state.start_run(), result="the result")
    assert state.result == "the result"

    state.open_file(good("two_pv_systems"), "two.json")

    assert state.result is None and state.run_error is None


def test_opening_a_bad_file_removes_the_old_result_too():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")
    state.finish_run(state.start_run(), result="the result")

    state.open_file(b"nope", "bad.json")

    assert state.result is None


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def test_a_run_needs_an_opened_file():
    assert PageState().start_run() is None


def test_a_run_starts_and_gives_back_what_is_run():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")

    started = state.start_run()

    assert started is state.opened and state.running is True


def test_only_one_run_at_a_time():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")
    state.start_run()

    assert state.start_run() is None


def test_the_result_is_kept_when_the_run_ends_and_the_file_is_still_open():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")

    state.finish_run(state.start_run(), result="the result")

    assert state.running is False and state.result == "the result" and state.run_error is None


def test_an_error_is_kept_when_the_run_fails():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")

    state.finish_run(state.start_run(), error=Msg("run.unexpected"))

    assert state.result is None and state.run_error == Msg("run.unexpected")


def test_a_new_run_removes_the_old_result():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")
    state.finish_run(state.start_run(), result="first")

    state.start_run()

    assert state.result is None and state.running is True


def test_the_outcome_of_a_run_is_dropped_when_another_file_was_opened_meanwhile():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")
    started = state.start_run()

    state.open_file(good("two_pv_systems"), "two.json")
    state.finish_run(started, result="the result of the first file")

    assert state.running is False                 # the run is over, a new one may start
    assert state.result is None and state.run_error is None


def test_the_outcome_of_a_run_is_dropped_when_a_bad_file_was_opened_meanwhile():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")
    started = state.start_run()

    state.open_file(b"nope", "bad.json")
    state.finish_run(started, result="the result")

    assert state.result is None and state.file_error == Msg("file_error.json")


def test_after_a_dropped_run_the_next_file_can_be_run():
    state = PageState()
    state.open_file(good(), "pv_and_grid.json")
    started = state.start_run()
    state.open_file(good("two_pv_systems"), "two.json")
    state.finish_run(started, result="old")

    assert state.start_run() is state.opened


def test_a_run_cannot_start_after_a_file_that_is_not_a_scenario():
    state = PageState()
    state.open_file(json.dumps({"x": 1}).encode(), "other.json")

    assert state.opened is None and state.start_run() is None