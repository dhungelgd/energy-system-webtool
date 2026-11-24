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
from tests.test_profile_session import two_years  # noqa: E402

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
        if not exists(user, "profile-reading") and not exists(user, "profile-analysing"):
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


# ---------------------------------------------------------------------------
# the analysis: key figures, tabs, charts, choices
# ---------------------------------------------------------------------------

THREE_WEEKS = dict(first="2024-02-05 00:00", last="2024-02-25 23:45")


def names_of(user, marker="analysis-typical"):
    """The names of the lines in a chart of the typical days (the bands have none)."""

    return [trace["name"] for trace in field(user, marker).figure["data"] if trace.get("name")]


async def loaded(user: User, content=None, query="?area=profile", **file):
    content = content if content is not None else a_file(**(file or THREE_WEEKS))[0]
    await to_profile(user, query)
    await upload(user, content)


async def test_a_file_that_is_ready_shows_the_key_figures_and_two_tabs_and_the_charts(user: User):
    await loaded(user)

    assert exists(user, "analysis-kpis") and field(user, "analysis-tabs").value == "overview"
    for key in ("energy", "peak", "base_percentile", "base_night", "utilization", "load_factor"):
        assert exists(user, f"analysis-kpi-{key}"), key
    assert [field(user, f"analysis-tab-{name}").props["label"] for name in ("overview", "quality")] == ["Overview", "Data quality"]
    assert all(exists(user, marker) for marker in ("analysis-typical", "analysis-duration", "analysis-monthly", "analysis-hints"))


async def test_the_key_figures_are_those_of_the_profile(user: User):
    content, values = a_file(**THREE_WEEKS)
    index = starts(THREE_WEEKS["first"], THREE_WEEKS["last"])
    await loaded(user, content)

    assert texts(user, "analysis-kpi-energy") == ["Energy in the period", f"{EN.integer(round(values.sum() / 4))} kWh", "21 days"]
    assert texts(user, "analysis-kpi-peak") == [
        "Peak load", f"{EN.number(round(float(values.max()), 1))} kW", f"on {index[int(np.argmax(values))].strftime('%Y-%m-%d %H:%M')}"]
    assert texts(user, "analysis-kpi-utilization") == ["Hours of use", "–", "Only for 330 days or more"]
    assert texts(user, "analysis-kpi-load_factor")[0] == "Load factor"


async def test_the_page_shows_the_key_figures_and_the_tabs_in_german(user: User):
    await loaded(user, query="?area=profile&lang=de")

    assert texts(user, "analysis-kpi-energy")[0] == "Energie im Zeitraum" and texts(user, "analysis-kpi-energy")[2] == "21 Tage"
    assert texts(user, "analysis-kpi-base_percentile")[0] == "Grundlast (95-%-Wert)" and texts(user, "analysis-kpi-base_night")[0] == "Grundlast (Nacht)"
    assert [field(user, f"analysis-tab-{name}").props["label"] for name in ("overview", "quality")] == ["Übersicht", "Datenqualität"]
    assert texts(user, "analysis-card-typical")[0] == "Typische Tage" and any("Tagesspitzen" in t or "Grundlast" in t or "Last erreicht" in t for t in texts(user, "analysis-hints"))


async def test_the_observations_are_there_and_say_how_rare_the_peak_is(user: User):
    await loaded(user)

    assert texts(user, "analysis-hints")[0] == "Observations" and exists(user, "analysis-hint-peak_rare")
    assert any("90 % of the peak" in line for line in texts(user, "analysis-hint-peak_rare"))


async def test_a_profile_with_too_few_days_for_a_typical_day_says_so_instead_of_drawing_one(user: User):
    await loaded(user, **dict(first="2024-02-05 00:00", last="2024-02-06 23:45"))

    assert field(user, "analysis-typical-none").text == "A typical day needs at least 3 days of its kind."
    assert exists(user, "analysis-duration") and exists(user, "analysis-monthly") and not exists(user, "analysis-typical")


async def test_the_lines_of_the_typical_days_are_for_the_types_of_day_that_have_enough_days(user: User):
    await loaded(user)

    assert names_of(user) == ["Workday (n = 15)", "Saturday (n = 3)", "Sunday or holiday (n = 3)"]


async def test_the_data_of_the_file_is_in_the_second_tab_with_the_count_of_the_warnings_a_gap_adds_one(user: User):
    index = starts("2024-02-05 00:00", "2024-02-25 23:45")
    values = kw(index)
    text = render(index[:200], values[:200]) + "\n".join(render(index[220:], values[220:]).splitlines()[1:]) + "\n"
    await loaded(user, text.encode())

    assert field(user, "analysis-quality-badge").text == "2"                          # the gap, and that the profile is not a year
    assert exists(user, "profile-summary") and exists(user, "profile-settings") and exists(user, "profile-notes")


async def test_a_file_without_a_gap_has_only_the_warning_that_it_is_less_than_a_year(user: User):
    await loaded(user)

    assert field(user, "analysis-quality-badge").text == "1" and exists(user, "profile-note-short_period")


async def test_a_file_that_is_not_ready_has_no_key_figures_and_no_tabs(user: User):
    content, _ = a_file(header="Zeit;Wert", **THREE_WEEKS)
    await loaded(user, content)

    assert exists(user, "profile-ask-hint") and not any(exists(user, m) for m in ("analysis-kpis", "analysis-tabs", "analysis-settings"))


