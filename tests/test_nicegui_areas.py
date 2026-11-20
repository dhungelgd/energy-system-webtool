"""The start page and the bar of the areas on the NiceGUI page (simulated user)."""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("nicegui")
from nicegui.testing import User  # noqa: E402

from tests.report_samples import sample_result  # noqa: E402
from tests.test_nicegui_draft_run import (  # noqa: E402
    build_draft,
    exists,
    field,
    settle,
    switched_to,
    use_solver,
)

TOOL = ("views", "draft-name", "draft-run", "status", "header-save", "header-series")        # what belongs to the optimization


def page_module():
    """The module of the page. It is not imported at the top of this file: the simulated user sets the pages up itself,
    and a module that was imported before would not set them up again."""

    import sys

    return sys.modules["frontend_nicegui.app"]


def label_of(user, marker):
    return field(user, marker).props["label"]


async def to(user: User, area):
    field(user, "area-bar").set_value(area)
    await settle()


@pytest.fixture
def server_without_setting(monkeypatch):
    monkeypatch.delenv("WEBTOOL_START_AREA", raising=False)


# ---------------------------------------------------------------------------
# where the page opens
# ---------------------------------------------------------------------------

async def test_the_page_opens_on_the_start_page_when_nothing_says_otherwise(user: User, server_without_setting):
    await user.open("/")

    assert field(user, "area-bar").value == "start" and exists(user, "start-title")
    assert not any(exists(user, marker) for marker in TOOL)
    assert exists(user, "language") and exists(user, "app-title")


async def test_the_older_page_tests_begin_in_the_optimization_by_the_setting_of_the_server(user: User):
    await user.open("/")

    assert field(user, "area-bar").value == "optimization" and not exists(user, "start-title")
    assert all(exists(user, marker) for marker in TOOL)


async def test_the_address_names_the_area_and_beats_the_setting(user: User):
    await user.open("/?area=start")

    assert field(user, "area-bar").value == "start" and exists(user, "start-title") and not exists(user, "views")


async def test_the_address_can_name_the_optimization_too(user: User, server_without_setting):
    await user.open("/?area=optimization")

    assert field(user, "area-bar").value == "optimization" and all(exists(user, marker) for marker in TOOL)


async def test_a_name_in_the_address_that_is_not_an_area_is_ignored(user: User, server_without_setting, monkeypatch):
    await user.open("/?area=nonsense")

    assert field(user, "area-bar").value == "start" and exists(user, "start-title")


async def test_an_address_that_is_not_an_area_leaves_the_setting_of_the_server(user: User):
    await user.open("/?area=nonsense")

    assert field(user, "area-bar").value == "optimization" and exists(user, "views")


# ---------------------------------------------------------------------------
# the bar of the areas
# ---------------------------------------------------------------------------

async def test_the_bar_has_the_start_and_the_optimization_in_the_language_of_the_page(user: User):
    await user.open("/?area=start")
    assert (label_of(user, "area-start"), label_of(user, "area-optimization")) == ("Start", "Optimization")

    await user.open("/?area=start&lang=de")
    assert (label_of(user, "area-start"), label_of(user, "area-optimization")) == ("Start", "Optimierung")


async def test_a_key_of_the_bar_takes_to_its_area_and_the_buttons_of_the_top_bar_come_with_it(user: User):
    await user.open("/?area=start")
    assert not any(exists(user, marker) for marker in TOOL)

    await to(user, "optimization")

    assert not exists(user, "start-title") and all(exists(user, marker) for marker in TOOL)


async def test_the_start_key_takes_back_to_the_start_page_and_the_tool_goes(user: User):
    await user.open("/")
    assert all(exists(user, marker) for marker in TOOL)

    await to(user, "start")

    assert exists(user, "start-title") and not any(exists(user, marker) for marker in TOOL)


async def test_the_language_switch_stays_on_the_start_page_and_the_area_stays_when_the_language_changes(user: User):
    await user.open("/?area=start")

    await switched_to(user, "de")
    await settle()

    assert field(user, "area-bar").value == "start" and field(user, "start-title").text == "Womit möchten Sie beginnen?"
    assert label_of(user, "area-optimization") == "Optimierung"


# ---------------------------------------------------------------------------
# what stays when the area changes
# ---------------------------------------------------------------------------

async def test_what_was_built_is_still_there_after_a_visit_to_the_start_page(user: User):
    await user.open("/")
    user.find(marker="template-pv-battery").click()
    await settle()
    user.find(marker="draft-name").clear().type("My plant")
    await settle()

    await to(user, "start")
    await to(user, "optimization")

    assert all(exists(user, f"tile-{key}") for key in ("pv", "battery")) and field(user, "draft-name").value == "My plant"


