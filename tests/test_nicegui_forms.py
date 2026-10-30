"""The forms of the components on the NiceGUI page (simulated user, no browser)."""

import asyncio

import pytest

pytest.importorskip("nicegui")
from nicegui import ElementFilter, ui  # noqa: E402
from nicegui.testing import User  # noqa: E402

from frontend_nicegui.markers import slug  # noqa: E402

CAPACITY = "field-pv-capacity-capacity"
MODE = "field-pv-capacity-mode"
INVEST_MARKERS = [f"field-pv-capacity-{key}" for key in ("maximum", "capex", "opex", "lifetime", "interest_rate")]


def field(user: User, marker: str):
    return user.find(marker=marker).elements.pop()


def exists(user: User, marker: str):
    # user.find() fails when there is no such element; this answers yes or no
    with user.client:
        return bool(list(ElementFilter(marker=marker)))


async def open_page(user: User, language=None):
    await user.open("/" if language is None else f"/?lang={language}")


async def choose_template(user: User, name: str):
    user.find(marker=f"template-{slug(name)}").click()
    await user.should_see(marker="selection-count")


async def settle():
    await asyncio.sleep(0.3)


async def pv_row(user: User):
    await user.should_see(marker="draft-components")
    rows = field(user, "draft-components").rows
    return next(row for row in rows if row["type"] in ("PV system", "PV-Anlage"))


async def wait_for_size(user: User, expected: str):
    """Wait until the table shows the size of the PV system. (The text of a table is in its rows, so
    should_see(content=...) cannot wait for it.)"""

    for _ in range(60):
        if (await pv_row(user))["size"] == expected:
            return
        await asyncio.sleep(0.05)

    assert (await pv_row(user))["size"] == expected


async def pick_mode(user: User, mode: str):
    field(user, MODE).value = mode
    marker = INVEST_MARKERS[0] if mode == "invest" else CAPACITY
    await user.should_see(marker=marker)


async def switched_to(user: User, language: str):
    field(user, "language").value = language
    from backend.i18n import catalog
    await user.should_see(marker="app-title", content=catalog(language)["app.title"])


# ---------------------------------------------------------------------------
# which components have a form
# ---------------------------------------------------------------------------

async def test_there_is_no_form_without_a_pv_system(user: User):
    await open_page(user)

    await choose_template(user, "Electricity only")

    assert not exists(user, "form-pv")
    await user.should_not_see("Settings of")


async def test_a_pv_system_gets_a_card_with_its_settings(user: User):
    await open_page(user)

    await choose_template(user, "PV system")

    await user.should_see(marker="form-pv")
    await user.should_see("Settings of PV system")
    assert exists(user, MODE) and exists(user, CAPACITY)


async def test_only_the_components_with_a_form_get_one(user: User):
    await open_page(user)

    await choose_template(user, "Full system")

    assert [m for m in ("form-pv", "form-wind", "form-battery", "form-demand", "form-grid") if exists(user, m)] == [
        "form-pv"]


