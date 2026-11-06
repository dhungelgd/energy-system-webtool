"""What the page remembers while a visitor uses it (no NiceGUI needed)."""

import json
from pathlib import Path

import pytest

from backend.i18n import Msg
from backend.scenario_v2 import SeriesData
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


# ---------------------------------------------------------------------------
# the time series that are being prepared
# ---------------------------------------------------------------------------

def test_the_files_that_are_being_prepared_belong_to_the_components_that_are_still_there():
    state = PageState()
    state.draft.apply_template("PV system")
    state.uploads = {"pv": object(), "demand": object(), "wind": object()}
    state.series_wanted = {"grid", "wind", "heat_pump"}

    state.drop_stale_uploads()

    assert set(state.uploads) == {"pv", "demand"}                           # the wind turbine is not part of the draft
    assert state.series_wanted == {"grid"}


def test_nothing_is_dropped_when_nothing_is_stale():
    state = PageState()
    state.draft.apply_template("Electricity only")
    first = object()
    state.uploads = {"demand": first}

    state.drop_stale_uploads()

    assert state.uploads == {"demand": first} and state.series_wanted == set()


# ---------------------------------------------------------------------------
# the run of the scenario that is being built
# ---------------------------------------------------------------------------

def ready_state():
    """A page state whose draft can be run: a demand with its series, and the grid, for one day."""

    state = PageState()
    state.draft.apply_template("Electricity only")
    state.draft.steps = 24
    state.draft.set_series("demand", SeriesData(values=[1 / 24] * 24))
    return state


def test_a_draft_without_errors_can_be_run_and_the_run_has_a_copy_of_the_scenario():
    state = ready_state()

    started = state.start_draft_run("Unnamed")

    assert started is not None and state.running is True and state.running_draft is True
    assert started.scenario.name == "Unnamed" and started.result is None and started.error is None
    assert state.draft_run is started
    state.draft.steps = 48                                         # the draft goes on, the run keeps what it got
    assert started.scenario.time.steps == 24


def test_nothing_is_run_when_nothing_is_chosen():
    assert PageState().start_draft_run() is None


def test_nothing_is_run_when_the_check_finds_errors():
    state = ready_state()
    state.draft.clear_series("demand")                              # the demand has no data now

    assert state.start_draft_run() is None
    assert state.running is False and state.draft_run is None


def test_nothing_is_run_while_something_else_is_running():
    state = ready_state()
    state.start_draft_run()

    assert state.start_draft_run() is None                         # the draft is running already

    other = ready_state()
    other.opened = OpenedFile(scenario=object(), file_name="x.json")
    other.start_run()
    assert other.start_draft_run() is None                         # the opened file is running


def test_a_file_that_is_opened_cannot_be_run_while_the_draft_is_running():
    state = ready_state()
    state.opened = OpenedFile(scenario=object(), file_name="x.json")
    state.start_draft_run()

    assert state.start_run() is None


def test_the_result_of_the_run_of_the_draft_is_kept_and_the_run_is_over():
    state = ready_state()
    started = state.start_draft_run()

    state.finish_draft_run(started, result="the result")

    assert state.running is False and state.running_draft is False
    assert state.draft_run.result == "the result" and state.draft_run.error is None


def test_the_error_of_a_run_of_the_draft_is_kept():
    state = ready_state()
    started = state.start_draft_run()

    state.finish_draft_run(started, error=Msg("run.unexpected"))

    assert state.draft_run.error == Msg("run.unexpected") and state.draft_run.result is None


def test_a_new_run_removes_the_result_of_the_old_one():
    state = ready_state()
    state.finish_draft_run(state.start_draft_run(), result="first")

    started = state.start_draft_run()

    assert started.result is None and state.draft_run is started


def test_the_end_of_a_run_that_is_not_the_current_one_is_ignored_but_frees_the_page():
    state = ready_state()
    old = state.start_draft_run()
    state.draft_run = None                                          # (the visitor started again)

    state.finish_draft_run(old, result="late")

    assert state.draft_run is None and state.running is False


def test_the_result_is_current_right_after_the_run_and_outdated_after_a_change():
    state = ready_state()
    assert state.draft_changed_since_run() is False                # nothing was run
    started = state.start_draft_run()
    assert state.draft_changed_since_run() is False                # it is running: no result yet

    state.finish_draft_run(started, result="the result")
    assert state.draft_changed_since_run() is False

    state.draft.steps = 48
    assert state.draft_changed_since_run() is True


@pytest.mark.parametrize("change", [
    lambda draft: setattr(draft, "start", "2022-03-01"),
    lambda draft: draft.set("pv", True),
    lambda draft: draft.set("grid", False),
    lambda draft: draft.set_series("demand", SeriesData(values=[2 / 24] * 24)),
    lambda draft: draft.clear_series("demand"),
])
def test_every_change_of_the_scenario_makes_the_result_outdated(change):
    state = ready_state()
    state.finish_draft_run(state.start_draft_run(), result="the result")

    change(state.draft)

    assert state.draft_changed_since_run() is True


def test_a_change_back_makes_the_result_current_again():
    state = ready_state()
    state.finish_draft_run(state.start_draft_run(), result="the result")
    state.draft.steps = 48
    assert state.draft_changed_since_run() is True

    state.draft.steps = 24

    assert state.draft_changed_since_run() is False


def test_the_name_of_the_scenario_does_not_make_the_result_outdated():
    # a name that nobody chose follows the language, and a name is not what was calculated
    state = ready_state()
    state.finish_draft_run(state.start_draft_run("Unnamed scenario"), result="the result")

    state.draft.name = "My system"
    assert state.draft_changed_since_run() is False

    state.language = "de"
    assert state.draft_changed_since_run() is False


# ---------------------------------------------------------------------------
# how long a run has been going on
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


def test_nothing_has_run_for_any_time_when_nothing_runs():
    state = ready_state()

    assert state.elapsed() == 0.0 and state.run_started is None


def test_the_time_of_a_run_of_the_draft_counts_from_its_start_and_stops_with_it():
    state = ready_state()
    state.clock = FakeClock()

    started = state.start_draft_run()
    assert state.elapsed() == 0.0

    state.clock.now += 72.5
    assert state.elapsed() == 72.5

    state.finish_draft_run(started, result="the result")
    assert state.elapsed() == 0.0 and state.run_started is None


def test_the_time_of_a_run_of_an_opened_file_counts_too():
    state = ready_state()
    state.opened = OpenedFile(scenario=object(), file_name="x.json")
    state.clock = FakeClock()

    started = state.start_run()
    state.clock.now += 5
    assert state.elapsed() == 5.0

    state.finish_run(started)
    assert state.elapsed() == 0.0


def test_a_run_that_cannot_start_does_not_start_the_clock():
    state = PageState()
    state.clock = FakeClock()

    assert state.start_draft_run() is None and state.start_run() is None
    assert state.run_started is None


def test_a_clock_that_goes_back_does_not_give_a_negative_time():
    state = ready_state()
    state.clock = FakeClock()
    state.start_draft_run()

    state.clock.now -= 10

    assert state.elapsed() == 0.0


def test_a_second_start_does_not_move_the_start_of_the_run_that_is_going_on():
    state = ready_state()
    state.clock = FakeClock()
    state.start_draft_run()
    state.clock.now += 30

    assert state.start_draft_run() is None
    assert state.elapsed() == 30.0