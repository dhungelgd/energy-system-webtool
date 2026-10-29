"""The names of components, groups and templates in the language of the reader."""

import pytest

from backend.component_specs import INFO
from backend.i18n import ENGLISH, Translator
from backend.system_templates import SYSTEM_TEMPLATES, components_by_group
from backend.templates import new_component
from frontend_nicegui.names import (
    component_label,
    component_short,
    display_name,
    group_label,
    template_label,
)

DE = Translator("de")


@pytest.mark.parametrize("key", list(INFO))
def test_in_english_every_name_is_the_one_of_the_backend(key):
    assert component_label(ENGLISH, key) == INFO[key].label
    assert component_short(ENGLISH, key) == INFO[key].short_label


def test_components_in_german():
    assert component_label(DE, "chp") == "BHKW"
    assert component_label(DE, "battery") == "Batteriespeicher"
    assert component_short(DE, "grid_feedin") == "Einspeisung"


def test_groups_and_templates_in_german():
    assert [group_label(DE, group) for group in components_by_group()] == [
        "Bedarf", "Netz & Brennstoff", "Erzeugung", "Umwandlung", "Speicher"]
    assert template_label(DE, "PV + battery") == "PV + Batterie"
    assert template_label(DE, "Full system") == "Komplettsystem"


@pytest.mark.parametrize("name", list(SYSTEM_TEMPLATES))
def test_in_english_every_template_has_its_own_name(name):
    assert template_label(ENGLISH, name) == name


def test_a_standard_name_follows_the_language():
    component = new_component("heat_pump")

    assert display_name(component, ENGLISH) == "Heat pump"
    assert display_name(component, DE) == "Wärmepumpe"


def test_a_name_that_somebody_chose_stays_as_it_is():
    component = new_component("pv", component_id="pv_east", name="PV east roof")

    assert display_name(component, DE) == "PV east roof"


def test_a_name_that_looks_like_the_standard_name_of_another_template_stays():
    component = new_component("pv", name="Heat pump")           # somebody called the PV plant that

    assert display_name(component, DE) == "Heat pump"


def test_a_custom_component_has_only_its_own_name():
    from backend.scenario_v2 import Component

    custom = Component(id="x", name="Electrolyser", template=None, kind="converter",
                       connections=[{"carrier": "electricity", "direction": "in"},
                                    {"carrier": "hydrogen", "direction": "out"}], blocks={})

    assert display_name(custom, DE) == "Electrolyser"