async def test_the_state_is_bavaria_at_first_and_it_has_the_assumption_to_switch(user: User):
    await loaded(user)

    assert field(user, "analysis-state").value == "BY" and field(user, "analysis-catholic").value is True
    assert not exists(user, "analysis-year") and exists(user, "analysis-settings-hint")


async def test_another_state_gives_other_holidays_and_the_typical_days_follow(user: User):
    content, _ = a_file(first="2023-01-02 00:00", last="2023-01-22 23:45")           # the 6th of January is a Friday
    await loaded(user, content)
    assert names_of(user)[0] == "Workday (n = 14)"

    field(user, "analysis-state").set_value("NW")
    await settle()
    await reading_done(user)

    assert names_of(user)[0] == "Workday (n = 15)" and field(user, "analysis-state").value == "NW"
    assert not exists(user, "analysis-catholic")                                        # only Bavaria has the choice


async def test_the_assumption_can_be_switched_off_and_the_typical_days_follow(user: User):
    content, _ = a_file(first="2023-08-14 00:00", last="2023-09-03 23:45")
    await loaded(user, content)
    assert names_of(user)[0] == "Workday (n = 14)"

    field(user, "analysis-catholic").set_value(False)
    await settle()
    await reading_done(user)

    assert names_of(user)[0] == "Workday (n = 15)" and field(user, "analysis-catholic").value is False


async def test_a_profile_of_two_years_is_analysed_for_the_latest_year_and_the_period_can_be_changed(user: User):
    text, index = two_years()
    values = kw(index)
    await loaded(user, text.encode())

    assert field(user, "analysis-year").value == "2023"
    assert texts(user, "analysis-kpi-energy")[:2] == ["Yearly energy", f"{EN.integer(round(values[index.year == 2023].sum()))} kWh"]

    field(user, "analysis-year").set_value("all")
    await settle()
    await reading_done(user)
    assert texts(user, "analysis-kpi-energy")[1] == f"{EN.integer(round(values.sum()))} kWh"

    field(user, "analysis-year").set_value("2022")
    await settle()
    await reading_done(user)
    assert texts(user, "analysis-kpi-energy")[1] == f"{EN.integer(round(values[index.year == 2022].sum()))} kWh"
    assert field(user, "analysis-year").value == "2022"


async def test_the_tab_that_is_open_stays_open_when_an_answer_reads_the_file_again(user: User):
    await loaded(user)
    field(user, "analysis-tabs").set_value("quality")
    await settle()

    field(user, "profile-ask-stamp").set_value("end")
    await apply(user)

    assert field(user, "analysis-tabs").value == "quality" and exists(user, "profile-summary")
    assert not exists(user, "profile-note-stamp_assumed") and field(user, "profile-ask-stamp").value == "end"


async def test_the_language_switch_keeps_the_tab_and_the_choices_of_the_analysis(user: User):
    await loaded(user)
    field(user, "analysis-state").set_value("SN")
    await settle()
    await reading_done(user)
    field(user, "analysis-tabs").set_value("quality")
    await settle()

    await switched_to(user, "de")
    await settle()

    assert field(user, "analysis-tabs").value == "quality" and field(user, "analysis-state").value == "SN"
    assert field(user, "analysis-tab-overview").props["label"] == "Übersicht"


async def test_while_the_analysis_is_worked_out_again_the_page_says_so(user: User, monkeypatch):
    await loaded(user)
    release = threading.Event()
    original = ProfileSession.analyse

    def slow(self):
        release.wait(10)
        original(self)

    monkeypatch.setattr(ProfileSession, "analyse", slow)

    field(user, "analysis-state").set_value("BE")
    await settle()
    assert exists(user, "profile-analysing") and not exists(user, "analysis-kpis")

    release.set()
    await reading_done(user)

    assert not exists(user, "profile-analysing") and exists(user, "analysis-kpis") and field(user, "analysis-state").value == "BE"


async def test_an_analysis_that_has_no_values_to_work_on_is_told_and_the_data_of_the_file_is_still_shown(user: User, monkeypatch):
    def nothing(self):
        self.analysis, self.analysis_failed = None, True                                # what the session does when it raises

    monkeypatch.setattr(ProfileSession, "analyse", nothing)

    await loaded(user)

    assert field(user, "analysis-error").text == "The profile could not be analysed: there are no values in the chosen period."
    assert exists(user, "profile-summary") and exists(user, "analysis-settings") and not exists(user, "analysis-kpis")


async def test_a_german_page_has_the_choices_of_the_analysis_in_german(user: User):
    await loaded(user, query="?area=profile&lang=de")

    assert field(user, "analysis-state").props["label"] == "Feiertage von" and field(user, "analysis-catholic").text.startswith("Mariä Himmelfahrt")
    assert any(label.startswith("Die Tagesarten") for label in texts(user, "analysis-settings-hint")) or field(user, "analysis-settings-hint").text.startswith("Die Tagesarten")


async def test_a_new_file_begins_in_the_overview_even_if_the_data_tab_was_open_before(user: User):
    content, _ = a_file(**THREE_WEEKS)
    await loaded(user, content)
    field(user, "analysis-tabs").set_value("quality")
    await settle()

    user.find(marker="profile-remove").click()
    await settle()
    await upload(user, content)

    assert field(user, "analysis-tabs").value == "overview"