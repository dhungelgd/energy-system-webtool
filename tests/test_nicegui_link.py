"""One file for the whole session on the NiceGUI page: the file that the load profile page holds is also the file of the
optimization (simulated user)."""

import pytest

pytest.importorskip("nicegui")
from nicegui.testing import User  # noqa: E402

from tests.test_nicegui_bulk import texts, upload as upload_bulk  # noqa: E402
from tests.test_nicegui_draft_run import exists, field, settle  # noqa: E402
from tests.test_nicegui_frame import views  # noqa: E402
from tests.test_nicegui_profile import (  # noqa: E402
    THREE_WEEKS,
    a_file,
    apply,
    loaded,
    reading_done,
    several_columns_file,
    to_profile,
    upload,
    workbook_bytes,
)
from tests.test_series_bulk import ALL, csv  # noqa: E402


async def link(user: User):
    user.find(marker="profile-use-in-optimization").click()
    await settle()


async def to_area(user: User, key):
    field(user, "area-bar").set_value(key)
    await settle()


# ---------------------------------------------------------------------------
# from the load profile page to the optimization
# ---------------------------------------------------------------------------

async def test_the_row_of_the_file_has_a_button_that_takes_the_file_to_the_card_of_the_optimization(user: User):
    await loaded(user)
    assert exists(user, "profile-use-in-optimization") and field(user, "profile-use-in-optimization").text == "Use this file in the optimization"

    await link(user)

    assert field(user, "area-bar").value == "optimization" and exists(user, "series-bulk-prepare")
    assert "Lastgang.csv" in texts(user, "series-bulk-prepare")[0]
    assert not exists(user, "series-bulk-from-profile")                              # it is the file of the optimization now


async def test_the_column_that_was_analysed_is_the_suggested_demand_and_not_the_first_that_fits(user: User):
    await to_profile(user)
    await upload(user, several_columns_file(), "zeitreihen.csv")
    field(user, "profile-ask-column").set_value("strom_hoch_kwh")
    await apply(user)

    await link(user)
    user.find(marker="series-bulk-add-components").click()
    await settle()

    assert field(user, "series-bulk-map-demand").value == "strom_hoch_kwh"


async def test_a_file_that_is_not_ready_as_a_profile_can_still_be_used_and_the_name_decides(user: User):
    await to_profile(user)
    await upload(user, several_columns_file(), "zeitreihen.csv")
    assert not exists(user, "analysis-kpis") and exists(user, "profile-use-in-optimization")

    await link(user)
    user.find(marker="series-bulk-add-components").click()
    await settle()

    assert field(user, "series-bulk-map-demand").value == "strom_niedrig_kwh"


async def test_the_sheet_and_the_settings_of_the_load_profile_page_are_the_sheet_and_the_settings_of_the_optimization(user: User):
    await to_profile(user)
    await upload(user, workbook_bytes(), "jahre.xlsx")
    field(user, "series-sheet-profile").set_value("2022")
    await settle()
    await reading_done(user)

    await link(user)

    assert field(user, "series-sheet-bulk").value == "2022"
    assert "2022-02-05" in field(user, "series-bulk-period-info").text and "2023" not in field(user, "series-bulk-period-info").text


async def test_a_quarter_hour_profile_says_that_the_optimization_works_on_hours_and_an_hourly_one_does_not(user: User):
    await loaded(user)
    await link(user)

    assert field(user, "series-bulk-peak-note").text == (
        "The optimization works on hourly values, so its highest hour is lower than the highest value of the load profile "
        "(time step: 15 minutes).")


async def test_an_hourly_profile_has_no_note_about_the_peak(user: User):
    await to_profile(user)
    await upload(user, several_columns_file(), "zeitreihen.csv")
    field(user, "profile-ask-column").set_value("strom_hoch_kwh")
    await apply(user)

    await link(user)

    assert exists(user, "series-bulk-prepare") and not exists(user, "series-bulk-peak-note")


async def test_an_unreadable_file_has_no_button(user: User):
    content, _ = a_file(**THREE_WEEKS)
    await loaded(user, content)

    field(user, "series-encoding-profile").set_value("utf-16")
    await settle()
    await reading_done(user)

    assert exists(user, "profile-error") and not exists(user, "profile-use-in-optimization")


async def test_the_button_and_the_card_are_in_german_for_a_german_page(user: User):
    await loaded(user, query="?area=profile&lang=de")
    assert field(user, "profile-use-in-optimization").text == "Datei in der Optimierung verwenden"

    await link(user)

    assert "Lastgang.csv" in texts(user, "series-bulk-prepare")[0]
    assert field(user, "series-bulk-peak-note").text.startswith("Die Optimierung rechnet mit Stundenwerten")


