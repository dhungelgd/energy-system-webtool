"""The area of the load profile on the NiceGUI page (simulated user): load a file, answer what it does not say, see what
was read and what is wrong with it."""

import asyncio
import threading

import numpy as np
import pytest

pytest.importorskip("nicegui")
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402

from backend.i18n import Translator  # noqa: E402
from frontend_nicegui.profile_session import ProfileSession  # noqa: E402
from tests.test_load_profile import kw, render, starts, workshop  # noqa: E402
from tests.test_nicegui_bulk import texts  # noqa: E402
from tests.test_nicegui_draft_run import exists, field, settle, switched_to  # noqa: E402

EN = Translator("en")


def a_file(header="Zeitstempel;Leistung kW", first="2024-02-05 00:00", last="2024-02-06 23:45", columns=None):
    """The bytes of a quarter-hour file (and its values)."""

    index = starts(first, last)
    values = kw(index)
    if columns:
        lines = [f"Zeit;{columns[0]};{columns[1]}"] + [
            f"{stamp.strftime('%d.%m.%Y %H:%M')};{str(v).replace('.', ',')};{str(round(v / 3, 3)).replace('.', ',')}"
            for stamp, v in zip(index, values)]
        return ("\n".join(lines) + "\n").encode(), values

    return render(index, values, header=header).encode(), values


async def reading_done(user: User):
    for _ in range(60):
        if not exists(user, "profile-reading"):
            break
        await asyncio.sleep(0.2)
    await settle()


async def upload(user: User, content: bytes, name="Lastgang.csv"):
    await field(user, "profile-upload").handle_uploads([SmallFileUpload(name, "text/csv", content)])
    await settle()
    await reading_done(user)


async def to_profile(user: User, query="?area=profile"):
    await user.open(f"/{query}")


async def apply(user: User):
    user.find(marker="profile-ask-apply").click()
    await settle()
    await reading_done(user)


# ---------------------------------------------------------------------------
# the area and the start page
# ---------------------------------------------------------------------------

async def test_the_area_opens_with_a_title_an_intro_and_a_place_to_upload_and_nothing_else(user: User):
    await to_profile(user)

    assert field(user, "area-bar").value == "profile" and field(user, "profile-title").text == "Load profile"
    assert exists(user, "profile-intro") and exists(user, "profile-upload")
    assert not any(exists(user, marker) for marker in ("profile-settings", "profile-summary", "profile-notes", "views", "draft-name"))


async def test_the_bar_has_the_load_profile_between_the_start_and_the_optimization(user: User):
    await user.open("/?area=start")

    assert [field(user, f"area-{key}").props["label"] for key in ("start", "profile", "optimization")] == [
        "Start", "Load profile", "Optimization"]


async def test_the_start_page_recommends_the_load_profile_as_the_place_to_begin(user: User):
    await user.open("/?area=start")

    assert exists(user, "start-card-profile") and exists(user, "start-recommended-profile")
    assert not exists(user, "start-recommended-optimization")
    assert field(user, "start-profile").text == "Load a file"
    assert field(user, "start-recommended-profile").text == "Recommended start"


async def test_the_start_page_is_in_german_for_the_load_profile(user: User):
    await user.open("/?area=start&lang=de")

    assert field(user, "start-profile").text == "Lastgang laden"
    assert field(user, "start-recommended-profile").text == "Empfohlener Einstieg"
    await user.should_see("Laden Sie Ihren Lastgang hoch (CSV oder Excel).")


async def test_the_card_of_the_load_profile_takes_to_its_area(user: User):
    await user.open("/?area=start")

    user.find(marker="start-profile").click()
    await settle()

    assert field(user, "area-bar").value == "profile" and exists(user, "profile-upload")


# ---------------------------------------------------------------------------
# a file that says everything
# ---------------------------------------------------------------------------

async def test_a_file_is_read_and_shows_what_was_read_and_what_the_reader_noted(user: User):
    content, values = a_file()
    await to_profile(user)

    await upload(user, content)

    assert field(user, "profile-file").text == "File: Lastgang.csv" and not exists(user, "profile-upload")
    assert texts(user, "profile-fact-period") == ["Period", "2024-02-05 00:00 to 2024-02-07 00:00"]
    assert texts(user, "profile-fact-step") == ["Time step", "15 minutes"]
    assert texts(user, "profile-fact-values") == ["Values", "192"]
    assert texts(user, "profile-fact-missing") == ["Missing", "0 %"]
    assert texts(user, "profile-fact-energy") == ["Energy in the period", f"{EN.integer(round(values.sum() / 4))} kWh"]
    assert texts(user, "profile-fact-peak") == ["Highest power", f"{EN.number(round(values.max(), 1))} kW"]
    for code in ("file_info", "column_info", "unit_info", "stamp_start"):
        assert exists(user, f"profile-note-{code}"), code
    assert not exists(user, "profile-ask-hint") and not exists(user, "profile-error")


