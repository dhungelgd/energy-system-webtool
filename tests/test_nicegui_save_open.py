"""Saving the scenario as a file and taking an opened file into the system view on the NiceGUI page (simulated user)."""

import json

import pytest

pytest.importorskip("nicegui")
from nicegui import ui  # noqa: E402
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402

from backend.scenario_v2 import ScenarioV2  # noqa: E402
from tests.test_nicegui_bulk import ALL, csv, open_with, texts, tooltip_of, upload, use_it  # noqa: E402
from tests.test_nicegui_draft_run import (  # noqa: E402
    EXAMPLES,
    PRICE,
    exists,
    fake_result,
    field,
    open_example,
    settle,
    switched_to,
    use_solver,
)
from tests.test_nicegui_frame import views  # noqa: E402

PV_AND_GRID = "PV and grid, one day"


def record_downloads(monkeypatch):
    """Take over what the page gives to the visitor as a file: a list of (bytes, file name, media type)."""

    calls = []
    monkeypatch.setattr(ui.download, "content", lambda content, filename=None, media_type="": calls.append((content, filename, media_type)))

    return calls


def saved(calls, index=-1):
    """The scenario of a downloaded file."""

    return ScenarioV2.model_validate_json(calls[index][0])


async def open_file(user: User, name="pv_and_grid"):
    """Open an example file in the card for opening a scenario (the page is opened first if that was not done yet)."""

    if user.client is None:
        await user.open("/")
    await open_example(user, name)


async def edit_it(user: User, name="pv_and_grid"):
    await open_file(user, name)
    user.find(marker="open-edit").click()
    await settle()


# ---------------------------------------------------------------------------
# saving
# ---------------------------------------------------------------------------

async def test_the_top_bar_has_a_save_button_that_waits_for_the_first_component(user: User):
    await user.open("/")

    assert field(user, "header-save").text == "Save scenario"
    assert not field(user, "header-save").enabled
    assert tooltip_of(user, "header-save") == ["Choose components first"]

    user.find(marker="component-demand").click()
    await settle()

    assert field(user, "header-save").enabled
    assert tooltip_of(user, "header-save") == ["Save the scenario with its time series as a file on your computer"]

    user.find(marker="component-demand").click()                           # the component is taken out again
    await settle()
    assert not field(user, "header-save").enabled


async def test_the_save_button_is_after_the_button_for_the_series_and_before_the_status(user: User):
    await user.open("/")

    order = list(user.client.layout.descendants())

    assert order.index(field(user, "header-series")) < order.index(field(user, "header-save")) < order.index(field(user, "status"))


async def test_a_click_gives_the_scenario_as_a_file_that_is_named_after_it(user: User, monkeypatch):
    await open_with(user, "demand", "pv")
    calls = record_downloads(monkeypatch)
    user.find(marker="draft-name").clear().type("My PV system")
    await settle()

    user.find(marker="header-save").click()

    assert len(calls) == 1
    content, file_name, media_type = calls[0]
    assert (file_name, media_type) == ("my_pv_system.json", "application/json")
    scenario = saved(calls)
    assert scenario.name == "My PV system" and sorted(c.id for c in scenario.components) == ["demand", "pv"]
    assert scenario.time.steps == 24


async def test_a_scenario_without_a_name_is_saved_under_the_name_that_the_page_shows(user: User, monkeypatch):
    await open_with(user, "demand")
    calls = record_downloads(monkeypatch)

    user.find(marker="header-save").click()

    assert calls[0][1] == "unnamed_scenario.json" and saved(calls).name == "Unnamed scenario"


async def test_the_save_button_is_in_german_and_the_name_of_the_file_follows(user: User, monkeypatch):
    await open_with(user, "demand", language="de")
    calls = record_downloads(monkeypatch)

    assert field(user, "header-save").text == "Szenario speichern"
    assert tooltip_of(user, "header-save") == ["Das Szenario mit seinen Zeitreihen als Datei auf Ihrem Computer speichern"]
    user.find(marker="header-save").click()

    assert calls[0][1] == "unbenanntes_szenario.json" and saved(calls).name == "Unbenanntes Szenario"


async def test_the_button_follows_the_language_when_it_changes(user: User):
    await user.open("/")

    await switched_to(user, "de")

    assert field(user, "header-save").text == "Szenario speichern" and tooltip_of(user, "header-save") == ["Wählen Sie zuerst Bauteile"]