async def test_the_card_of_the_optimization_says_to_continue_when_a_scenario_was_built(user: User):
    await user.open("/?area=start")
    assert field(user, "start-optimization").text == "Build a scenario"

    await to(user, "optimization")
    user.find(marker="component-demand").click()
    await settle()
    await to(user, "start")

    assert field(user, "start-optimization").text == "Continue with the scenario"


async def test_the_card_of_the_optimization_takes_to_it(user: User):
    await user.open("/?area=start")

    user.find(marker="start-optimization").click()
    await settle()

    assert field(user, "area-bar").value == "optimization" and exists(user, "views")


async def test_the_side_sheet_is_closed_on_the_start_page_and_no_component_is_open_when_coming_back(user: User):
    await user.open("/")
    user.find(marker="component-demand").click()
    await settle()
    user.find(marker="tile-demand").click()
    await settle()
    assert field(user, "drawer-sheet").value is True

    await to(user, "start")
    assert field(user, "drawer-sheet").value is False

    await to(user, "optimization")
    assert field(user, "drawer-sheet").value is False


async def test_a_run_goes_on_while_the_visitor_is_on_the_start_page_and_the_result_is_there_afterwards(user: User, monkeypatch):
    gate = asyncio.Event()

    async def solver(scenario):
        await gate.wait()
        return sample_result(24)

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await settle()

    await to(user, "start")
    assert not exists(user, "status")
    gate.set()
    await settle()
    await to(user, "optimization")
    await settle()

    assert exists(user, "draft-tab-costs") and field(user, "draft-run").enabled


# ---------------------------------------------------------------------------
# the example
# ---------------------------------------------------------------------------

async def test_the_example_is_taken_into_the_scenario_and_the_optimization_is_shown(user: User):
    await user.open("/?area=start")

    user.find(marker="start-example").click()
    await settle()

    assert field(user, "area-bar").value == "optimization"
    assert all(exists(user, f"tile-{key}") for key in ("demand", "grid", "pv")) and field(user, "draft-name").value == "PV and grid, one day"
    assert user.notify.contains("is in the system view now") and not exists(user, "scenario-name")


async def test_the_example_asks_before_it_replaces_what_was_built_and_a_no_leaves_everything_as_it_was(user: User):
    await user.open("/")
    user.find(marker="template-pv-battery").click()
    await settle()
    await to(user, "start")

    user.find(marker="start-example").click()
    await settle()
    assert exists(user, "open-edit-dialog")

    user.find(marker="open-edit-cancel").click()
    await settle()

    assert field(user, "area-bar").value == "start" and not exists(user, "open-edit-dialog")       # nothing happened
    await to(user, "optimization")
    assert exists(user, "tile-battery") and not exists(user, "scenario-name")


async def test_the_example_replaces_what_was_built_after_a_yes(user: User):
    await user.open("/")
    user.find(marker="template-pv-battery").click()
    await settle()
    await to(user, "start")

    user.find(marker="start-example").click()
    await settle()
    user.find(marker="open-edit-confirm").click()
    await settle()

    assert not exists(user, "tile-battery") and all(exists(user, f"tile-{key}") for key in ("demand", "grid", "pv"))


async def test_an_example_that_cannot_be_read_is_told_and_the_page_stays_where_it_is(user: User, monkeypatch, caplog):
    await user.open("/?area=start")
    monkeypatch.setattr(page_module(), "EXAMPLE", Path("/nowhere/at/all/example.json"))

    user.find(marker="start-example").click()
    await settle()

    assert user.notify.contains("The example could not be opened.") and field(user, "area-bar").value == "start"
    assert "could not be read" in caplog.text
    caplog.clear()


async def test_an_example_that_is_not_a_scenario_is_told_too(user: User, monkeypatch, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    await user.open("/?area=start")
    monkeypatch.setattr(page_module(), "EXAMPLE", broken)

    user.find(marker="start-example").click()
    await settle()

    assert user.notify.contains("The example could not be opened.") and field(user, "area-bar").value == "start"


# ---------------------------------------------------------------------------
# the start page itself
# ---------------------------------------------------------------------------

async def test_the_start_page_has_a_card_for_each_area_and_one_for_the_example(user: User):
    await user.open("/?area=start")

    assert field(user, "start-title").text == "Where would you like to start?"
    assert exists(user, "start-intro") and exists(user, "start-card-optimization") and exists(user, "start-card-example")
    assert field(user, "start-example").text == "Open example"


async def test_the_start_page_is_in_german(user: User):
    await user.open("/?area=start&lang=de")

    assert field(user, "start-title").text == "Womit möchten Sie beginnen?"
    assert field(user, "start-optimization").text == "Szenario aufbauen" and field(user, "start-example").text == "Beispiel öffnen"
    await user.should_see("Ihr Projekt hält alle Daten an einem Ort.")
    await user.should_see("PV, Speicher und Wärme kombinieren und das kostengünstigste System finden.")