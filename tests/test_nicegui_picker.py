"""Choosing the components on the NiceGUI page (simulated user, no browser)."""

import pytest

pytest.importorskip("nicegui")
from nicegui.testing import User  # noqa: E402

from backend.component_specs import INFO  # noqa: E402
from backend.system_templates import GROUP_ORDER, SYSTEM_TEMPLATES  # noqa: E402
from frontend_nicegui.markers import slug  # noqa: E402


def box(user: User, key: str):
    return user.find(marker=f"component-{key}").elements.pop()


def ticked(user: User):
    return sorted(key for key in INFO if box(user, key).value)


async def rows(user: User):
    await user.should_see(marker="draft-components")
    return user.find(marker="draft-components").elements.pop().rows


async def names(user: User):
    return [row["component"] for row in await rows(user)]


async def choose_template(user: User, name: str):
    user.find(marker=f"template-{slug(name)}").click()
    await user.should_see(marker="selection-count")


async def test_the_page_offers_templates_and_every_component(user: User):
    await user.open("/")

    await user.should_see("Build a scenario")
    for name in SYSTEM_TEMPLATES:
        await user.should_see(marker=f"template-{slug(name)}")
    for key in INFO:
        await user.should_see(marker=f"component-{key}")
    await user.should_see(marker="clear-selection")


async def test_the_components_are_listed_by_group_with_readable_names(user: User):
    await user.open("/")

    for group in GROUP_ORDER:
        await user.should_see(group)
    await user.should_see("Electricity demand")
    await user.should_see("Battery storage")


async def test_nothing_is_selected_at_first(user: User):
    await user.open("/")

    await user.should_see("Nothing selected yet. Choose a template or tick components.")
    await user.should_not_see(marker="selection-count")
    await user.should_not_see(marker="draft-components")
    assert ticked(user) == []


async def test_a_template_selects_its_components(user: User):
    await user.open("/")

    await choose_template(user, "PV + battery")

    await user.should_see("5 components")
    assert await names(user) == [
        "Electricity demand", "Electricity grid", "Grid feed-in", "PV system", "Battery storage",
    ]
    await user.should_not_see("Nothing selected yet")
    assert ticked(user) == sorted(["demand", "grid", "grid_feedin", "pv", "battery"])


async def test_the_table_says_what_each_component_is_and_how_it_is_set(user: User):
    await user.open("/")

    await choose_template(user, "PV system")

    by_name = {row["component"]: row for row in await rows(user)}
    assert by_name["PV system"] == {"component": "PV system", "type": "PV system", "mode": "fixed", "size": "not set"}
    assert by_name["Electricity grid"]["mode"] == "-"


async def test_another_template_replaces_the_first(user: User):
    await user.open("/")
    await choose_template(user, "PV + battery")

    await choose_template(user, "Electricity only")

    await user.should_see("2 components")
    assert await names(user) == ["Electricity demand", "Electricity grid"]
    assert ticked(user) == ["demand", "grid"]


async def test_the_full_system_selects_everything(user: User):
    await user.open("/")

    await choose_template(user, "Full system")

    await user.should_see("13 components")
    assert ticked(user) == sorted(INFO)
    assert len(await rows(user)) == 13


async def test_ticking_a_box_adds_the_component(user: User):
    await user.open("/")

    user.find(marker="component-wind").click()

    await user.should_see("1 component")
    assert await names(user) == ["Wind turbine"]
    assert ticked(user) == ["wind"]


async def test_unticking_a_box_removes_the_component(user: User):
    await user.open("/")
    await choose_template(user, "PV system")

    user.find(marker="component-pv").click()

    await user.should_see("3 components")
    assert "PV system" not in await names(user)
    assert "pv" not in ticked(user)


async def test_the_rows_are_in_the_order_of_the_groups_whatever_was_ticked_first(user: User):
    await user.open("/")

    user.find(marker="component-battery").click()
    user.find(marker="component-pv").click()
    user.find(marker="component-demand").click()

    await user.should_see("3 components")
    assert await names(user) == ["Electricity demand", "PV system", "Battery storage"]


async def test_a_template_and_single_ticks_work_together(user: User):
    await user.open("/")
    await choose_template(user, "Electricity only")

    user.find(marker="component-battery").click()
    await user.should_see("3 components")

    await choose_template(user, "Gas heating")

    await user.should_see("3 components")
    assert ticked(user) == sorted(["heat_demand", "gas_import", "gas_boiler"])


async def test_clearing_the_selection(user: User):
    await user.open("/")
    await choose_template(user, "Full system")

    user.find(marker="clear-selection").click()

    await user.should_see("Nothing selected yet")
    await user.should_not_see(marker="selection-count")
    await user.should_not_see(marker="draft-components")
    assert ticked(user) == []