"""Which components are chosen (no NiceGUI needed)."""

import pytest

from backend.scenario import COMPONENTS, Scenario
from frontend.ui_registry import GROUP_ORDER, UI_REGISTRY
from frontend.ui_templates import TEMPLATES
from frontend_nicegui.selection import (
    ComponentSelection,
    components_by_group,
    slug,
    template_names,
)


def test_nothing_is_chosen_at_first():
    selection = ComponentSelection()

    assert len(selection) == 0
    assert selection.components() == []
    assert selection.selected_by_group() == []


def test_components_can_be_chosen_and_removed():
    selection = ComponentSelection()

    selection.set("pv", True)
    selection.set("grid", True)
    assert selection.is_selected("pv") and len(selection) == 2

    selection.set("pv", False)
    assert not selection.is_selected("pv") and len(selection) == 1


def test_choosing_twice_or_removing_something_not_chosen_does_no_harm():
    selection = ComponentSelection(["pv", "pv"])
    selection.set("wind", False)

    assert selection.components() == ["pv"]


def test_an_unknown_component_is_refused():
    with pytest.raises(KeyError, match="unknown component 'fusion'"):
        ComponentSelection().set("fusion")

    with pytest.raises(KeyError):
        ComponentSelection(["demand", "fusion"])


def test_the_order_is_by_group_whatever_order_they_were_chosen_in():
    selection = ComponentSelection(["battery", "chp", "pv", "grid", "heat_demand", "demand"])

    assert selection.components() == ["demand", "heat_demand", "grid", "pv", "chp", "battery"]


def test_the_groups_and_their_components():
    groups = components_by_group()

    assert list(groups) == GROUP_ORDER
    assert groups["Demand"] == ["demand", "heat_demand"]
    assert groups["Storage"] == ["battery", "heat_storage"]


def test_every_component_is_in_exactly_one_group():
    listed = [key for keys in components_by_group().values() for key in keys]

    assert sorted(listed) == sorted(UI_REGISTRY)
    assert len(listed) == len(set(listed))


def test_the_summary_has_keys_and_readable_names_and_skips_empty_groups():
    selection = ComponentSelection(["demand", "grid", "battery"])

    assert selection.selected_by_group() == [
        ("Demand", [("demand", "Electricity Demand")]),
        ("Grid & fuel", [("grid", "Electricity Grid")]),
        ("Storage", [("battery", "Battery Storage")]),
    ]


def test_a_template_chooses_exactly_its_components():
    selection = ComponentSelection(["wind", "chp"])

    selection.apply_template("PV + battery")

    assert selection.components() == ["demand", "grid", "grid_feedin", "pv", "battery"]


def test_an_unknown_template_is_refused_and_changes_nothing():
    selection = ComponentSelection(["pv"])

    with pytest.raises(KeyError, match="unknown template"):
        selection.apply_template("Fusion plant")

    assert selection.components() == ["pv"]


def test_clearing():
    selection = ComponentSelection(["pv", "grid"])

    selection.clear()

    assert selection.components() == []


def test_the_template_names():
    assert template_names() == list(TEMPLATES)
    assert "Full system" in template_names()


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_every_template_gives_a_valid_scenario_in_the_same_order_as_streamlit(name):
    selection = ComponentSelection()
    selection.apply_template(name)

    assert Scenario(components=selection.components()).components == selection.components()
    assert set(selection.components()) == set(TEMPLATES[name])


def test_every_component_of_the_interface_is_known_to_the_model():
    assert set(UI_REGISTRY) <= set(COMPONENTS)


def test_the_groups_are_the_same_as_in_the_streamlit_interface():
    pytest.importorskip("streamlit")
    from frontend.ui_selection import components_by_group as streamlit_groups

    assert components_by_group() == streamlit_groups()


@pytest.mark.parametrize("text, expected", [
    ("Electricity only", "electricity-only"),
    ("PV + battery", "pv-battery"),
    ("Heat pump + heating rod", "heat-pump-heating-rod"),
    ("  Full system  ", "full-system"),
])
def test_names_become_markers(text, expected):
    assert slug(text) == expected