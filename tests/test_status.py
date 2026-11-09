"""The status of the draft in the top bar: which state it is in, what it says, and when the Run button may be pressed."""

import json
from pathlib import Path

import pytest

from backend.i18n import ENGLISH, Translator
from frontend_nicegui.status import COLORS, ICONS, TEXTS, Status, badge_of, draft_status, run_hint, status_text

DE = Translator("de")
CATALOGS = Path(__file__).resolve().parent.parent / "backend" / "i18n"
KINDS = ("empty", "running", "errors", "outdated", "warnings", "ready")


def status(**changes):
    values = dict(has_components=True, errors=0, warnings=0, running=False, outdated=False)
    values.update(changes)
    return draft_status(**values)


# ---------------------------------------------------------------------------
# which state
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("changes, kind", [
    ({}, "ready"),
    ({"warnings": 2}, "warnings"),
    ({"errors": 1}, "errors"),
    ({"errors": 1, "warnings": 3}, "errors"),
    ({"outdated": True}, "outdated"),
    ({"outdated": True, "warnings": 1}, "outdated"),
    ({"has_components": False}, "empty"),
    ({"running": True}, "running"),
])
def test_the_state_follows_what_is_known(changes, kind):
    assert status(**changes).kind == kind


@pytest.mark.parametrize("changes, kind", [
    ({"running": True, "has_components": False, "errors": 2, "outdated": True}, "running"),       # a run comes first
    ({"has_components": False, "errors": 2, "outdated": True}, "empty"),                          # then what is missing
    ({"errors": 2, "outdated": True, "warnings": 1}, "errors"),                                   # then errors
    ({"outdated": True, "warnings": 1}, "outdated"),                                              # then the old result
])
def test_the_order_of_the_states(changes, kind):
    assert status(**changes).kind == kind


@pytest.mark.parametrize("kind, can_run", [
    ("ready", True), ("warnings", True), ("outdated", True), ("empty", False), ("errors", False), ("running", False),
])
def test_only_a_draft_without_errors_that_is_not_running_can_be_run(kind, can_run):
    assert Status(kind).can_run is can_run


def test_the_counts_are_kept():
    found = status(errors=2, warnings=1)

    assert (found.errors, found.warnings) == (2, 1)


# ---------------------------------------------------------------------------
# the words
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("current, english, german", [
    (Status("empty"), "Choose components", "Komponenten wählen"),
    (Status("ready"), "Ready", "Bereit"),
    (Status("outdated"), "Result outdated", "Ergebnis veraltet"),
    (Status("errors", errors=1), "1 error", "1 Fehler"),
    (Status("errors", errors=3), "3 errors", "3 Fehler"),
    (Status("errors", errors=1, warnings=1), "1 error, 1 warning", "1 Fehler, 1 Warnung"),
    (Status("errors", errors=2, warnings=3), "2 errors, 3 warnings", "2 Fehler, 3 Warnungen"),
    (Status("warnings", warnings=1), "1 warning", "1 Warnung"),
    (Status("warnings", warnings=4), "4 warnings", "4 Warnungen"),
])
def test_the_words_of_the_chip(current, english, german):
    assert status_text(current, ENGLISH) == english and status_text(current, DE) == german


def test_a_run_that_goes_on_shows_its_time_in_both_languages():
    assert status_text(Status("running"), ENGLISH, "1:12") == "Running 1:12"
    assert status_text(Status("running"), DE, "1:12") == "Läuft 1:12"
    assert status_text(Status("running"), ENGLISH) == "Running 0:00"


@pytest.mark.parametrize("current, english, german", [
    (Status("errors", errors=1), "Fix the errors first", "Zuerst die Fehler beheben"),
    (Status("empty"), "Choose components first", "Zuerst Komponenten wählen"),
    (Status("running"), "A run is going on", "Ein Lauf ist im Gange"),
])
def test_why_the_button_is_blocked(current, english, german):
    assert run_hint(current, ENGLISH) == english and run_hint(current, DE) == german


@pytest.mark.parametrize("kind", ["ready", "warnings", "outdated"])
def test_a_button_that_can_be_pressed_has_no_excuse(kind):
    assert run_hint(Status(kind), ENGLISH) == ""


# ---------------------------------------------------------------------------
# the badge on the tab of the check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("current, expected", [
    (Status("ready"), (0, "grey")),
    (Status("warnings", warnings=2), (2, "warning")),
    (Status("errors", errors=1), (1, "negative")),
    (Status("errors", errors=1, warnings=2), (3, "negative")),          # errors colour the whole count
    (Status("empty"), (0, "grey")),
])
def test_the_badge_counts_everything_the_check_found_and_is_red_for_errors(current, expected):
    assert badge_of(current) == expected


# ---------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------

def test_every_state_has_a_colour_and_an_icon():
    assert set(COLORS) == set(ICONS) == set(KINDS)


def test_every_text_of_a_state_is_in_both_catalogs():
    english = json.loads((CATALOGS / "en.json").read_text(encoding="utf-8"))
    german = json.loads((CATALOGS / "de.json").read_text(encoding="utf-8"))

    for key in TEXTS.values():
        assert key in english and key in german and english[key] != german[key], key