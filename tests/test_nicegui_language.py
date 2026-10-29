"""The language of the NiceGUI page: what the visitor gets and how it is changed (simulated user)."""

import asyncio
import json
from pathlib import Path

import pytest

pytest.importorskip("nicegui")
from nicegui import ui  # noqa: E402
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402

from backend.component_specs import INFO  # noqa: E402
from backend.i18n import catalog  # noqa: E402
from backend.results import KeyFigure, ScenarioResult, SolverInfo, Table  # noqa: E402
from backend.system_templates import SYSTEM_TEMPLATES  # noqa: E402
from frontend_nicegui.calendar import LOCALES  # noqa: E402
from frontend_nicegui.markers import slug  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"
DE = catalog("de")


def field(user: User, marker: str):
    return user.find(marker=marker).elements.pop()


async def open_page(user: User, language=None):
    await user.open("/" if language is None else f"/?lang={language}")


async def switch_to(user: User, language: str):
    field(user, "language").value = language
    await user.should_see(marker="app-title", content=catalog(language)["app.title"])


async def choose_template(user: User, name: str):
    user.find(marker=f"template-{slug(name)}").click()
    await user.should_see(marker="selection-count")


async def open_example(user: User, name: str):
    content = (EXAMPLES / f"{name}.json").read_bytes()
    upload = field(user, "upload")
    await upload.handle_uploads([SmallFileUpload(f"{name}.json", "application/json", content)])
    await user.should_see(marker="scenario-name")


def fake_result():
    return ScenarioResult(
        objective=72.0, horizon_hours=24,
        solver=SolverInfo(status="ok", termination="optimal", seconds=1.5),
        key_figures=[KeyFigure(label="System cost", value=1234.0, unit="€")],
        cost_breakdown=Table(columns=[]), capacities=Table(columns=[]),
    )


def use_solver(monkeypatch, solver):
    import sys

    monkeypatch.setattr(sys.modules["frontend_nicegui.app"], "solve", solver)


# ---------------------------------------------------------------------------
# which language the visitor gets
# ---------------------------------------------------------------------------

async def test_the_page_is_english_without_a_wish(user: User):
    await open_page(user)

    await user.should_see("Energy System Web Tool")
    await user.should_see("Your scenario")
    assert field(user, "language").value == "en"


async def test_the_link_asks_for_german(user: User):
    await open_page(user, "de")

    await user.should_see("Energiesystem-Webtool")
    await user.should_see("Ihr Szenario")
    await user.should_see("Szenario aufbauen")
    await user.should_see("Szenariodatei öffnen")
    assert field(user, "language").value == "de"
    await user.should_not_see("Your scenario")


async def test_a_language_that_is_not_offered_gives_english(user: User):
    await open_page(user, "fr")

    await user.should_see("Your scenario")
    assert field(user, "language").value == "en"


# ---------------------------------------------------------------------------
# the switch
# ---------------------------------------------------------------------------

async def test_the_switch_offers_both_languages_by_their_own_names(user: User):
    await open_page(user)

    assert field(user, "language").options == {"en": "English", "de": "Deutsch"}


async def test_switching_changes_every_text_of_the_page_and_back(user: User):
    await open_page(user)

    await switch_to(user, "de")
    await user.should_see("Ihr Szenario")
    await user.should_see("Startdatum")
    await user.should_see("Stundenschritte")
    await user.should_see("Auswahl leeren")
    await user.should_see("Noch nichts ausgewählt")
    await user.should_not_see("Your scenario")

    await switch_to(user, "en")
    await user.should_see("Your scenario")
    await user.should_see("Start date")
    await user.should_not_see("Ihr Szenario")


async def test_the_templates_and_components_have_german_names_but_the_same_markers(user: User):
    await open_page(user, "de")

    for name in SYSTEM_TEMPLATES:
        element = field(user, f"template-{slug(name)}")
        assert element.text == DE[f"template.{slug(name)}"]
    for key in INFO:
        assert field(user, f"component-{key}").text == DE[f"component.{key}.label"]
    for group in ("Bedarf", "Netz & Brennstoff", "Erzeugung", "Umwandlung", "Speicher"):
        await user.should_see(group)


