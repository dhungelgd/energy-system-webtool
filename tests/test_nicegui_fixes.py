"""The repair buttons of the check on the NiceGUI page (simulated user, no browser)."""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("nicegui")
from nicegui import ElementFilter, ui  # noqa: E402
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402

from backend.i18n import catalog  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"


def field(user: User, marker: str):
    return user.find(marker=marker).elements.pop()


def exists(user: User, marker: str):
    with user.client:
        return bool(list(ElementFilter(marker=marker)))


def buttons(user: User):
    """The texts of the repair buttons that are on the page now, in the order of the findings."""

    found = []
    with user.client:
        for finding in range(30):
            for option in range(6):
                found += [element.text for element in ElementFilter(kind=ui.button, marker=f"fix-{finding}-{option}")]
    return found


async def settle():
    await asyncio.sleep(0.3)


async def start_with(user: User, *keys, language=None):
    """Open the page and tick the components one by one."""

    await user.open("/" if language is None else f"/?lang={language}")
    for key in keys:
        user.find(marker=f"component-{key}").click()
    await settle()
    await user.should_see(marker="selection-count")


async def press(user: User, text: str):
    user.find(kind=ui.button, content=text).click()
    await settle()


async def switched_to(user: User, language: str):
    field(user, "language").value = language
    await user.should_see(marker="app-title", content=catalog(language)["app.title"])


# ---------------------------------------------------------------------------
# a finding with a repair has a button, and the button repairs
# ---------------------------------------------------------------------------

async def test_a_finding_with_a_repair_has_a_button_that_repairs_it(user: User):
    await start_with(user, "demand")                                  # a demand and nothing that supplies it
    assert "Add Electricity grid" in buttons(user)
    assert field(user, "component-grid").value is False and not exists(user, "form-grid")

    await press(user, "Add Electricity grid")

    assert field(user, "component-grid").value is True               # the box of the builder follows
    await user.should_see(marker="form-grid")                          # and the component has its form
    assert "Add Electricity grid" not in buttons(user)                # the finding is solved: the button is gone


async def test_a_finding_with_several_repairs_has_a_button_for_each(user: User):
    await start_with(user, "pv")                                       # no demand at all

    assert buttons(user)[:2] == ["Add Electricity demand", "Add Heat demand"]

    await press(user, "Add Heat demand")

    assert field(user, "component-heat_demand").value is True and not field(user, "component-demand").value
    assert "Add Electricity demand" not in buttons(user)


async def test_a_repair_with_several_components_adds_them_all(user: User):
    await start_with(user, "grid_feedin")                              # fed in, but nothing produces electricity
    assert "Add CHP plant + Gas import + Heat demand" in buttons(user)

    await press(user, "Add CHP plant + Gas import + Heat demand")

    for key in ("chp", "gas_import", "heat_demand"):
        assert field(user, f"component-{key}").value is True
        assert exists(user, f"form-{key}")
    assert "Add CHP plant + Gas import + Heat demand" not in buttons(user)


async def test_a_warning_has_buttons_too(user: User):
    await start_with(user, "demand", "grid", "pv")                    # the surplus of the PV system cannot go anywhere

    assert "Add Grid feed-in" in buttons(user)

    await press(user, "Add Grid feed-in")

    assert field(user, "component-grid_feedin").value is True and "Add Grid feed-in" not in buttons(user)


async def test_the_repairs_can_be_followed_one_after_the_other_until_nothing_is_proposed_any_more(user: User):
    await start_with(user, "pv")                                       # a PV system and nothing else

    await press(user, "Add Electricity demand")
    assert "Add Electricity grid" in buttons(user)                    # the demand needs more than the sun

    await press(user, "Add Electricity grid")
    assert "Add Grid feed-in" in buttons(user)                        # and the surplus has to go somewhere

    await press(user, "Add Grid feed-in")

    assert buttons(user) == [] and not exists(user, "fix-note")       # what is left needs data, not components

# ---------------------------------------------------------------------------
# where the check is on the page
# ---------------------------------------------------------------------------

