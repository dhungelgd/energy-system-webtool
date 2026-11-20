"""The button for the Excel file of a result on the NiceGUI page (simulated user)."""

import asyncio
import io
import threading

import pytest

pytest.importorskip("nicegui")
from nicegui import ui  # noqa: E402
from nicegui.testing import User  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from frontend_nicegui import result_excel  # noqa: E402
from tests.report_samples import sample_result  # noqa: E402
from tests.test_nicegui_draft_run import (  # noqa: E402
    PRICE,
    build_draft,
    exists,
    field,
    open_example,
    settle,
    use_solver,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def record_downloads(monkeypatch):
    """Take over what the page gives to the visitor as a file: a list of (bytes, file name, media type)."""

    calls = []
    monkeypatch.setattr(ui.download, "content", lambda content, filename=None, media_type="": calls.append((content, filename, media_type)))

    return calls


async def waiting_for(calls, count=1, seconds=15.0):
    for _ in range(int(seconds * 20)):
        if len(calls) >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"no download after {seconds} s")


def book_of(content):
    return load_workbook(io.BytesIO(content))


async def ran(user: User, monkeypatch, language=None, name=None, hours=24):
    async def solver(scenario):
        return sample_result(hours)

    use_solver(monkeypatch, solver)
    await build_draft(user, language=language)
    if name is not None:
        user.find(marker="draft-name").clear().type(name)
        await settle()
    user.find(marker="draft-run").click()
    await user.should_see(marker="draft-tab-costs")


# ---------------------------------------------------------------------------
# the button
# ---------------------------------------------------------------------------

async def test_a_result_has_a_button_for_the_excel_file_and_before_a_run_there_is_none(user: User, monkeypatch):
    await user.open("/")
    assert not exists(user, "draft-excel")

    await ran(user, monkeypatch)

    assert field(user, "draft-excel").text == "Download Excel"
    with user.client:
        assert len(user.find(marker="draft-excel").elements) == 1


async def test_the_button_is_in_german(user: User, monkeypatch):
    await ran(user, monkeypatch, language="de")

    assert field(user, "draft-excel").text == "Excel herunterladen"


async def test_the_text_of_the_button_is_never_the_key_of_a_text_and_the_failure_text_neither(user: User, monkeypatch):
    await ran(user, monkeypatch)

    assert "." not in field(user, "draft-excel").text and "." not in field(user, "draft-report").text


async def test_the_two_buttons_are_side_by_side_the_report_first_and_both_before_the_tabs(user: User, monkeypatch):
    await ran(user, monkeypatch)

    order = list(user.client.content.descendants())

    assert order.index(field(user, "solver")) < order.index(field(user, "draft-report")) < order.index(field(user, "draft-excel")) < order.index(
        field(user, "draft-tab-costs"))


# ---------------------------------------------------------------------------
# the download
# ---------------------------------------------------------------------------

async def test_a_click_gives_an_excel_file_that_is_named_after_the_scenario(user: User, monkeypatch):
    await ran(user, monkeypatch, name="My PV system")
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-excel").click()
    await waiting_for(calls)

    content, file_name, media_type = calls[0]
    assert (file_name, media_type) == ("my_pv_system_results.xlsx", XLSX) and content[:2] == b"PK"
    book = book_of(content)
    assert book.sheetnames[:4] == ["Summary", "Costs", "Capacities", "Electricity"] and book["Summary"][
        "A1"].value == "My PV system"
    assert book["Costs"]["C2"].value == 19080.3 and book["Electricity"].max_row == 25


async def test_the_file_is_in_german_for_a_german_page_and_the_file_name_follows(user: User, monkeypatch):
    await ran(user, monkeypatch, language="de", name="Mein Betrieb")
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-excel").click()
    await waiting_for(calls)

    assert calls[0][1] == "mein_betrieb_ergebnisse.xlsx"
    book = book_of(calls[0][0])
    assert book.sheetnames[:4] == ["Übersicht", "Kosten", "Größen", "Strom"] and book["Strom"]["A1"].value == "Zeit"