async def test_the_unnamed_scenario_gets_the_default_name_of_the_language(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    await user.should_see(marker="draft-title", content="Unnamed scenario")

    await switch_to(user, "de")

    await user.should_see(marker="draft-title", content="Unbenanntes Szenario")
    assert field(user, "draft-name").props["placeholder"] == "Unbenanntes Szenario"


# ---------------------------------------------------------------------------
# nothing is lost
# ---------------------------------------------------------------------------

async def test_what_was_chosen_and_typed_stays_when_the_language_changes(user: User):
    await open_page(user)
    await choose_template(user, "PV + battery")
    user.find(marker="draft-name").clear().type("Bakery Meier")
    user.find(marker="draft-steps").clear().type("48")
    user.find(marker="draft-start").clear().type("2022-03-01")
    await user.should_see("Period: 48 hourly steps (2 days) from 01.03.2022 00:00")
    await user.should_see(marker="draft-title", content="Bakery Meier")

    await switch_to(user, "de")

    await user.should_see("Zeitraum: 48 Stundenschritte (2 Tage) ab 01.03.2022 00:00")
    await user.should_see(marker="draft-title", content="Bakery Meier")
    assert field(user, "draft-name").value == "Bakery Meier"
    assert field(user, "draft-steps").value == 48
    assert field(user, "draft-start").value == "2022-03-01"
    ticked = sorted(key for key in INFO if field(user, f"component-{key}").value)
    assert ticked == sorted(["demand", "grid", "grid_feedin", "pv", "battery"])


async def test_the_table_of_the_draft_is_in_german_after_the_switch(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await switch_to(user, "de")

    await user.should_see("4 Komponenten")
    rows = field(user, "draft-components").rows
    assert [row["component"] for row in rows] == ["Strombedarf", "Stromnetz", "Netzeinspeisung", "PV-Anlage"]
    assert rows[3] == {"component": "PV-Anlage", "type": "PV-Anlage", "mode": "fest", "size": "nicht festgelegt"}
    headers = [column["label"] for column in field(user, "draft-components").columns]
    assert headers == ["Komponente", "Typ", "Modus", "Größe"]


async def test_the_card_of_the_check_is_in_german_after_the_switch(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    await switch_to(user, "de")

    await user.should_see("Systemprüfung Ihres Szenarios")
    await user.should_see("Beheben Sie die Fehler oben, bevor die Optimierung starten kann.")


async def test_the_plural_follows_the_language(user: User):
    await open_page(user, "de")

    user.find(marker="component-wind").click()
    await user.should_see("1 Komponente")
    user.find(marker="component-pv").click()
    await user.should_see("2 Komponenten")


async def test_an_opened_file_stays_and_is_shown_in_german(user: User):
    await open_page(user)
    await open_example(user, "two_pv_systems")

    await switch_to(user, "de")

    await user.should_see("Datei: two_pv_systems.json")
    await user.should_see("Zeitraum: 24 Stundenschritte (1 Tag) ab 01.01.2021 00:00")
    rows = field(user, "components").rows
    assert rows[2] == {"component": "PV south roof", "type": "PV-Anlage", "mode": "fest", "size": "60 kW"}
    assert rows[3]["mode"] == "Investition" and rows[3]["size"] == "bis zu 40 kW"
    assert [column["label"] for column in field(user, "series").columns][:3] == [
        "Zeitreihe", "Einheit", "Verwendet von"]


async def test_the_error_about_a_file_is_explained_in_the_language_of_the_page(user: User):
    await open_page(user, "de")

    await field(user, "upload").handle_uploads([SmallFileUpload("x.json", "application/json", b"nope")])

    await user.should_see("Diese Datei ist kein gültiges JSON.")


async def test_the_error_about_a_file_is_worded_again_when_the_language_changes(user: User):
    await open_page(user)
    await field(user, "upload").handle_uploads([SmallFileUpload("x.json", "application/json", b"nope")])
    await user.should_see("This file is not valid JSON.")

    await switch_to(user, "de")

    await user.should_see("Diese Datei ist kein gültiges JSON.")
    await user.should_not_see("This file is not valid JSON.")


async def test_a_result_stays_when_the_language_changes_and_its_numbers_follow_the_language(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_page(user)
    await open_example(user, "pv_and_grid")
    user.find(marker="run").click()
    await user.should_see("Solver: optimal in 1.5 s")
    await user.should_see("1,234 €")

    await switch_to(user, "de")

    await user.should_see("Ergebnisse")
    await user.should_see("Solver: optimal in 1,5 s")
    await user.should_see("1.234 €")
    assert len(user.find(marker="headline").elements) == 1


async def test_a_problem_with_the_run_is_explained_in_german(user: User, monkeypatch):
    from backend.service import ScenarioError

    async def solver(scenario):
        raise ScenarioError("no solution")

    use_solver(monkeypatch, solver)
    await open_page(user, "de")
    await open_example(user, "pv_and_grid")

    user.find(marker="run").click()

    await user.should_see("Die Optimierung konnte nicht abgeschlossen werden: no solution")


async def test_an_unexpected_failure_is_explained_in_german_and_the_details_stay_hidden(
    user: User, monkeypatch, caplog
):
    async def solver(scenario):
        raise RuntimeError("secret internal detail")

    use_solver(monkeypatch, solver)
    await open_page(user, "de")
    await open_example(user, "pv_and_grid")

    user.find(marker="run").click()

    await user.should_see("Die Optimierung wurde unerwartet beendet.")
    await user.should_not_see("secret internal detail")
    caplog.clear()


# ---------------------------------------------------------------------------
# while a run is going
# ---------------------------------------------------------------------------

async def test_the_switch_is_blocked_during_a_run_and_free_afterwards(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_page(user)
    await open_example(user, "pv_and_grid")

    user.find(marker="run").click()
    await user.should_see("Running the optimization...")
    assert not field(user, "language").enabled

    field(user, "language").value = "de"                     # even if it is forced, the page stays as it is
    await asyncio.sleep(0.2)
    assert field(user, "app-title").text == "Energy System Web Tool"

    release.set()
    await user.should_see("Solver: optimal in 1.5 s")
    assert field(user, "language").enabled


async def test_the_running_text_and_the_blocked_button_are_in_german(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_page(user, "de")
    await open_example(user, "pv_and_grid")

    user.find(marker="run").click()

    await user.should_see("Die Optimierung läuft ...")
    assert not field(user, "run").enabled
    release.set()
    await user.should_see("Ergebnisse")


async def test_a_result_that_arrives_after_another_file_was_opened_is_dropped(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_page(user)
    await open_example(user, "pv_and_grid")
    user.find(marker="run").click()
    await user.should_see("Running the optimization...")

    await open_example(user, "with_problems")                 # another file, while the first is running
    release.set()
    await asyncio.sleep(0.3)

    await user.should_not_see(marker="headline")              # the result of the first file is not shown here
    await user.should_see("Fix the errors above")


async def test_after_a_dropped_result_the_next_scenario_can_be_run(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_page(user)
    await open_example(user, "pv_and_grid")
    user.find(marker="run").click()
    await user.should_see("Running the optimization...")
    await open_example(user, "pv_and_grid")                   # the same file again: a new opened scenario
    release.set()
    await asyncio.sleep(0.3)

    assert field(user, "run").enabled
    user.find(marker="run").click()
    await user.should_see("Solver: optimal in 1.5 s")


# ---------------------------------------------------------------------------
# input hints and the calendar
# ---------------------------------------------------------------------------

async def test_the_hints_of_the_input_fields_are_in_german(user: User):
    await open_page(user, "de")

    user.find(marker="draft-steps").clear().type("0")
    user.find(marker="draft-start").clear().type("tomorrow")
    await asyncio.sleep(0.2)

    assert field(user, "draft-steps").error == "Geben Sie eine ganze Zahl von 1 bis 8.784 ein."
    assert field(user, "draft-start").error == (
        "Verwenden Sie das Format JJJJ-MM-TT (zum Beispiel 2021-01-01) in den Jahren 1980 bis 2100.")


async def test_the_buttons_for_a_day_a_week_and_a_year_are_in_german(user: User):
    await open_page(user, "de")

    assert [field(user, f"steps-{n}").text for n in (24, 168, 8760)] == ["1 Tag", "1 Woche", "1 Jahr"]


async def test_the_calendar_has_german_names_in_german_only(user: User):
    await open_page(user, "de")
    calendar = user.find(kind=ui.date).elements.pop()
    assert json.loads(calendar.props[":locale"]) == LOCALES["de"]

    await switch_to(user, "en")
    calendar = user.find(kind=ui.date).elements.pop()
    assert ":locale" not in calendar.props


async def test_the_close_button_of_the_calendar_is_translated(user: User):
    await open_page(user, "de")

    buttons = [element.text for element in user.find(kind=ui.button).elements]

    assert "Schließen" in buttons and "Close" not in buttons