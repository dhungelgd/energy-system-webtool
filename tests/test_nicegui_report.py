"""The button for the PDF report on the NiceGUI page (simulated user)."""

import asyncio
import io
import sys
import threading

import pytest

pytest.importorskip("nicegui")
pytest.importorskip("reportlab")
pypdf = pytest.importorskip("pypdf")
from nicegui import ui  # noqa: E402
from nicegui.testing import User  # noqa: E402

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


def record_downloads(monkeypatch):
    """Take over what the page gives to the visitor as a file: a list of (bytes, file name, media type)."""

    calls = []
    monkeypatch.setattr(ui.download, "content", lambda content, filename=None, media_type="": calls.append((content, filename, media_type)))

    return calls


async def waiting_for(calls, count=1, seconds=15.0):
    """Wait until the report is there (it is made in a thread)."""

    for _ in range(int(seconds * 20)):
        if len(calls) >= count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"no download after {seconds} s")


def text_of(content):
    return " ".join(" ".join(page.extract_text().split()) for page in pypdf.PdfReader(io.BytesIO(content)).pages)


async def ran(user: User, monkeypatch, language=None, name=None, hours=24):
    """Run the draft with a result by hand, and wait until the result is shown."""

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

async def test_a_result_of_the_draft_has_a_button_for_the_report_and_before_a_run_there_is_none(user: User, monkeypatch):
    await user.open("/")
    assert not exists(user, "draft-report")

    await ran(user, monkeypatch)

    assert field(user, "draft-report").text == "Download report (PDF)"
    with user.client:
        assert len(user.find(marker="draft-report").elements) == 1


async def test_the_button_is_in_german(user: User, monkeypatch):
    await ran(user, monkeypatch, language="de")

    assert field(user, "draft-report").text == "Bericht als PDF herunterladen"


async def test_the_button_is_before_the_tabs_of_the_result_and_after_the_solver(user: User, monkeypatch):
    await ran(user, monkeypatch)

    order = list(user.client.content.descendants())

    assert order.index(field(user, "solver")) < order.index(field(user, "draft-report")) < order.index(field(user, "draft-tab-costs"))


# ---------------------------------------------------------------------------
# the download
# ---------------------------------------------------------------------------

async def test_a_click_gives_the_report_as_a_pdf_that_is_named_after_the_scenario(user: User, monkeypatch):
    await ran(user, monkeypatch, name="My PV system")
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-report").click()
    await waiting_for(calls)

    content, file_name, media_type = calls[0]
    assert (file_name, media_type) == ("my_pv_system_report.pdf", "application/pdf") and content.startswith(b"%PDF-")
    text = text_of(content)
    assert "My PV system" in text and "RESULT REPORT" in text and "The optimised system" in text and "55,353 €" in text


async def test_the_report_is_in_german_for_a_german_page_and_the_file_name_follows(user: User, monkeypatch):
    await ran(user, monkeypatch, language="de", name="Mein Betrieb")
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-report").click()
    await waiting_for(calls)

    assert calls[0][1] == "mein_betrieb_bericht.pdf"
    text = text_of(calls[0][0])
    assert "ERGEBNISBERICHT" in text and "Das optimierte System" in text and "Seite 1" in text


async def test_a_scenario_without_a_name_is_reported_under_the_name_of_the_page(user: User, monkeypatch):
    await ran(user, monkeypatch)
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-report").click()
    await waiting_for(calls)

    assert calls[0][1] == "unnamed_scenario_report.pdf" and "Unnamed scenario" in text_of(calls[0][0])


async def test_the_report_is_of_the_scenario_that_was_run_and_not_of_what_was_changed_after(user: User, monkeypatch):
    await ran(user, monkeypatch, name="First version")
    user.find(marker="draft-name").clear().type("Second version")
    user.find(marker=PRICE).clear().type("0.41")                           # a real change: the result is out of date now
    await settle()
    await user.should_see(marker="draft-outdated")
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-report").click()
    await waiting_for(calls)

    assert calls[0][1] == "first_version_report.pdf" and "First version" in text_of(calls[0][0])
    assert "Second version" not in text_of(calls[0][0])