async def test_a_scenario_without_a_name_is_named_as_the_page_shows_it(user: User, monkeypatch):
    await ran(user, monkeypatch)
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-excel").click()
    await waiting_for(calls)

    assert calls[0][1] == "unnamed_scenario_results.xlsx" and book_of(calls[0][0])["Summary"]["A1"].value == "Unnamed scenario"


async def test_the_file_is_of_the_scenario_that_was_run_and_not_of_what_was_changed_after(user: User, monkeypatch):
    await ran(user, monkeypatch, name="First version")
    user.find(marker="draft-name").clear().type("Second version")
    user.find(marker=PRICE).clear().type("0.41")
    await settle()
    await user.should_see(marker="draft-outdated")
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-excel").click()
    await waiting_for(calls)

    assert calls[0][1] == "first_version_results.xlsx" and book_of(calls[0][0])["Summary"]["A1"].value == "First version"


async def test_every_click_gives_a_file_and_the_report_button_is_not_touched(user: User, monkeypatch):
    await ran(user, monkeypatch)
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-excel").click()
    await waiting_for(calls, 1)
    user.find(marker="draft-excel").click()
    await waiting_for(calls, 2)

    assert len(calls) == 2 and all(call[1].endswith(".xlsx") for call in calls) and field(user, "draft-report").enabled


# ---------------------------------------------------------------------------
# while it works, and when it fails
# ---------------------------------------------------------------------------

async def test_while_the_file_is_made_the_button_waits_and_is_free_again_afterwards(user: User, monkeypatch):
    release, started = threading.Event(), threading.Event()
    real = result_excel.build_workbook

    def slow(scenario, result, tr):
        started.set()
        release.wait(10)
        return real(scenario, result, tr)

    await ran(user, monkeypatch)
    monkeypatch.setattr(result_excel, "build_workbook", slow)
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-excel").click()
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.05)
    assert started.is_set() and not field(user, "draft-excel").enabled and "loading" in field(user, "draft-excel").props
    assert calls == [] and field(user, "draft-report").enabled                      # the other button is free

    release.set()
    await waiting_for(calls)
    await settle()

    assert field(user, "draft-excel").enabled and "loading" not in field(user, "draft-excel").props


async def test_when_the_file_cannot_be_made_the_visitor_is_told_and_the_page_goes_on(user: User, monkeypatch, caplog):
    def broken(scenario, result, tr):
        raise RuntimeError("the workbook went wrong")

    await ran(user, monkeypatch)
    monkeypatch.setattr(result_excel, "build_workbook", broken)
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-excel").click()
    for _ in range(100):
        if user.notify.contains("The Excel file could not be created."):
            break
        await asyncio.sleep(0.05)

    assert user.notify.contains("The Excel file could not be created.") and calls == []
    assert not user.notify.contains("the workbook went wrong") and "the workbook went wrong" in caplog.text
    caplog.clear()
    assert field(user, "draft-excel").enabled and exists(user, "draft-tab-costs")


async def test_the_failure_is_told_in_german(user: User, monkeypatch, caplog):
    await ran(user, monkeypatch, language="de")
    monkeypatch.setattr(result_excel, "build_workbook", lambda *args: (_ for _ in ()).throw(RuntimeError("x")))

    user.find(marker="draft-excel").click()
    for _ in range(100):
        if user.notify.contains("Die Excel-Datei konnte nicht erstellt werden."):
            break
        await asyncio.sleep(0.05)

    assert user.notify.contains("Die Excel-Datei konnte nicht erstellt werden.")
    caplog.clear()


# ---------------------------------------------------------------------------
# the result of an opened file
# ---------------------------------------------------------------------------

async def test_the_result_of_an_opened_file_has_the_button_too_and_gives_that_file(user: User, monkeypatch):
    async def solver(scenario):
        return sample_result(24)

    use_solver(monkeypatch, solver)
    await user.open("/")
    await open_example(user, "pv_and_grid")
    assert not exists(user, "file-excel")

    user.find(marker="run").click()
    await user.should_see(marker="file-excel")
    calls = record_downloads(monkeypatch)
    user.find(marker="file-excel").click()
    await waiting_for(calls)

    assert calls[0][1] == "pv_and_grid_one_day_results.xlsx" and book_of(calls[0][0])["Summary"]["A1"].value == "PV and grid, one day"
    assert not exists(user, "draft-excel")