async def test_unticking_the_pv_system_removes_its_form_and_ticking_it_again_starts_with_the_defaults(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    user.find(marker=CAPACITY).clear().type("50")
    await settle()

    user.find(marker="component-pv").click()
    await user.should_not_see(marker="form-pv")
    user.find(marker="component-pv").click()
    await user.should_see(marker="form-pv")

    assert field(user, CAPACITY).value is None


# ---------------------------------------------------------------------------
# what is shown
# ---------------------------------------------------------------------------

async def test_the_start_is_a_fixed_size_that_is_not_filled_in_yet(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    assert field(user, MODE).value == "fixed"
    assert field(user, CAPACITY).value is None
    assert field(user, CAPACITY).props["suffix"] == "kW"
    assert not any(exists(user, marker) for marker in INVEST_MARKERS)


async def test_the_choice_is_worded_for_the_reader(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    assert field(user, MODE).options == {"fixed": "I enter a fixed size", "invest": "The optimizer chooses the size"}
    await user.should_see("How is the size decided?")


async def test_every_setting_has_its_help_text_under_it(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    await user.should_see("The installed peak power of the plant.")
    await pick_mode(user, "invest")
    await user.should_see("Used to spread the investment over its lifetime. 0 means no interest.")


async def test_the_optimizer_chooses_the_size_shows_the_investment_settings_and_hides_the_size(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    await pick_mode(user, "invest")

    assert all(exists(user, marker) for marker in INVEST_MARKERS)
    assert not exists(user, CAPACITY)
    await user.should_see("Investment")                                    # the title of the section


async def test_the_defaults_of_the_investment_settings_are_filled_in(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await pick_mode(user, "invest")

    values = {marker.removeprefix("field-pv-capacity-"): field(user, marker).value for marker in INVEST_MARKERS}

    assert values == {"maximum": None, "capex": 1200.0, "opex": 2.0, "lifetime": 25.0, "interest_rate": 3.0}


async def test_the_units_are_behind_the_numbers_and_a_percentage_is_a_percentage(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await pick_mode(user, "invest")

    suffixes = {marker: field(user, marker).props["suffix"] for marker in INVEST_MARKERS}

    assert suffixes == {
        "field-pv-capacity-maximum": "kW",
        "field-pv-capacity-capex": "€ per kW",
        "field-pv-capacity-opex": "% of the investment per year",
        "field-pv-capacity-lifetime": "years",
        "field-pv-capacity-interest_rate": "% per year",
    }
    assert field(user, "field-pv-capacity-interest_rate").props["max"] == 100


async def test_going_back_to_a_fixed_size_brings_the_size_back_with_what_was_typed(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    user.find(marker=CAPACITY).clear().type("60")
    await settle()

    await pick_mode(user, "invest")
    await pick_mode(user, "fixed")

    assert field(user, CAPACITY).value == 60


# ---------------------------------------------------------------------------
# what typing does
# ---------------------------------------------------------------------------

async def test_a_size_that_is_typed_in_answers_the_check_and_the_table(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await user.should_see("PV system: fixed mode needs a capacity")
    assert (await pv_row(user))["size"] == "not set"

    user.find(marker=CAPACITY).clear().type("50")

    await user.should_not_see("PV system: fixed mode needs a capacity")
    assert (await pv_row(user))["size"] == "50 kW"


async def test_a_maximum_is_in_the_table_and_clearing_it_means_no_limit(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await pick_mode(user, "invest")
    assert (await pv_row(user))["size"] == "no upper limit"

    user.find(marker="field-pv-capacity-maximum").clear().type("40")
    await wait_for_size(user, "up to 40 kW")

    user.find(marker="field-pv-capacity-maximum").clear()
    await wait_for_size(user, "no upper limit")


async def test_an_empty_investment_setting_is_asked_for_by_the_check(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await pick_mode(user, "invest")

    user.find(marker="field-pv-capacity-capex").clear()

    await user.should_see("PV system: invest mode needs values for capex")


@pytest.mark.parametrize("marker, text, message", [
    ("field-pv-capacity-interest_rate", "150", "Enter a number from 0 to 100."),
    ("field-pv-capacity-lifetime", "0", "Enter a number from 1 to 100."),
    ("field-pv-capacity-capex", "-5", "Enter a number of at least 0."),
])
async def test_a_number_that_does_not_fit_is_explained_at_the_field_and_not_taken_over(user: User, marker, text, message):
    await open_page(user)
    await choose_template(user, "PV system")
    await pick_mode(user, "invest")
    stored = field(user, marker).value                       # the default that was filled in

    # the wrong number replaces the old one in one go (clearing the field first would store "not filled in")
    field(user, marker).value = float(text)
    await settle()

    assert field(user, marker).error == message
    # draw the form again from what is stored: it shows the last value that fitted, not the wrong one
    await pick_mode(user, "fixed")
    await pick_mode(user, "invest")
    assert field(user, marker).value == stored and stored is not None


async def test_a_size_below_zero_does_not_change_the_table(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    user.find(marker=CAPACITY).clear().type("50")
    await wait_for_size(user, "50 kW")

    field(user, CAPACITY).value = -3.0                      # in one go: clearing the field first would empty it
    await settle()

    assert field(user, CAPACITY).error == "Enter a number of at least 0."
    assert (await pv_row(user))["size"] == "50 kW"


async def test_clearing_a_field_means_not_filled_in_and_is_stored_that_way(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    user.find(marker=CAPACITY).clear().type("50")
    await wait_for_size(user, "50 kW")

    user.find(marker=CAPACITY).clear()

    await wait_for_size(user, "not set")
    await user.should_see("PV system: fixed mode needs a capacity")


async def test_typing_in_a_number_does_not_draw_the_form_again_but_a_choice_does(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    number = field(user, CAPACITY)
    radio = field(user, MODE)

    user.find(marker=CAPACITY).clear().type("50")
    await settle()

    assert field(user, CAPACITY).id == number.id           # the same field: the cursor would stay in it
    assert field(user, MODE).id == radio.id

    field(user, MODE).value = "invest"
    await user.should_see(marker=INVEST_MARKERS[0])

    assert field(user, MODE).id != radio.id                # a choice draws the form again


async def test_the_form_of_a_component_that_stays_keeps_what_was_typed_when_the_template_changes(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    user.find(marker=CAPACITY).clear().type("50")
    await settle()

    await choose_template(user, "PV + battery")

    assert field(user, CAPACITY).value == 50


# ---------------------------------------------------------------------------
# in German
# ---------------------------------------------------------------------------

async def test_the_form_is_in_german(user: User):
    await open_page(user, "de")

    await choose_template(user, "PV system")

    await user.should_see("Einstellungen: PV-Anlage")
    await user.should_see("Wie wird die Größe festgelegt?")
    await user.should_see("Die installierte Spitzenleistung der Anlage.")
    assert field(user, MODE).options == {"fixed": "Ich gebe eine feste Größe ein", "invest": "Der Optimierer wählt die Größe"}
    assert field(user, CAPACITY).props["suffix"] == "kW"


async def test_the_investment_settings_have_german_units(user: User):
    await open_page(user, "de")
    await choose_template(user, "PV system")
    await pick_mode(user, "invest")

    suffixes = [field(user, marker).props["suffix"] for marker in INVEST_MARKERS]

    assert suffixes == ["kW", "€ pro kW", "% der Investition pro Jahr", "Jahre", "% pro Jahr"]
    await user.should_see("Investition")


async def test_a_number_that_does_not_fit_is_explained_in_german(user: User):
    await open_page(user, "de")
    await choose_template(user, "PV system")
    await pick_mode(user, "invest")

    user.find(marker="field-pv-capacity-interest_rate").clear().type("150")
    user.find(marker="field-pv-capacity-capex").clear().type("-1")
    await settle()

    assert field(user, "field-pv-capacity-interest_rate").error == "Geben Sie eine Zahl von 0 bis 100 ein."
    assert field(user, "field-pv-capacity-capex").error == "Geben Sie eine Zahl von mindestens 0 ein."


async def test_the_form_keeps_what_was_typed_and_chosen_when_the_language_changes(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    user.find(marker=CAPACITY).clear().type("50")
    await settle()

    await switched_to(user, "de")

    await user.should_see("Einstellungen: PV-Anlage")
    assert field(user, CAPACITY).value == 50
    assert field(user, MODE).value == "fixed"

    await pick_mode(user, "invest")
    user.find(marker="field-pv-capacity-maximum").clear().type("40")
    await wait_for_size(user, "bis zu 40 kW")

    await switched_to(user, "en")

    assert field(user, MODE).value == "invest"
    assert field(user, "field-pv-capacity-maximum").value == 40
    assert field(user, "field-pv-capacity-maximum").props["suffix"] == "kW"


async def test_the_table_and_the_check_follow_the_form_in_german(user: User):
    await open_page(user, "de")
    await choose_template(user, "PV system")
    await user.should_see("PV-Anlage: Der Modus 'fest' braucht eine Größe über 0")

    user.find(marker=CAPACITY).clear().type("50")

    await user.should_not_see("PV-Anlage: Der Modus 'fest' braucht eine Größe über 0")
    assert (await pv_row(user))["size"] == "50 kW"


async def test_the_page_says_which_forms_there_are_so_far(user: User):
    await open_page(user)

    await user.should_see("settings forms exist for the PV system so far")


async def test_the_unit_of_the_number_field_is_an_input_suffix_not_a_separate_text(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    assert isinstance(field(user, CAPACITY), ui.number)
    assert isinstance(field(user, MODE), ui.radio)