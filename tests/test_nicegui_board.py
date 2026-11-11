"""The board and the drawer on the NiceGUI page: tiles, what they say, adding, opening, removing (simulated user)."""

import pytest

pytest.importorskip("nicegui")
from nicegui import ui  # noqa: E402
from nicegui.testing import User  # noqa: E402

from tests.test_nicegui_draft_run import (  # noqa: E402
    PRICE,
    build_draft,
    build_pv_draft,
    exists,
    field,
    give_demand,
    settle,
    switched_to,
)
from tests.test_nicegui_frame import views  # noqa: E402


def drawer(user):
    """The component that is open in the drawer ('none' when none is)."""

    return field(user, "drawer").value


def sheet(user):
    """The side sheet on the right (its value says whether it is open)."""

    return field(user, "drawer-sheet")


def tile_texts(user, key):
    """All the texts on a tile, in order."""

    with user.client:
        return [e.text for e in field(user, f"tile-{key}").descendants() if isinstance(e, ui.label)]


def tile_state(user, key):
    return field(user, f"tile-{key}").props["data-state"]


async def start(user: User, template="electricity-only", language=None):
    """Open the page and choose a template, for one day (so that a series of 24 values is the right length)."""

    await user.open("/" if language is None else f"/?lang={language}")
    user.find(marker=f"template-{template}").click()
    await user.should_see(marker="selection-count")
    user.find(marker="draft-steps").clear().type("24")
    await settle()


# ---------------------------------------------------------------------------
# the board
# ---------------------------------------------------------------------------

async def test_the_board_has_three_lanes_and_the_words_above_the_columns(user: User):
    await user.open("/")

    for lane in ("electricity", "heat", "gas"):
        assert exists(user, f"lane-{lane}")
    await user.should_see("Your system")
    for word in ("Supply", "Conversion", "Storage", "Demand and export"):
        await user.should_see(word)


async def test_a_template_puts_a_tile_on_the_board_for_each_component_and_nowhere_else(user: User):
    await start(user, "electricity-only")

    assert exists(user, "tile-demand") and exists(user, "tile-grid")
    assert not exists(user, "tile-pv") and not exists(user, "tile-heat_pump")


async def test_a_tile_says_the_name_and_the_main_setting_of_its_component(user: User):
    await start(user, "electricity-only")

    assert tile_texts(user, "grid") == ["Electricity grid", "Price 0.3 EUR/kWh"]
    assert tile_texts(user, "demand")[:2] == ["Electricity demand", "30,000 kWh per year"]


async def test_each_tile_is_in_the_lane_of_its_carrier(user: User):
    await start(user, "full-system")

    for lane, keys in (("electricity", ("grid", "pv", "battery", "demand", "grid_feedin")),
                       ("heat", ("heat_pump", "chp", "heat_storage", "heat_demand")), ("gas", ("gas_import",))):
        lane_element = field(user, f"lane-{lane}")
        for key in keys:
            assert field(user, f"tile-{key}") in list(lane_element.descendants()), (lane, key)


async def test_the_board_is_in_german(user: User):
    await start(user, "electricity-only", language="de")

    await user.should_see("Ihr System")
    await user.should_see("Quellen")
    assert tile_texts(user, "grid") == ["Stromnetz", "Preis 0,3 €/kWh"]
    assert tile_texts(user, "demand")[:2] == ["Strombedarf", "30.000 kWh pro Jahr"]


# ---------------------------------------------------------------------------
# what a tile says about its problems
# ---------------------------------------------------------------------------

async def test_a_tile_says_when_its_component_has_a_problem_and_when_it_is_in_order(user: User):
    await start(user, "electricity-only")                                 # the demand has no data
    assert tile_state(user, "demand") == "error" and tile_state(user, "grid") == "ok"
    assert "1 error" in tile_texts(user, "demand")

    await give_demand(user)

    assert tile_state(user, "demand") == "ok" and "1 error" not in tile_texts(user, "demand")


