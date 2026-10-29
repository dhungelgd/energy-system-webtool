"""The 13 curated components as data, and their agreement with the Streamlit interface."""

import copy

import pytest

from backend.blocks import BLOCKS
from backend.component_specs import INFO
from backend.scenario_v2 import ScenarioV2
from backend.templates import CARRIER_LABELS, TEMPLATES, carriers_for, new_component
from tests.v1_support import OTHER_V1_KEYS, to_percent


def scenario_with(*components):
    carriers = [
        {"id": c, "label": c.title()} for c in ("electricity", "heat", "gas")
        if any(x.carrier == c for comp in components for x in comp.connections)
    ]
    return ScenarioV2(carriers=carriers, components=list(components))


def test_there_is_a_template_for_every_component():
    assert list(TEMPLATES) == list(INFO)


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_a_template_only_uses_blocks_its_kind_may_have(key):
    for block in TEMPLATES[key].blocks:
        assert INFO[key].role in BLOCKS[block].kinds, f"{key}: {block}"


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_a_new_component_is_valid_and_has_the_kind_and_connections_of_the_template(key):
    component = new_component(key)

    assert component.template == key and component.id == key
    assert component.kind == INFO[key].role
    assert {(c.carrier, c.direction) for c in component.connections} == {
        (c.bus, c.direction) for c in INFO[key].connections
    }
    assert scenario_with(component).component(key) == component


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_every_link_points_at_a_setting_that_exists(key):
    for link in TEMPLATES[key].links:
        assert link.block in TEMPLATES[key].blocks
        if link.block != "conversion":
            assert link.field in {f.key for f in BLOCKS[link.block].fields} | {"rated_flow"}


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_every_percentage_setting_is_a_link_with_percent(key):
    for link in TEMPLATES[key].links:
        if link.block == "storage" and link.field in ("efficiency_charge", "efficiency_discharge", "loss_rate"):
            assert link.percent
        if link.field.endswith(".efficiency"):
            assert link.percent
        if link.field in ("capex", "opex", "lifetime", "interest_rate", "capacity", "maximum", "mode"):
            assert not link.percent                 # these are not fractions in layout 1 either


def test_converters_have_the_rated_flow_the_engine_uses():
    assert {k: t.rated_flow for k, t in TEMPLATES.items() if INFO[k].role == "converter"} == {
        "gas_boiler": "heat", "heating_rod": "heat", "chp": "electricity", "heat_pump": "heat",
    }
    assert new_component("chp").blocks["capacity"]["rated_flow"] == "electricity"
    assert "rated_flow" not in new_component("pv").blocks["capacity"]


def test_a_new_component_can_have_its_own_id_and_name_and_does_not_share_defaults():
    first = new_component("pv", component_id="pv_east", name="PV east roof")
    first.blocks["capacity"]["capex"] = 1.0

    assert (first.id, first.name) == ("pv_east", "PV east roof")
    assert new_component("pv").blocks["capacity"]["capex"] == 1200.0
    assert TEMPLATES["pv"].defaults["capacity"]["capex"] == 1200.0


def test_two_new_components_of_one_template_can_live_in_one_scenario():
    two = scenario_with(new_component("pv", "pv_south"), new_component("pv", "pv_east"))

    assert two.component_ids() == ["pv_south", "pv_east"]


# ---------------------------------------------------------------------------
# in step with the Streamlit interface while both exist
# ---------------------------------------------------------------------------

def streamlit_defaults(key):
    from frontend.ui_defaults import TECH_DEFAULTS
    from frontend.ui_registry import UI_REGISTRY

    values = {}
    for field in UI_REGISTRY[key]["inputs"]:
        default = TECH_DEFAULTS.get(key, {}).get(field["key"], field.get("default"))
        if field["type"] == "selectbox" and default is None:
            default = field["options"][0]
        values[field["key"]] = default
    return values


def at_path(values, path):
    for part in path.split("."):
        values = values.get(part, {}) if isinstance(values, dict) else {}
    return values if not isinstance(values, dict) else None


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_the_defaults_are_those_of_the_streamlit_interface(key):
    shown = streamlit_defaults(key)
    template = TEMPLATES[key]

    for link in template.links:
        value = shown.get(link.v1_key)
        if value is None:
            continue
        expected = to_percent(value) if link.percent else value
        assert at_path(template.defaults.get(link.block, {}), link.field) == pytest.approx(expected), link

    if key in ("demand", "heat_demand"):
        assert template.defaults["demand"]["annual_demand"] == shown["scaling_factor"]
    if key == "heat_pump":
        assert template.defaults["conversion"]["outputs"]["heat"]["ratio"] == shown["cop_value"]


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_every_setting_of_the_streamlit_form_is_converted(key):
    # a setting that is not converted would be dropped without a word
    from frontend.ui_registry import UI_REGISTRY

    template = TEMPLATES[key]
    covered = (
        {link.v1_key for link in template.links}
        | {slot.v1_key for slot in template.slots}
        | OTHER_V1_KEYS.get(key, set())
    )
    form = {field["key"] for field in UI_REGISTRY[key]["inputs"]}

    assert form <= covered, f"{key}: not converted: {sorted(form - covered)}"


def test_the_default_mode_is_fixed_as_in_the_streamlit_interface():
    for key in ("pv", "wind", "battery", "heat_storage", "gas_boiler", "heating_rod", "chp", "heat_pump"):
        assert copy.deepcopy(TEMPLATES[key].defaults["capacity"])["mode"] == "fixed"


# ---------------------------------------------------------------------------
# the carriers of a set of components
# ---------------------------------------------------------------------------

def carrier_ids(*keys):
    return [carrier["id"] for carrier in carriers_for([new_component(key) for key in keys])]


def test_the_carriers_follow_the_components():
    assert carrier_ids("demand", "grid") == ["electricity"]
    assert carrier_ids("heat_demand", "gas_import", "gas_boiler") == ["heat", "gas"]


def test_the_carriers_come_in_the_usual_order_whatever_order_the_components_come_in():
    assert carrier_ids("gas_boiler", "heat_demand", "demand") == ["electricity", "heat", "gas"]
    assert carrier_ids("demand", "heat_demand", "gas_boiler") == ["electricity", "heat", "gas"]


def test_a_carrier_that_nothing_uses_is_left_out_and_nothing_gives_no_carrier():
    assert "gas" not in carrier_ids("demand", "heat_demand", "heat_pump")
    assert carriers_for([]) == []


def test_the_carriers_have_readable_labels():
    assert carriers_for([new_component("gas_boiler")]) == [
        {"id": "heat", "label": "Heat"}, {"id": "gas", "label": "Gas"}]
    assert set(CARRIER_LABELS) == {"electricity", "heat", "gas"}