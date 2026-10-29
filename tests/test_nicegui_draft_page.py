"""Name, period and live system check of the scenario that is built on the page (simulated user)."""

import asyncio

import pytest

pytest.importorskip("nicegui")
from nicegui import ui  # noqa: E402
from nicegui.testing import User  # noqa: E402

from frontend_nicegui.draft import DEFAULT_NAME, START_HINT, STEPS_HINT  # noqa: E402
from frontend_nicegui.markers import slug  # noqa: E402


def field(user: User, marker: str):
    return user.find(marker=marker).elements.pop()


async def choose_template(user: User, name: str):
    user.find(marker=f"template-{slug(name)}").click()
    await user.should_see(marker="selection-count")


async def type_into(user: User, marker: str, text: str):
    user.find(marker=marker).clear().type(text)


async def settle():
    """Let the page apply what was typed: it updates a moment after the typing.

    Needed when the page must NOT change: waiting for a text that is already there proves nothing.
    """

    await asyncio.sleep(0.3)


def period_text(user: User):
    return field(user, "draft-period").text


async def finding_texts(user: User):
    await user.should_see(marker="draft-findings")
    card = field(user, "draft-findings")
    return [element.text for element in card.descendants() if isinstance(element, ui.label)]


# ---------------------------------------------------------------------------
# the start
# ---------------------------------------------------------------------------

async def test_the_page_starts_with_the_defaults_of_a_scenario(user: User):
    await user.open("/")

    await user.should_see("Your scenario")
    assert field(user, "draft-name").value == ""  # not named yet ...
    assert field(user, "draft-name").props["placeholder"] == DEFAULT_NAME  # ... and it says what then
    assert field(user, "draft-start").value == "2021-01-01"
    assert field(user, "draft-steps").value == 8760
    await user.should_see("Period: 8760 hourly steps (365 days) from 01.01.2021 00:00")
    await user.should_see("The model works in hourly steps")


# ---------------------------------------------------------------------------
# the number of steps
# ---------------------------------------------------------------------------

async def test_typing_the_steps_changes_the_period(user: User):
    await user.open("/")

    await type_into(user, "draft-steps", "48")

    await user.should_see("Period: 48 hourly steps (2 days) from 01.01.2021 00:00")


@pytest.mark.parametrize("marker, text", [
    ("steps-24", "24 hourly steps (1 day)"),
    ("steps-168", "168 hourly steps (7 days)"),
    ("steps-8760", "8760 hourly steps (365 days)"),
])
async def test_the_buttons_set_a_day_a_week_or_a_year(user: User, marker, text):
    await user.open("/")
    await type_into(user, "draft-steps", "100")
    await user.should_see("100 hourly steps")

    user.find(marker=marker).click()

    await user.should_see(text)
    assert field(user, "draft-steps").value == int(marker.split("-")[1])


@pytest.mark.parametrize("text", ["0", "8785", "1.5"])
async def test_steps_that_do_not_fit_keep_the_old_period_and_say_why(user: User, text):
    await user.open("/")
    await type_into(user, "draft-steps", "24")
    await user.should_see("Period: 24 hourly steps")

    await type_into(user, "draft-steps", text)
    await settle()

    assert period_text(user) == "Period: 24 hourly steps (1 day) from 01.01.2021 00:00"
    assert field(user, "draft-steps").error == STEPS_HINT


async def test_steps_that_were_wrong_and_are_then_corrected_work_again(user: User):
    await user.open("/")
    await type_into(user, "draft-steps", "0")
    assert field(user, "draft-steps").error == STEPS_HINT

    await type_into(user, "draft-steps", "72")

    await user.should_see("Period: 72 hourly steps (3 days)")
    assert field(user, "draft-steps").error is None


# ---------------------------------------------------------------------------
# the start date
# ---------------------------------------------------------------------------

async def test_typing_a_start_date_changes_the_period(user: User):
    await user.open("/")

    await type_into(user, "draft-start", "2022-03-01")

    await user.should_see("from 01.03.2022 00:00")
    assert field(user, "draft-start").error is None


@pytest.mark.parametrize("text", ["2022-13-01", "01.03.2022", "1979-01-01", "tomorrow"])
async def test_a_start_date_that_does_not_fit_keeps_the_old_one_and_says_why(user: User, text):
    await user.open("/")
    await type_into(user, "draft-start", "2022-03-01")
    await user.should_see("from 01.03.2022 00:00")

    await type_into(user, "draft-start", text)
    await settle()

    assert period_text(user) == "Period: 8760 hourly steps (365 days) from 01.03.2022 00:00"
    assert field(user, "draft-start").error == START_HINT