async def test_a_german_page_shows_the_numbers_and_the_notes_in_german(user: User):
    content, _ = a_file()
    await to_profile(user, "?area=profile&lang=de")

    await upload(user, content)

    assert texts(user, "profile-fact-period") == ["Zeitraum", "05.02.2024 00:00 bis 07.02.2024 00:00"]
    assert texts(user, "profile-fact-step")[1] == "15 Minuten" and texts(user, "profile-fact-missing")[1] == "0 %"
    assert any("Zeitpunkte von 05.02.2024" in label for label in texts(user, "profile-note-file_info"))


async def test_the_settings_are_there_for_a_file_that_is_ready_and_show_what_was_worked_out(user: User):
    content, _ = a_file()
    await to_profile(user)

    await upload(user, content)

    assert field(user, "profile-ask-unit").value == "kW" and field(user, "profile-ask-stamp").value == "start"
    assert not exists(user, "profile-ask-column") and not exists(user, "profile-ask-energy")


async def test_a_gap_in_the_file_is_shown_as_a_warning_and_in_the_missing_value(user: User):
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)
    text = render(index[:50], values[:50]) + "\n".join(
        line for line in render(index[60:], values[60:]).splitlines()[1:]) + "\n"
    await to_profile(user)

    await upload(user, text.encode())

    assert exists(user, "profile-note-gaps") and texts(user, "profile-fact-missing") == ["Missing", "5.2 %"]


# ---------------------------------------------------------------------------
# what the file does not say
# ---------------------------------------------------------------------------

async def test_a_file_without_a_unit_asks_for_it_and_shows_what_the_two_readings_would_give(user: User):
    content, values = a_file(header="Zeit;Wert")
    await to_profile(user)

    await upload(user, content)

    assert exists(user, "profile-ask-hint") and field(user, "profile-ask-unit").value is None
    assert not exists(user, "profile-summary")
    preview = texts(user, "profile-settings")
    assert any(f"{EN.integer(round(values.sum() / 4))} kWh" in line and f"{EN.integer(round(values.sum()))} kWh" in line for line in preview)


async def test_the_answer_is_applied_and_the_file_is_read_again_with_it(user: User):
    content, values = a_file(header="Zeit;Wert")
    await to_profile(user)
    await upload(user, content)

    field(user, "profile-ask-unit").set_value("kWh")
    await apply(user)

    assert exists(user, "profile-summary") and not exists(user, "profile-ask-hint")
    assert texts(user, "profile-fact-energy")[1] == f"{EN.integer(round(values.sum()))} kWh"
    assert exists(user, "profile-note-unit_info")


async def test_applying_without_the_answer_that_is_asked_says_so_and_changes_nothing(user: User):
    content, _ = a_file(header="Zeit;Wert")
    await to_profile(user)
    await upload(user, content)

    user.find(marker="profile-ask-apply").click()
    await settle()

    assert user.notify.contains("Please fill in what is asked first.") and exists(user, "profile-ask-hint")
    assert not exists(user, "profile-summary")


async def test_two_columns_that_could_be_the_load_ask_which_and_then_it_is_read(user: User):
    content, values = a_file(columns=("Last Halle 1 kW", "Last Halle 2 kW"))
    await to_profile(user)
    await upload(user, content)
    assert exists(user, "profile-ask-hint") and not exists(user, "profile-summary")
    assert field(user, "profile-ask-column").value is None

    field(user, "profile-ask-column").set_value("Last Halle 2 kW")
    await apply(user)

    assert exists(user, "profile-summary") and field(user, "profile-ask-column").value == "Last Halle 2 kW"
    assert texts(user, "profile-fact-peak")[1] == f"{EN.number(round(float(np.round(values / 3, 3).max()), 1))} kW"


async def test_a_column_of_shares_asks_for_the_energy_and_an_energy_that_is_not_above_zero_is_refused(user: User):
    content, _ = workshop(hours=240)
    await to_profile(user)
    await upload(user, content.encode(), "workshop.csv")
    assert exists(user, "profile-ask-energy") and not exists(user, "profile-ask-unit") and exists(user, "profile-ask-hint")

    field(user, "profile-ask-energy").set_value(0)
    user.find(marker="profile-ask-apply").click()
    await settle()
    assert user.notify.contains("Please give an energy above zero, in kWh.") and not exists(user, "profile-summary")

    field(user, "profile-ask-energy").set_value(12000)
    await apply(user)

    assert exists(user, "profile-summary") and texts(user, "profile-fact-energy")[1] == "12,000 kWh"
    assert exists(user, "profile-note-share_info") and field(user, "profile-ask-energy").value == 12000


