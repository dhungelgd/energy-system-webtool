"""The colours of the components: one for each, valid, and found by id and by the name that people read."""

import re

import pytest

from backend.plotting import NODE_NAMES
from frontend_nicegui.palette import (
    BUS_COLOR,
    BY_NAME,
    COLORS,
    DEMAND_LINE,
    GREY,
    color_of_name,
    color_of_node,
    with_alpha,
)

HEX = re.compile(r"^#[0-9A-F]{6}$")


def test_every_component_of_the_model_has_a_colour():
    assert set(COLORS) == set(NODE_NAMES)


def test_every_colour_is_a_hex_colour():
    for color in list(COLORS.values()) + [BUS_COLOR, DEMAND_LINE, GREY]:
        assert HEX.match(color), color


def test_the_components_that_share_a_chart_have_colours_that_differ():
    # the demands may share their dark colour (they are lines or nodes on different buses); the others must differ
    sources = {key: color for key, color in COLORS.items() if "demand" not in key}

    assert len(set(sources.values())) == len(sources)
    assert GREY not in sources.values() and BUS_COLOR not in sources.values()


def test_a_colour_is_found_by_the_id_of_the_component_and_by_its_name():
    assert color_of_node("pv") == COLORS["pv"] == color_of_name("PV")
    assert color_of_node("heat_pump") == color_of_name("Heat pump")
    assert color_of_name("Grid feed-in") == COLORS["grid_feedin"]


def test_every_name_of_the_backend_has_its_colour():
    assert set(BY_NAME) == set(NODE_NAMES.values())
    assert all(color_of_name(name) == COLORS[key] for key, name in NODE_NAMES.items())


@pytest.mark.parametrize("unknown", ["fusion_reactor", None, "", "Something new"])
def test_what_is_not_known_is_grey(unknown):
    assert color_of_node(unknown) == GREY and color_of_name(unknown) == GREY


def test_a_colour_can_be_made_see_through():
    assert with_alpha("#C98200", 0.35) == "rgba(201, 130, 0, 0.35)"
    assert with_alpha("#000000", 1) == "rgba(0, 0, 0, 1)"
    assert with_alpha("#FFFFFF", 0) == "rgba(255, 255, 255, 0)"