async def test_the_saved_file_has_what_was_typed_and_the_time_series(user: User, monkeypatch):
    await open_with(user, "demand", "heat_demand", "pv", "grid")
    calls = record_downloads(monkeypatch)
    await upload(user, csv(ALL))
    await use_it(user)

    user.find(marker="header-save").click()

    scenario = saved(calls)
    assert sorted(scenario.series) == ["electricity_demand", "grid_price", "heat_demand", "pv_profile"]
    assert scenario.series["pv_profile"].values[:8] == [0.0] * 7 + [0.1]
    assert scenario.series["pv_profile"].source.file == "alle.csv" and scenario.series["pv_profile"].source.column == "PV"


async def test_every_click_gives_the_scenario_as_it_is_then(user: User, monkeypatch):
    await open_with(user, "demand")
    calls = record_downloads(monkeypatch)
    user.find(marker="header-save").click()

    user.find(marker="component-pv").click()
    await settle()
    user.find(marker="header-save").click()

    assert [sorted(c.id for c in saved(calls, i).components) for i in (0, 1)] == [["demand"], ["demand", "pv"]]


# ---------------------------------------------------------------------------
# opening a file into the system view
# ---------------------------------------------------------------------------

async def test_a_file_that_the_draft_can_hold_has_a_button_to_edit_it(user: User):
    await open_file(user, "pv_and_grid")

    assert field(user, "open-edit").text == "Edit this scenario"
    await user.should_see("Takes the scenario into the system view, where you can change it and run it.")
    assert not exists(user, "open-edit-problem")


async def test_the_scenario_is_taken_in_without_asking_when_nothing_was_built(user: User):
    await open_file(user, "pv_and_grid")
    assert not exists(user, "tile-pv")

    user.find(marker="open-edit").click()
    await settle()

    assert all(exists(user, f"tile-{key}") for key in ("demand", "grid", "pv"))
    assert not exists(user, "open-edit-dialog")
    assert field(user, "draft-name").value == PV_AND_GRID
    assert field(user, "draft-start").value == "2021-01-01" and field(user, "draft-steps").value == 24
    assert views(user).value == "system"
    assert not exists(user, "scenario-name") and not exists(user, "open-edit")      # the file card has done its job


async def test_the_page_says_that_the_scenario_is_in_the_system_view(user: User):
    await edit_it(user)

    assert user.notify.contains(f"The scenario {PV_AND_GRID} is in the system view now.")


async def test_the_time_series_of_the_file_are_in_the_forms(user: User):
    await edit_it(user)

    assert exists(user, "series-summary-demand") and exists(user, "series-summary-pv")
    assert texts(user, "series-summary-demand")[0].startswith("24 values")
    assert not exists(user, "series-summary-grid")                         # the grid has a constant price in this file


async def test_the_period_and_the_name_come_from_the_file_also_when_they_were_changed_before(user: User):
    await user.open("/")
    user.find(marker="draft-steps").clear().type("168")
    user.find(marker="draft-name").clear().type("Something else")
    await settle()
    await open_file(user, "pv_and_grid")

    user.find(marker="open-edit").click()
    await settle()
    user.find(marker="open-edit-confirm").click() if exists(user, "open-edit-confirm") else None
    await settle()

    assert field(user, "draft-steps").value == 24 and field(user, "draft-name").value == PV_AND_GRID


async def test_with_something_built_the_visitor_is_asked_before_it_is_replaced(user: User):
    await user.open("/")
    user.find(marker="template-pv-battery").click()                        # a PV system with a battery
    await settle()
    await open_file(user, "pv_and_grid")

    user.find(marker="open-edit").click()
    await settle()

    assert exists(user, "open-edit-dialog")
    await user.should_see("Replace the scenario you are building?")
    await user.should_see("The scenario in the system view (5 components) is replaced by the one from the file.")
    assert exists(user, "tile-battery")                                    # nothing has happened yet


async def test_one_component_is_said_in_the_singular_in_the_question(user: User):
    await user.open("/")
    user.find(marker="component-demand").click()
    await settle()
    await open_file(user, "pv_and_grid")

    user.find(marker="open-edit").click()
    await settle()

    await user.should_see("The scenario in the system view (1 component) is replaced by the one from the file.")