async def test_every_click_gives_a_report(user: User, monkeypatch):
    await ran(user, monkeypatch)
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-report").click()
    await waiting_for(calls, 1)
    user.find(marker="draft-report").click()
    await waiting_for(calls, 2)

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# while it works, and when it fails
# ---------------------------------------------------------------------------

async def test_while_the_report_is_made_the_button_waits_and_is_free_again_afterwards(user: User, monkeypatch):
    from frontend_nicegui import report_pdf

    release, started = threading.Event(), threading.Event()
    real = report_pdf.build_pdf

    def slow(scenario, result, tr):
        started.set()
        release.wait(10)
        return real(scenario, result, tr)

    await ran(user, monkeypatch)
    monkeypatch.setattr(report_pdf, "build_pdf", slow)
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-report").click()
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.05)
    assert started.is_set() and not field(user, "draft-report").enabled and "loading" in field(user, "draft-report").props
    assert calls == []

    release.set()
    await waiting_for(calls)
    await settle()

    assert field(user, "draft-report").enabled and "loading" not in field(user, "draft-report").props


async def test_when_the_report_cannot_be_made_the_visitor_is_told_and_the_page_goes_on(user: User, monkeypatch, caplog):
    from frontend_nicegui import report_pdf

    def broken(scenario, result, tr):
        raise RuntimeError("the drawing went wrong")

    await ran(user, monkeypatch)
    monkeypatch.setattr(report_pdf, "build_pdf", broken)
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-report").click()
    for _ in range(100):
        if user.notify.contains("The report could not be created."):
            break
        await asyncio.sleep(0.05)

    assert user.notify.contains("The report could not be created.") and calls == []
    assert not user.notify.contains("the drawing went wrong")             # the details are not for the visitor ...
    assert "the drawing went wrong" in caplog.text                        # ... but for the developers
    caplog.clear()                                                        # the log entry is expected here
    assert field(user, "draft-report").enabled and exists(user, "draft-tab-costs")


async def test_the_failure_is_told_in_german(user: User, monkeypatch, caplog):
    from frontend_nicegui import report_pdf

    await ran(user, monkeypatch, language="de")
    monkeypatch.setattr(report_pdf, "build_pdf", lambda *args: (_ for _ in ()).throw(RuntimeError("x")))

    user.find(marker="draft-report").click()
    for _ in range(100):
        if user.notify.contains("Der Bericht konnte nicht erstellt werden."):
            break
        await asyncio.sleep(0.05)

    assert user.notify.contains("Der Bericht konnte nicht erstellt werden.")
    caplog.clear()


async def test_a_page_without_the_pdf_library_still_works_and_says_that_the_report_failed(user: User, monkeypatch, caplog):
    await ran(user, monkeypatch)
    monkeypatch.delitem(sys.modules, "frontend_nicegui.report_pdf", raising=False)
    for name in [name for name in sys.modules if name == "reportlab" or name.startswith("reportlab.")]:
        monkeypatch.setitem(sys.modules, name, None)                         # an import of it fails now
    calls = record_downloads(monkeypatch)

    user.find(marker="draft-report").click()
    for _ in range(100):
        if user.notify.contains("The report could not be created."):
            break
        await asyncio.sleep(0.05)

    assert user.notify.contains("The report could not be created.") and calls == [] and exists(user, "draft-tab-costs")
    assert "reportlab" in caplog.text
    caplog.clear()


# ---------------------------------------------------------------------------
# the result of an opened file
# ---------------------------------------------------------------------------

async def test_the_result_of_an_opened_file_has_the_button_too_and_reports_that_file(user: User, monkeypatch):
    async def solver(scenario):
        return sample_result(24)

    use_solver(monkeypatch, solver)
    await user.open("/")
    await open_example(user, "pv_and_grid")
    assert not exists(user, "file-report")                                  # nothing was run yet

    user.find(marker="run").click()
    await user.should_see(marker="file-report")
    calls = record_downloads(monkeypatch)
    user.find(marker="file-report").click()
    await waiting_for(calls)

    assert calls[0][1] == "pv_and_grid_one_day_report.pdf" and "PV and grid, one day" in text_of(calls[0][0])
    assert not exists(user, "draft-report")