# ---------------------------------------------------------------------------
# from the optimization to the file of the load profile page
# ---------------------------------------------------------------------------

async def test_the_card_of_the_optimization_offers_the_file_of_the_load_profile_page_and_not_without_one(user: User):
    await user.open("/")
    assert not exists(user, "series-bulk-from-profile")

    await to_area(user, "profile")
    await upload(user, several_columns_file(), "zeitreihen.csv")
    await to_area(user, "optimization")

    assert field(user, "series-bulk-from-profile").text == "Use the file of the load profile page: zeitreihen.csv"
    user.find(marker="series-bulk-from-profile").click()
    await settle()

    assert exists(user, "series-bulk-prepare") and not exists(user, "series-bulk-from-profile")
    assert "zeitreihen.csv" in texts(user, "series-bulk-prepare")[0]


async def test_a_file_that_was_uploaded_in_the_optimization_does_not_hide_the_offer_of_the_file_of_the_load_profile_page(user: User):
    await user.open("/")
    await upload_bulk(user, csv(ALL))
    assert not exists(user, "series-bulk-from-profile")

    await to_area(user, "profile")
    await upload(user, several_columns_file(), "zeitreihen.csv")
    await to_area(user, "optimization")

    assert exists(user, "series-bulk-from-profile") and "alle.csv" in texts(user, "series-bulk-prepare")[0]


# ---------------------------------------------------------------------------
# taking the file away
# ---------------------------------------------------------------------------

async def test_taking_the_file_away_on_the_load_profile_page_takes_it_from_the_optimization_too(user: User):
    await loaded(user)
    await link(user)
    assert exists(user, "series-bulk-prepare")

    await to_area(user, "profile")
    user.find(marker="profile-remove").click()
    await settle()
    await to_area(user, "optimization")

    assert not exists(user, "series-bulk-prepare") and not exists(user, "series-bulk-from-profile")


async def test_a_file_that_was_uploaded_in_the_optimization_stays_when_the_load_profile_file_is_taken_away(user: User):
    await user.open("/")
    await upload_bulk(user, csv(ALL))
    await to_area(user, "profile")
    await upload(user, several_columns_file(), "zeitreihen.csv")

    user.find(marker="profile-remove").click()
    await settle()
    await to_area(user, "optimization")

    assert exists(user, "series-bulk-prepare") and "alle.csv" in texts(user, "series-bulk-prepare")[0]


async def test_the_page_says_that_the_file_stays_in_the_session_and_is_not_saved(user: User):
    await to_profile(user)

    assert "stays in the memory of your session" in field(user, "profile-intro").text and "not saved on the server" in field(user, "profile-intro").text
    assert "keeps nothing" not in field(user, "profile-intro").text


async def test_the_visitor_who_was_in_another_view_of_the_optimization_lands_in_the_view_with_the_card(user: User):
    await user.open("/")
    views(user).set_value("check")
    await settle()
    await to_area(user, "profile")
    await upload(user, several_columns_file(), "zeitreihen.csv")

    await link(user)

    assert field(user, "area-bar").value == "optimization" and views(user).value == "system" and exists(user, "series-bulk-prepare")


async def test_a_file_of_the_load_profile_page_that_cannot_be_read_is_not_offered_in_the_optimization(user: User):
    content, _ = a_file(**THREE_WEEKS)
    await loaded(user, content)
    field(user, "series-encoding-profile").set_value("utf-16")
    await settle()
    await reading_done(user)
    assert exists(user, "profile-error")

    await to_area(user, "optimization")

    assert not exists(user, "series-bulk-from-profile")


async def test_a_file_with_the_date_and_the_time_of_day_in_two_columns_can_be_analysed_and_used_in_the_optimization(user: User):
    from tests.test_shared_file import two_column_file

    content, _ = two_column_file()
    await to_profile(user)
    await upload(user, content, "netz.csv")
    assert exists(user, "analysis-kpis") and exists(user, "profile-note-time_joined")

    await link(user)
    user.find(marker="series-bulk-add-components").click()
    await settle()

    assert "2024-02-05 00:00" in field(user, "series-bulk-period-info").text and "48" in field(user, "series-bulk-period-info").text
    assert exists(user, "series-bulk-status-demand") and not exists(user, "series-bulk-error")
    assert any("48" in line for line in texts(user, "series-bulk-status-demand"))