async def test_cancelling_the_question_keeps_what_was_built_and_the_opened_file(user: User):
    await user.open("/")
    user.find(marker="template-pv-battery").click()
    await settle()
    await open_file(user, "pv_and_grid")
    user.find(marker="open-edit").click()
    await settle()

    user.find(marker="open-edit-cancel").click()
    await settle()

    assert exists(user, "tile-battery") and exists(user, "scenario-name") and exists(user, "open-edit")
    assert not exists(user, "open-edit-dialog") and not user.notify.contains("is in the system view now")


async def test_confirming_the_question_replaces_what_was_built(user: User):
    await user.open("/")
    user.find(marker="template-pv-battery").click()
    await settle()
    await open_file(user, "pv_and_grid")
    user.find(marker="open-edit").click()
    await settle()

    user.find(marker="open-edit-confirm").click()
    await settle()

    assert not exists(user, "tile-battery") and all(exists(user, f"tile-{key}") for key in ("demand", "grid", "pv"))
    assert not exists(user, "open-edit-dialog") and not exists(user, "scenario-name")
    assert user.notify.contains("is in the system view now")


async def test_the_old_check_and_the_old_result_do_not_follow_the_scenario_that_was_taken_in(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result(cost=72.0)

    use_solver(monkeypatch, solver)
    await user.open("/")
    user.find(marker="template-pv-system").click()
    await settle()
    await open_file(user, "with_problems")
    user.find(marker="open-edit").click()
    await settle()
    if exists(user, "open-edit-confirm"):
        user.find(marker="open-edit-confirm").click()
        await settle()

    assert exists(user, "draft-results-empty") and not exists(user, "draft-results")


async def test_a_scenario_with_problems_is_taken_in_and_the_check_says_what_is_wrong(user: User):
    await edit_it(user, "with_problems")

    assert "error" in field(user, "status").text
    assert exists(user, "problems-pv") or exists(user, "problems-demand") or exists(user, "problems-grid")


async def test_the_scenario_that_was_taken_in_can_be_run_and_is_the_one_from_the_file(user: User, monkeypatch):
    seen = []

    async def solver(scenario):
        seen.append(scenario)
        return fake_result(cost=72.0)

    use_solver(monkeypatch, solver)
    await edit_it(user)

    user.find(marker="draft-run").click()
    await user.should_see(marker="draft-results")

    assert len(seen) == 1 and sorted(c.id for c in seen[0].components) == ["demand", "grid", "pv"]
    assert sorted(seen[0].series) == ["electricity_demand", "pv_profile"] and seen[0].time.steps == 24


async def test_what_is_changed_after_the_file_was_taken_in_is_part_of_the_next_file(user: User, monkeypatch):
    await edit_it(user)
    calls = record_downloads(monkeypatch)
    user.find(marker=PRICE).clear().type("0.41")
    await settle()

    user.find(marker="header-save").click()

    grid = next(c for c in saved(calls).components if c.id == "grid")
    assert grid.blocks["costs"]["variable_costs"] == 0.41


async def test_the_save_button_is_on_after_the_scenario_was_taken_in(user: User):
    await open_file(user, "pv_and_grid")
    user.find(marker="open-edit").click()
    await settle()

    assert field(user, "header-save").enabled


# ---------------------------------------------------------------------------
# the whole way: save, clear, open, edit
# ---------------------------------------------------------------------------

async def test_a_saved_file_opened_again_gives_the_same_scenario_back(user: User, monkeypatch):
    await open_with(user, "demand", "heat_demand", "pv", "grid", steps=24)
    calls = record_downloads(monkeypatch)
    await upload(user, csv(ALL))
    await use_it(user)
    user.find(marker="draft-name").clear().type("Round trip")
    await settle()
    user.find(marker="header-save").click()
    first = calls[0][0]

    user.find(marker="clear-selection").click()
    await settle()
    assert not exists(user, "tile-pv")
    await field(user, "upload").handle_uploads([SmallFileUpload("round_trip.json", "application/json", first)])
    await user.should_see(marker="scenario-name")
    user.find(marker="open-edit").click()
    await settle()
    user.find(marker="header-save").click()

    assert saved(calls, 1).model_dump() == saved(calls, 0).model_dump()
    assert all(exists(user, f"tile-{key}") for key in ("demand", "heat_demand", "pv", "grid"))
    assert field(user, "draft-name").value == "Round trip"


# ---------------------------------------------------------------------------
# a file that the system view cannot hold
# ---------------------------------------------------------------------------

async def test_a_file_with_two_pv_systems_says_why_it_cannot_be_edited(user: User):
    await open_file(user, "two_pv_systems")

    assert not exists(user, "open-edit")
    assert field(user, "open-edit-problem").text == (
        "This scenario cannot be edited here: it has more than one component of the kind PV system, "
        "and the system view holds one of each kind.")
    assert not exists(user, "run")                                         # it has an error: it cannot be run either


async def test_a_file_with_a_carrier_of_its_own_says_which(user: User):
    await open_file(user, "hydrogen_chain")

    assert not exists(user, "open-edit")
    assert "it uses energy carriers that the system view does not know yet: hydrogen." in field(user, "open-edit-problem").text
    assert "can still be run" not in field(user, "open-edit-problem").text          # it has errors: that would not be true


async def test_a_file_without_errors_that_cannot_be_edited_can_still_be_run_and_says_so(user: User):
    data = json.loads((EXAMPLES / "pv_and_grid.json").read_text(encoding="utf-8"))
    data["time"]["start"] = "2021-01-01T06:00:00"                          # valid, but not at midnight
    await user.open("/")
    await field(user, "upload").handle_uploads([SmallFileUpload("six.json", "application/json", json.dumps(data).encode())])
    await user.should_see(marker="scenario-name")

    assert not exists(user, "open-edit")
    assert field(user, "open-edit-problem").text == (
        "This scenario cannot be edited here: it does not start at midnight, and the system view only knows whole days. "
        "It can still be run as it is.")
    assert exists(user, "run")


async def test_the_sentence_that_it_can_still_be_run_is_in_german(user: User):
    data = json.loads((EXAMPLES / "pv_and_grid.json").read_text(encoding="utf-8"))
    data["time"]["start"] = "2021-01-01T06:00:00"
    await user.open("/?lang=de")
    await field(user, "upload").handle_uploads([SmallFileUpload("six.json", "application/json", json.dumps(data).encode())])
    await user.should_see(marker="scenario-name")

    assert field(user, "open-edit-problem").text.endswith("Es kann aber unverändert gerechnet werden.")


async def test_a_file_that_cannot_be_edited_does_not_touch_what_was_built(user: User):
    await user.open("/")
    user.find(marker="template-pv-battery").click()
    await settle()

    await open_file(user, "two_pv_systems")

    assert exists(user, "tile-battery") and not exists(user, "open-edit-dialog")


async def test_a_file_that_cannot_be_opened_has_no_edit_button(user: User):
    await user.open("/")
    await field(user, "upload").handle_uploads([SmallFileUpload("kaputt.json", "application/json", b"{not json")])
    await user.should_see(marker="file-error")

    assert not exists(user, "open-edit") and not exists(user, "open-edit-problem")


async def test_the_reasons_are_in_german(user: User):
    await user.open("/?lang=de")

    await open_file(user, "two_pv_systems")

    assert field(user, "open-edit-problem").text == (
        "Dieses Szenario lässt sich hier nicht bearbeiten: es hat mehr als ein Bauteil der Art PV-Anlage, "
        "und die Ansicht System hält je Art eines.")


# ---------------------------------------------------------------------------
# language
# ---------------------------------------------------------------------------

async def test_the_button_the_question_and_the_message_are_in_german(user: User):
    await user.open("/?lang=de")
    user.find(marker="template-pv-battery").click()
    await settle()
    await open_file(user, "pv_and_grid")
    assert field(user, "open-edit").text == "Dieses Szenario bearbeiten"

    user.find(marker="open-edit").click()
    await settle()
    await user.should_see("Das Szenario ersetzen, das Sie gerade aufbauen?")
    await user.should_see("Das Szenario in der Ansicht System (5 Bauteile) wird durch das aus der Datei ersetzt.")
    assert field(user, "open-edit-confirm").text == "Ersetzen" and field(user, "open-edit-cancel").text == "Abbrechen"
    user.find(marker="open-edit-confirm").click()
    await settle()

    assert user.notify.contains(f"Das Szenario {PV_AND_GRID} ist jetzt in der Ansicht System.")