async def test_the_tile_follows_what_is_typed_in_the_drawer(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()

    user.find(marker=PRICE).clear().type("0.35")
    await settle()

    assert tile_texts(user, "grid")[1] == "Price 0.35 EUR/kWh"


async def test_typing_in_the_drawer_does_not_draw_the_field_again(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()
    typed_into = field(user, PRICE)

    user.find(marker=PRICE).clear().type("0.35")
    await settle()

    assert field(user, PRICE) is typed_into                               # the cursor stays where it is


async def test_a_tile_with_a_warning_is_marked_as_one(user: User):
    await build_pv_draft(user)
    user.find(marker="field-pv-capacity-maximum").clear().type("50")
    await settle()

    assert tile_state(user, "pv") == "warning" and "1 warning" in tile_texts(user, "pv")


# ---------------------------------------------------------------------------
# the drawer
# ---------------------------------------------------------------------------

async def test_a_template_leaves_the_side_sheet_closed_and_the_board_shows_what_is_missing(user: User):
    await start(user, "electricity-only")

    assert drawer(user) == "none" and not sheet(user).value
    assert tile_state(user, "demand") == "error"                          # the tile says that the demand needs data


async def test_the_side_sheet_is_closed_before_anything_is_open(user: User):
    await user.open("/")

    assert drawer(user) == "none" and exists(user, "drawer-empty") and not sheet(user).value


async def test_a_click_on_a_tile_opens_its_component_in_the_drawer(user: User):
    await start(user, "electricity-only")

    user.find(marker="tile-grid").click()

    assert drawer(user) == "grid"
    user.find(marker="tile-demand").click()
    assert drawer(user) == "demand"


async def test_the_open_tile_is_marked_and_the_others_are_not(user: User):
    await start(user, "electricity-only")
    assert not field(user, "tile-demand").style.get("outline") and not field(user, "tile-grid").style.get("outline")

    user.find(marker="tile-grid").click()
    await settle()                                                         # the board is drawn again a moment later
    assert field(user, "tile-grid").style.get("outline") and not field(user, "tile-demand").style.get("outline")

    user.find(marker="tile-demand").click()
    await settle()
    assert field(user, "tile-demand").style.get("outline") and not field(user, "tile-grid").style.get("outline")


async def test_the_close_button_closes_the_side_sheet_and_empties_the_drawer(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-demand").click()
    assert drawer(user) == "demand" and sheet(user).value

    user.find(marker="drawer-close").click()
    await settle()

    assert drawer(user) == "none" and not sheet(user).value
    assert not field(user, "tile-demand").style.get("outline")             # and no tile is marked any more


async def test_every_component_has_its_own_form_in_the_drawer(user: User):
    await start(user, "electricity-only")

    assert exists(user, "form-demand") and exists(user, "form-grid")
    assert exists(user, "drawer-demand") and exists(user, "drawer-grid")


async def test_the_drawer_tells_what_the_check_says_about_the_component(user: User):
    await start(user, "electricity-only")

    assert exists(user, "problems-demand") and not exists(user, "problems-grid")
    await user.should_see("What the check says")

    await give_demand(user)

    assert not exists(user, "problems-demand")


# ---------------------------------------------------------------------------
# adding and removing
# ---------------------------------------------------------------------------

async def test_a_place_that_has_room_has_an_add_button_and_one_that_is_full_has_not(user: User):
    await start(user, "electricity-only")

    assert exists(user, "add-electricity-supply") and exists(user, "add-electricity-storage")
    assert exists(user, "add-gas-supply") and exists(user, "add-heat-conversion")
    assert not exists(user, "add-gas-storage") and not exists(user, "add-heat-supply")      # nothing fits there

    await start(user, "full-system")

    assert not exists(user, "add-gas-supply")                              # the only gas component is there already


async def test_adding_a_component_puts_a_tile_on_the_board_and_opens_it(user: User):
    await start(user, "electricity-only")

    user.find(marker="add-wind").click()
    await settle()

    assert exists(user, "tile-wind") and drawer(user) == "wind"
    assert field(user, "component-wind").value is True                     # the list of all components follows


async def test_a_component_that_was_added_cannot_be_added_again(user: User):
    await start(user, "electricity-only")
    user.find(marker="add-wind").click()
    await settle()

    assert not exists(user, "add-wind") and exists(user, "add-pv")


async def test_removing_the_open_component_takes_its_tile_away_and_closes_the_drawer(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()

    user.find(marker="drawer-remove-grid").click()
    await settle()

    assert not exists(user, "tile-grid") and not exists(user, "form-grid")
    assert drawer(user) == "none" and field(user, "component-grid").value is False
    assert exists(user, "add-electricity-supply") and exists(user, "add-grid")        # it can be added again


async def test_the_list_of_all_components_still_works_and_keeps_the_board_in_step(user: User):
    await start(user, "electricity-only")

    user.find(marker="component-battery").click()
    await settle()

    assert exists(user, "tile-battery")
    user.find(marker="component-battery").click()
    await settle()
    assert not exists(user, "tile-battery")


async def test_unticking_the_open_component_in_the_list_closes_the_drawer(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()
    assert drawer(user) == "grid"

    user.find(marker="component-grid").click()
    await settle()

    assert not exists(user, "tile-grid") and drawer(user) == "none"


async def test_clearing_the_selection_empties_the_board_and_the_drawer(user: User):
    await start(user, "electricity-only")

    user.find(marker="clear-selection").click()
    await settle()

    assert not exists(user, "tile-demand") and drawer(user) == "none"


async def test_choosing_a_template_closes_the_component_that_was_open(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()
    assert sheet(user).value

    user.find(marker="template-gas-heating").click()
    await settle()

    assert drawer(user) == "none" and not sheet(user).value


# ---------------------------------------------------------------------------
# from the check to the component
# ---------------------------------------------------------------------------

async def test_a_finding_about_a_component_has_a_button_that_opens_it_and_shows_the_system_view(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()                                 # another component is open ...
    views(user).set_value("check")                                        # ... and the check is shown
    assert drawer(user) == "grid" and views(user).value == "check"

    user.find(marker="goto-0-demand").click()

    assert drawer(user) == "demand" and views(user).value == "system"


async def test_the_button_names_the_component_in_both_languages(user: User):
    await start(user, "electricity-only")
    assert field(user, "goto-0-demand").text == "Show Electricity demand"

    await switched_to(user, "de")

    assert field(user, "goto-0-demand").text == "Strombedarf anzeigen"


# ---------------------------------------------------------------------------
# language and views
# ---------------------------------------------------------------------------

async def test_the_open_component_stays_open_when_the_language_changes(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()

    await switched_to(user, "de")

    assert drawer(user) == "grid" and tile_texts(user, "grid")[0] == "Stromnetz"


async def test_a_change_of_view_does_not_close_the_drawer(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()

    views(user).set_value("results")
    views(user).set_value("system")
    await settle()

    assert drawer(user) == "grid"


async def test_the_board_follows_a_change_in_a_file_that_is_taken_away(user: User):
    await build_draft(user)
    assert tile_state(user, "demand") == "ok"

    user.find(marker="series-remove-demand").click()
    await settle()

    assert tile_state(user, "demand") == "error"


# ---------------------------------------------------------------------------
# the side sheet
# ---------------------------------------------------------------------------

async def test_a_click_on_a_tile_opens_the_side_sheet(user: User):
    await start(user, "electricity-only")
    assert not sheet(user).value

    user.find(marker="tile-grid").click()

    assert sheet(user).value and drawer(user) == "grid"


async def test_adding_a_component_opens_the_side_sheet(user: User):
    await start(user, "electricity-only")

    user.find(marker="add-wind").click()
    await settle()

    assert sheet(user).value and drawer(user) == "wind"


async def test_removing_the_open_component_closes_the_side_sheet(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()

    user.find(marker="drawer-remove-grid").click()
    await settle()

    assert not sheet(user).value


async def test_unticking_the_open_component_in_the_list_closes_the_side_sheet(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()

    user.find(marker="component-grid").click()
    await settle()

    assert not sheet(user).value


async def test_a_finding_button_opens_the_side_sheet(user: User):
    await start(user, "electricity-only")
    views(user).set_value("check")

    user.find(marker="goto-0-demand").click()

    assert sheet(user).value and drawer(user) == "demand"


async def test_the_side_sheet_stays_open_when_the_language_changes(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()

    await switched_to(user, "de")

    assert sheet(user).value and drawer(user) == "grid"


async def test_the_forms_in_the_side_sheet_follow_the_language(user: User):
    await start(user, "electricity-only")

    def heading():
        with user.client:
            return [e.text for e in field(user, "form-grid").descendants() if isinstance(e, ui.label)][0]

    assert "Electricity grid" in heading()

    await switched_to(user, "de")

    assert "Stromnetz" in heading() and "Electricity grid" not in heading()


async def test_a_sheet_that_is_closed_from_outside_leaves_no_tile_marked(user: User):
    await start(user, "electricity-only")
    user.find(marker="tile-grid").click()
    await settle()
    assert field(user, "tile-grid").style.get("outline")

    sheet(user).set_value(False)                      # what a click outside the sheet does on a small screen
    await settle()

    assert drawer(user) == "none" and not field(user, "tile-grid").style.get("outline")


# ---------------------------------------------------------------------------
# the columns: demand first
# ---------------------------------------------------------------------------

async def test_the_columns_are_demand_supply_conversion_storage_in_that_order(user: User):
    await user.open("/")

    with user.client:
        order = [e.text for e in (field(user, f"column-{c}") for c in ("demand", "supply", "conversion", "storage"))]
        positions = [list(user.client.layout.descendants()).index(field(user, f"column-{c}"))
                     for c in ("demand", "supply", "conversion", "storage")]

    assert order == ["Demand and export", "Supply", "Conversion", "Storage"] and positions == sorted(positions)


async def test_in_a_lane_the_demand_tiles_come_before_the_supply_tiles(user: User):
    await start(user, "electricity-only")

    with user.client:
        tiles = list(field(user, "lane-electricity").descendants())

    assert tiles.index(field(user, "tile-demand")) < tiles.index(field(user, "tile-grid"))