async def test_what_the_reader_was_not_sure_about_stays_a_warning_until_the_visitor_decides_it(user: User):
    content, _ = a_file(first="2024-02-05 08:00", last="2024-02-06 16:45")
    await to_profile(user)

    await upload(user, content)
    assert exists(user, "profile-note-stamp_assumed")
    assert texts(user, "profile-fact-period")[1] == "2024-02-05 08:00 to 2024-02-06 17:00"

    field(user, "profile-ask-stamp").set_value("end")
    await apply(user)

    assert not exists(user, "profile-note-stamp_assumed") and field(user, "profile-ask-stamp").value == "end"
    assert texts(user, "profile-fact-period")[1] == "2024-02-05 07:45 to 2024-02-06 16:45"


async def test_an_answer_to_one_question_does_not_decide_another_that_the_reader_was_not_sure_about(user: User):
    content, _ = a_file(header="Zeit;Wert", first="2024-02-05 08:00", last="2024-02-06 16:45")
    await to_profile(user)
    await upload(user, content)

    field(user, "profile-ask-unit").set_value("kW")
    await apply(user)

    assert exists(user, "profile-summary") and exists(user, "profile-note-stamp_assumed")


# ---------------------------------------------------------------------------
# a file that cannot be used
# ---------------------------------------------------------------------------

async def test_a_file_without_a_time_is_explained_and_nothing_else_is_shown(user: User):
    await to_profile(user)

    await upload(user, b"Name;kW\na;1\nb;2\nc;3\nd;4\n")

    assert field(user, "profile-error").text == "No column with dates and times was found."
    assert not any(exists(user, marker) for marker in ("profile-settings", "profile-summary", "profile-notes"))


async def test_a_file_that_is_empty_is_explained_by_the_reader_of_files(user: User):
    await to_profile(user)

    await upload(user, b"", "leer.csv")

    assert exists(user, "profile-error") and not exists(user, "profile-summary")


async def test_a_german_page_explains_an_error_in_german(user: User):
    await to_profile(user, "?area=profile&lang=de")

    await upload(user, b"Name;kW\na;1\nb;2\nc;3\nd;4\n")

    assert field(user, "profile-error").text == "Es wurde keine Spalte mit Datum und Uhrzeit gefunden."


async def test_a_reading_that_breaks_in_a_way_that_was_not_foreseen_is_told_and_logged_and_the_page_goes_on(user: User, monkeypatch, caplog):
    def broken(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(ProfileSession, "read", broken)
    content, _ = a_file()
    await to_profile(user)

    await upload(user, content)

    assert exists(user, "profile-failed") and not exists(user, "profile-summary") and exists(user, "profile-remove")
    assert "could not be read" in caplog.text
    caplog.clear()


# ---------------------------------------------------------------------------
# the file stays with the project
# ---------------------------------------------------------------------------

async def test_another_file_can_be_loaded_after_taking_the_first_away(user: User):
    content, _ = a_file()
    await to_profile(user)
    await upload(user, content)

    user.find(marker="profile-remove").click()
    await settle()

    assert exists(user, "profile-upload") and not exists(user, "profile-file") and not exists(user, "profile-summary")


async def test_the_file_is_still_there_after_a_visit_to_the_start_page_and_the_start_card_says_to_continue(user: User):
    content, _ = a_file()
    await to_profile(user)
    await upload(user, content)

    field(user, "area-bar").set_value("start")
    await settle()
    assert field(user, "start-profile").text == "Continue with the load profile"
    user.find(marker="start-profile").click()
    await settle()

    assert exists(user, "profile-summary") and field(user, "profile-file").text == "File: Lastgang.csv"


async def test_the_language_switch_keeps_the_file_and_shows_it_in_the_new_language(user: User):
    content, _ = a_file()
    await to_profile(user)
    await upload(user, content)

    await switched_to(user, "de")
    await settle()

    assert field(user, "area-bar").value == "profile" and field(user, "profile-file").text == "Datei: Lastgang.csv"
    assert texts(user, "profile-fact-step") == ["Zeitschritt", "15 Minuten"]


async def test_while_the_file_is_being_read_the_page_says_so_and_goes_on_working(user: User, monkeypatch):
    release = threading.Event()
    original = ProfileSession.read

    def slow(self):
        release.wait(10)
        original(self)

    monkeypatch.setattr(ProfileSession, "read", slow)
    content, _ = a_file()
    await to_profile(user)

    await field(user, "profile-upload").handle_uploads([SmallFileUpload("Lastgang.csv", "text/csv", content)])
    await settle()
    assert exists(user, "profile-reading") and not exists(user, "profile-summary")

    field(user, "area-bar").set_value("start")                         # the visitor goes away meanwhile
    await settle()
    release.set()
    await asyncio.sleep(1.0)
    field(user, "area-bar").set_value("profile")
    await settle()

    assert not exists(user, "profile-reading") and exists(user, "profile-summary")