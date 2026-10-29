"""System templates and the groups of the components."""

import pytest

from backend.component_specs import INFO
from backend.scenario_v2 import ScenarioV2
from backend.system_templates import GROUP_ORDER, SYSTEM_TEMPLATES, components_by_group, in_order
from backend.templates import carriers_for, new_component


def test_the_names_of_the_templates():
    assert list(SYSTEM_TEMPLATES) == [
        "Electricity only", "PV system", "PV + battery", "PV + wind", "Gas heating",
        "Heat pump + PV", "Heat pump + heating rod", "CHP system", "Full system",
    ]


@pytest.mark.parametrize("name", list(SYSTEM_TEMPLATES))
def test_a_template_only_has_known_components_and_each_only_once(name):
    keys = SYSTEM_TEMPLATES[name]

    assert set(keys) <= set(INFO)
    assert len(keys) == len(set(keys))


def test_the_full_system_has_every_component():
    assert set(SYSTEM_TEMPLATES["Full system"]) == set(INFO)


@pytest.mark.parametrize("name", list(SYSTEM_TEMPLATES))
def test_every_template_makes_a_valid_scenario(name):
    components = [new_component(key) for key in in_order(SYSTEM_TEMPLATES[name])]

    scenario = ScenarioV2(carriers=carriers_for(components), components=components)

    assert scenario.component_ids() == in_order(SYSTEM_TEMPLATES[name])


# ---------------------------------------------------------------------------
# groups and order
# ---------------------------------------------------------------------------

def test_the_groups_and_their_components():
    assert components_by_group() == {
        "Demand": ["demand", "heat_demand"],
        "Grid & fuel": ["grid", "grid_feedin", "gas_import"],
        "Generation": ["pv", "wind"],
        "Conversion": ["gas_boiler", "heating_rod", "chp", "heat_pump"],
        "Storage": ["battery", "heat_storage"],
    }


def test_every_component_is_in_exactly_one_group_and_every_group_is_known():
    listed = [key for keys in components_by_group().values() for key in keys]

    assert sorted(listed) == sorted(INFO)
    assert {info.group for info in INFO.values()} <= set(GROUP_ORDER)


def test_the_order_is_by_group_whatever_order_the_components_come_in():
    assert in_order(["battery", "pv", "demand", "grid"]) == ["demand", "grid", "pv", "battery"]
    assert in_order(["demand", "grid", "pv", "battery"]) == ["demand", "grid", "pv", "battery"]


def test_the_order_follows_the_order_of_the_groups_and_not_the_order_of_the_table(monkeypatch):
    # today both orders happen to be the same, so this changes the order of the groups
    from backend import system_templates

    monkeypatch.setattr(system_templates, "GROUP_ORDER", tuple(reversed(GROUP_ORDER)))

    assert list(system_templates.components_by_group()) == list(reversed(GROUP_ORDER))
    assert system_templates.in_order(["demand", "pv", "battery"]) == ["battery", "pv", "demand"]


def test_ordering_ignores_repeats_and_unknown_keys_and_handles_nothing():
    assert in_order(["pv", "pv", "ufo"]) == ["pv"]
    assert in_order([]) == []


# ---------------------------------------------------------------------------
# in step with the Streamlit interface while both exist
# ---------------------------------------------------------------------------

def test_the_templates_are_those_of_the_streamlit_interface():
    from frontend.ui_templates import TEMPLATES

    assert {name: list(keys) for name, keys in SYSTEM_TEMPLATES.items()} == TEMPLATES
    assert list(SYSTEM_TEMPLATES) == list(TEMPLATES)


def test_the_groups_are_those_of_the_streamlit_interface():
    from frontend.ui_registry import GROUP_ORDER as STREAMLIT_ORDER
    from frontend.ui_registry import UI_REGISTRY

    assert list(GROUP_ORDER) == STREAMLIT_ORDER

    streamlit = {name: [] for name in STREAMLIT_ORDER}
    for key, spec in UI_REGISTRY.items():
        streamlit[spec["group"]].append(key)

    assert components_by_group() == {name: keys for name, keys in streamlit.items() if keys}


def test_every_template_gives_the_same_order_of_components_as_streamlit():
    from frontend.ui_registry import GROUP_ORDER as STREAMLIT_ORDER
    from frontend.ui_registry import UI_REGISTRY
    from frontend.ui_templates import TEMPLATES

    def streamlit_order(keys):
        return [k for group in STREAMLIT_ORDER for k, spec in UI_REGISTRY.items()
                if spec["group"] == group and k in keys]

    for name, keys in TEMPLATES.items():
        assert in_order(keys) == streamlit_order(keys), name