def position(user: User, marker: str):
    """Where an element is on the page, counted from the top (the order in which it is drawn)."""

    return list(user.client.content.descendants()).index(field(user, marker))


async def test_the_views_come_in_the_order_system_check_results_and_a_repair_adds_a_tile_to_the_board(user: User):
    await start_with(user, "demand", "pv")

    # the system view: the builder, then the board, and the file to open at the end ...
    assert position(user, "component-pv") < position(user, "lane-electricity") < position(user, "upload")
    # ... then the check, then the results
    assert position(user, "upload") < position(user, "draft-findings") < position(user, "draft-results-empty")
    assert not exists(user, "tile-grid")

    await press(user, "Add Electricity grid")

    assert exists(user, "tile-grid") and exists(user, "form-grid")          # a tile on the board, a form in the side sheet

# ---------------------------------------------------------------------------
# what a repair leaves alone
# ---------------------------------------------------------------------------

async def test_what_was_typed_stays_when_a_repair_adds_components(user: User):
    await start_with(user, "demand", "pv")
    user.find(marker="field-pv-capacity-capacity").clear().type("7")
    await settle()

    await press(user, "Add Electricity grid")

    assert field(user, "field-pv-capacity-capacity").value == 7


async def test_a_time_series_that_was_used_stays_when_a_repair_adds_components(user: User):
    await start_with(user, "demand")
    rows = ["Zeit;Last"] + [f"2021-01-01 {h:02d}:00;{1 + h / 10}" for h in range(24)]
    content = ("\n".join(rows) + "\n").encode()
    await field(user, "series-upload-demand").handle_uploads([SmallFileUpload("last.csv", "text/csv", content)])
    await user.should_see(marker="series-prepare-demand")
    user.find(marker="series-use-demand").click()
    await user.should_see(marker="series-summary-demand")

    await press(user, "Add Electricity grid")

    assert exists(user, "series-summary-demand")


# ---------------------------------------------------------------------------
# the note under the findings
# ---------------------------------------------------------------------------

async def test_the_note_says_what_a_button_does_and_is_only_there_when_there_is_one(user: User):
    await start_with(user, "demand")
    await user.should_see("A button adds the missing components with their standard settings.")

    await press(user, "Add Electricity grid")

    assert not exists(user, "fix-note")


# ---------------------------------------------------------------------------
# a scenario that was opened from a file cannot be changed
# ---------------------------------------------------------------------------

async def test_the_findings_of_an_opened_file_have_no_buttons(user: User):
    await user.open("/")
    content = (EXAMPLES / "with_problems.json").read_bytes()
    await field(user, "upload").handle_uploads([SmallFileUpload("with_problems.json", "application/json", content)])
    await user.should_see(marker="scenario-name")

    await user.should_see(marker="findings")                          # the warning that proposes a repair is there ...
    assert buttons(user) == [] and not exists(user, "fix-note")         # ... without a button


# ---------------------------------------------------------------------------
# in German
# ---------------------------------------------------------------------------

async def test_the_buttons_are_in_german(user: User):
    await start_with(user, "demand", language="de")

    assert "Stromnetz hinzufügen" in buttons(user)
    await user.should_see("Ein Knopf fügt die fehlenden Bauteile mit ihren Standardeinstellungen hinzu.")

    await press(user, "Stromnetz hinzufügen")

    assert field(user, "component-grid").value is True


async def test_a_repair_with_several_components_in_german(user: User):
    await start_with(user, "grid_feedin", language="de")

    assert "BHKW + Gasbezug + Wärmebedarf hinzufügen" in buttons(user)


async def test_the_buttons_follow_a_change_of_the_language(user: User):
    await start_with(user, "demand")
    assert "Add Electricity grid" in buttons(user)

    await switched_to(user, "de")

    assert "Stromnetz hinzufügen" in buttons(user) and "Add Electricity grid" not in buttons(user)
    await press(user, "Stromnetz hinzufügen")
    assert field(user, "component-grid").value is True