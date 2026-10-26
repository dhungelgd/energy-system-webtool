"""The component picker of the NiceGUI interface (simulated user, no browser)."""

import pytest

pytest.importorskip("nicegui")
from nicegui import ui  # noqa: E402
from nicegui.testing import User  # noqa: E402

from frontend.ui_registry import UI_REGISTRY  # noqa: E402
from frontend_nicegui.selection import slug, template_names  # noqa: E402


def box(user: User, key: str):
    return user.find(marker=f"component-{key}").elements.pop()


def ticked(user: User):
    return sorted(key for key in UI_REGISTRY if box(user, key).value)


async def choose_template(user: User, name: str):
    user.find(marker=f"template-{slug(name)}").click()
    await user.should_see(marker="selection-count")


async def test_the_page_offers_templates_and_every_component(user: User):
    await user.open("/")

    await user.should_see("Build a scenario")
    for name in template_names():
        await user.should_see(marker=f"template-{slug(name)}")
    for key in UI_REGISTRY:
        await user.should_see(marker=f"component-{key}")
    await user.should_see(marker="clear-selection")


async def test_the_components_are_listed_by_group_with_readable_names(user: User):
    await user.open("/")

    for group in ("Demand", "Grid & fuel", "Generation", "Conversion", "Storage"):
        await user.should_see(group)
    await user.should_see("Electricity Demand")
    await user.should_see("Battery Storage")


async def test_nothing_is_selected_at_first(user: User):
    await user.open("/")

    await user.should_see("Nothing selected yet. Choose a template or tick components.")
    await user.should_not_see(marker="selection-count")
    assert ticked(user) == []


async def test_a_template_selects_its_components(user: User):
    await user.open("/")

    await choose_template(user, "PV + battery")

    await user.should_see("5 components selected")
    for key in ("demand", "grid", "grid_feedin", "pv", "battery"):
        await user.should_see(marker=f"chosen-{key}")
    await user.should_not_see(marker="chosen-wind")
    await user.should_not_see("Nothing selected yet")
    assert ticked(user) == sorted(["demand", "grid", "grid_feedin", "pv", "battery"])


async def test_another_template_replaces_the_first(user: User):
    await user.open("/")
    await choose_template(user, "PV + battery")

    await choose_template(user, "Electricity only")

    await user.should_see("2 components selected")
    await user.should_not_see(marker="chosen-pv")
    await user.should_not_see(marker="chosen-battery")
    assert ticked(user) == ["demand", "grid"]


async def test_the_full_system_selects_everything(user: User):
    await user.open("/")

    await choose_template(user, "Full system")

    await user.should_see("13 components selected")
    assert ticked(user) == sorted(UI_REGISTRY)


async def test_ticking_a_box_adds_the_component(user: User):
    await user.open("/")

    user.find(marker="component-wind").click()

    await user.should_see("1 component selected")
    await user.should_see(marker="chosen-wind")
    assert ticked(user) == ["wind"]


async def test_unticking_a_box_removes_the_component(user: User):
    await user.open("/")
    await choose_template(user, "PV system")

    user.find(marker="component-pv").click()

    await user.should_see("3 components selected")
    await user.should_not_see(marker="chosen-pv")
    assert "pv" not in ticked(user)


async def test_a_template_and_single_ticks_work_together(user: User):
    await user.open("/")
    await choose_template(user, "Electricity only")

    user.find(marker="component-battery").click()
    await user.should_see("3 components selected")

    await choose_template(user, "Gas heating")

    await user.should_see("3 components selected")
    assert ticked(user) == sorted(["heat_demand", "gas_import", "gas_boiler"])


async def test_clearing_the_selection(user: User):
    await user.open("/")
    await choose_template(user, "Full system")

    user.find(marker="clear-selection").click()

    await user.should_see("Nothing selected yet")
    await user.should_not_see(marker="selection-count")
    assert ticked(user) == []


def label_texts(user: User):
    return [element.text for element in user.find(kind=ui.label).elements]


async def test_the_summary_shows_only_the_groups_that_have_a_chosen_component(user: User):
    await user.open("/")
    # every group name appears once as the heading of its column of boxes
    assert label_texts(user).count("Storage") == 1

    await choose_template(user, "CHP system")

    texts = label_texts(user)
    for group in ("Demand", "Grid & fuel", "Conversion"):
        assert texts.count(group) == 2          # column heading and summary line
    for group in ("Generation", "Storage"):
        assert texts.count(group) == 1          # only the column heading