async def test_the_calendar_and_the_field_show_the_same_date(user: User):
    await user.open("/")
    calendar = user.find(kind=ui.date).elements.pop()
    assert calendar.value == "2021-01-01"

    calendar.value = "2023-05-04"

    await user.should_see("from 04.05.2023 00:00")
    assert field(user, "draft-start").value == "2023-05-04"

    await type_into(user, "draft-start", "2024-02-29")

    await user.should_see("from 29.02.2024 00:00")
    assert calendar.value == "2024-02-29"


# ---------------------------------------------------------------------------
# the name
# ---------------------------------------------------------------------------

async def test_the_name_is_the_title_of_the_scenario(user: User):
    await user.open("/")
    await choose_template(user, "Electricity only")
    await user.should_see(marker="draft-title", content=DEFAULT_NAME)

    await type_into(user, "draft-name", "Bakery Meier")

    # with a text as first argument should_see ignores the marker and finds the text in the
    # input field at once; marker and content together wait for the title itself
    await user.should_see(marker="draft-title", content="Bakery Meier")
    assert field(user, "draft-title").text == "Bakery Meier"


async def test_a_blank_name_falls_back_to_the_default_name(user: User):
    await user.open("/")
    await choose_template(user, "Electricity only")
    await type_into(user, "draft-name", "Bakery Meier")
    await user.should_see(marker="draft-title", content="Bakery Meier")

    user.find(marker="draft-name").clear()

    await user.should_see(marker="draft-title", content=DEFAULT_NAME)
    assert field(user, "draft-title").text == DEFAULT_NAME


@pytest.mark.parametrize("marker", ["draft-name", "draft-start", "draft-steps"])
async def test_the_fields_wait_for_a_pause_in_the_typing(user: User, marker):
    # in a browser a check runs when the typing pauses, not for every key
    await user.open("/")

    assert field(user, marker).props["debounce"] == "300"          # properties come back as text


async def test_the_empty_name_field_shows_what_the_default_is(user: User):
    await user.open("/")

    assert field(user, "draft-name").props["placeholder"] == DEFAULT_NAME


async def test_there_is_no_title_and_no_check_before_something_is_selected(user: User):
    await user.open("/")

    await type_into(user, "draft-name", "Bakery Meier")

    await user.should_not_see(marker="draft-title")
    await user.should_not_see(marker="draft-findings")


# ---------------------------------------------------------------------------
# the live system check
# ---------------------------------------------------------------------------

async def test_the_check_appears_with_the_first_component_and_says_what_is_missing(user: User):
    await user.open("/")
    await user.should_not_see(marker="draft-findings")

    await choose_template(user, "Gas heating")

    await user.should_see("System check of your scenario")
    texts = await finding_texts(user)
    assert any(t.startswith("Heat demand: no time series") for t in texts)
    assert any(t.startswith("Gas boiler: fixed mode needs a capacity") for t in texts)
    assert "Fix the errors above before the optimization can start." in texts


async def test_the_check_follows_every_change(user: User):
    await user.open("/")
    await choose_template(user, "Gas heating")
    assert not any(t.startswith("Electricity demand") for t in await finding_texts(user))

    user.find(marker="component-demand").click()
    await user.should_see("Electricity demand: no time series")

    user.find(marker="component-gas_boiler").click()
    await user.should_not_see("Gas boiler: fixed mode needs a capacity")


async def test_clearing_the_selection_removes_the_check(user: User):
    await user.open("/")
    await choose_template(user, "PV + battery")
    await user.should_see(marker="draft-findings")

    user.find(marker="clear-selection").click()

    await user.should_not_see(marker="draft-findings")
    await user.should_see("Nothing selected yet")


async def test_the_page_says_that_the_forms_and_the_upload_are_not_there_yet(user: User):
    await user.open("/")

    await user.should_see("Work in progress")
    await user.should_see("open a complete scenario file further down")


async def test_the_check_of_the_draft_and_of_an_opened_file_do_not_get_mixed_up(user: User):
    from pathlib import Path

    from nicegui.elements.upload_files import SmallFileUpload

    await user.open("/")
    await choose_template(user, "Gas heating")
    path = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2" / "pv_and_grid.json"

    upload = user.find(marker="upload").elements.pop()
    await upload.handle_uploads([SmallFileUpload("pv_and_grid.json", "application/json", path.read_bytes())])

    await user.should_see("System check passed. Ready to optimize.")      # the file
    await user.should_see("System check of your scenario")                # the draft, still there
    assert len(user.find(marker="findings").elements) == 1
    assert len(user.find(marker="draft-findings").elements) == 1