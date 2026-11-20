"""The areas of the tool: the list, where the page opens, and the area in the state of the page."""

import json
from pathlib import Path

import pytest

from frontend_nicegui import areas
from frontend_nicegui.areas import AREAS, START, START_ENV, Area, area_of, is_area, keys, start_area
from frontend_nicegui.page_state import PageState

CATALOGS = Path(__file__).resolve().parent.parent / "backend" / "i18n"


def test_the_start_page_comes_first_and_then_the_areas_in_the_order_of_the_list():
    assert keys() == ["start", "optimization"] and START == "start"


def test_the_start_page_and_each_area_are_places_and_nothing_else_is():
    assert all(is_area(key) for key in keys())
    assert not any(is_area(value) for value in ("", None, "Start", "optimisation", "profile", "start ", 3))


def test_an_area_is_found_by_its_key_and_the_start_page_is_not_one():
    assert area_of("optimization") is AREAS[0] and isinstance(AREAS[0], Area)
    with pytest.raises(StopIteration):
        area_of("start")


@pytest.mark.parametrize("query, environ, expected", [
    (None, {}, "start"),                                                # nothing says: the start page
    ("optimization", {}, "optimization"),                               # the address
    (None, {START_ENV: "optimization"}, "optimization"),                # the setting of the server
    ("start", {START_ENV: "optimization"}, "start"),                    # the address wins over the setting
    ("optimization", {START_ENV: "start"}, "optimization"),
    ("nonsense", {}, "start"),                                          # an old or mistyped link does not break the page
    ("nonsense", {START_ENV: "optimization"}, "optimization"),          # ... and the setting still counts
    (None, {START_ENV: "nonsense"}, "start"),
    ("", {START_ENV: ""}, "start"),
])
def test_the_page_opens_where_the_address_says_else_where_the_server_is_set_to_else_on_the_start_page(query, environ, expected):
    assert start_area(query, environ) == expected


def test_without_an_environment_given_the_real_one_is_read(monkeypatch):
    monkeypatch.delenv(START_ENV, raising=False)
    assert start_area() == "start"

    monkeypatch.setenv(START_ENV, "optimization")
    assert start_area() == "optimization" and start_area("start") == "start"


def test_the_name_of_the_setting_is_the_one_that_a_server_sets():
    assert START_ENV == "WEBTOOL_START_AREA" and areas.START_ENV == START_ENV


@pytest.mark.parametrize("language", ["en", "de"])
def test_every_text_of_an_area_is_in_the_catalog_of_each_language(language):
    catalog = json.loads((CATALOGS / f"{language}.json").read_text(encoding="utf-8"))

    for area in AREAS:
        for key in (area.label, area.title, area.text, area.button, area.resume, f"area.{START}"):
            assert key in catalog, key


def test_every_area_has_its_own_key_label_and_a_name_that_works_in_an_address():
    assert len({area.key for area in AREAS}) == len(AREAS) and len({area.label for area in AREAS}) == len(AREAS)
    assert all(area.key.isidentifier() and area.key == area.key.lower() and area.key != START for area in AREAS)
    assert all(area.icon for area in AREAS)


# ---------------------------------------------------------------------------
# the state of the page
# ---------------------------------------------------------------------------

def test_a_page_begins_on_the_start_page():
    assert PageState().area == "start"


def test_the_area_can_be_changed_to_any_place_and_to_nothing_else():
    state = PageState()

    for key in keys():
        state.area = key
        assert state.area == key

    with pytest.raises(ValueError, match="unknown area 'profile'"):
        state.area = "profile"

    assert state.area == "optimization"                                 # a refused name changes nothing


def test_changing_the_area_does_not_touch_what_was_built():
    state = PageState()
    state.draft.set("demand")
    state.draft.name = "Mine"

    state.area = "optimization"
    state.area = "start"

    assert [c.id for c in state.draft.components()] == ["demand"] and state.draft.name == "Mine"