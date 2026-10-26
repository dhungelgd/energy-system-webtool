"""Roles and connections of all 13 components, checked against the model itself."""

import itertools

import pytest
from pydantic import ValidationError

from backend.component_specs import (
    BUSES,
    INFO,
    PV,
    ComponentInfo,
    Connection,
    bus_balance,
    get_info,
)
from backend.config_builder import build_config
from backend.model_builder import build_model
from backend.scenario import Scenario
from backend.system_check import check_system

# ---------------------------------------------------------------------------
# what we expect, written down by hand (an independent statement of the data)
# ---------------------------------------------------------------------------

EXPECTED = {
    "demand": ("sink", {("electricity", "in")}),
    "heat_demand": ("sink", {("heat", "in")}),
    "grid": ("source", {("electricity", "out")}),
    "grid_feedin": ("sink", {("electricity", "in")}),
    "gas_import": ("source", {("gas", "out")}),
    "pv": ("source", {("electricity", "out")}),
    "wind": ("source", {("electricity", "out")}),
    "gas_boiler": ("converter", {("gas", "in"), ("heat", "out")}),
    "heating_rod": ("converter", {("electricity", "in"), ("heat", "out")}),
    "chp": ("converter", {("gas", "in"), ("electricity", "out"), ("heat", "out")}),
    "heat_pump": ("converter", {("electricity", "in"), ("heat", "out")}),
    "battery": ("storage", {("electricity", "both")}),
    "heat_storage": ("storage", {("heat", "both")}),
}


def pairs(info):
    return {(c.bus, c.direction) for c in info.connections}


@pytest.mark.parametrize("key", list(EXPECTED))
def test_role_and_connections_are_as_written_down(key):
    role, connections = EXPECTED[key]

    assert INFO[key].role == role
    assert pairs(INFO[key]) == connections


def test_there_are_exactly_thirteen_components():
    assert list(INFO) == list(EXPECTED) or set(INFO) == set(EXPECTED)
    assert len(INFO) == 13


def test_the_roles_are_distributed_as_expected():
    roles = [info.role for info in INFO.values()]

    assert {role: roles.count(role) for role in set(roles)} == {
        "source": 4, "sink": 3, "converter": 4, "storage": 2,
    }


def test_every_connection_uses_a_known_bus():
    used = {c.bus for info in INFO.values() for c in info.connections}

    assert used == set(BUSES)


# ---------------------------------------------------------------------------
# the model itself: what is each component connected to in oemof?
# ---------------------------------------------------------------------------

STEPS = 4
SETTINGS = {
    "demand": ({"scaling_factor": 1.0}, {"electricity_demand": [1.0] * STEPS}),
    "heat_demand": ({"scaling_factor": 1.0}, {"heat_demand": [1.0] * STEPS}),
    "grid": ({"price_mode": "constant", "variable_costs": 0.3}, {}),
    "grid_feedin": ({"feedin_tariff": 0.05}, {}),
    "gas_import": ({"variable_costs": 0.1}, {}),
    "pv": ({"mode": "fixed", "capacity": 1.0}, {"pv": [0.5] * STEPS}),
    "wind": ({"mode": "fixed", "capacity": 1.0}, {"wind": [0.5] * STEPS}),
    "gas_boiler": ({"mode": "fixed", "capacity": 10.0, "efficiency": 0.9}, {}),
    "heating_rod": ({"mode": "fixed", "capacity": 10.0, "efficiency": 1.0}, {}),
    "chp": ({"mode": "fixed", "capacity": 10.0, "efficiency_el": 0.35, "efficiency_th": 0.5}, {}),
    "heat_pump": ({"mode": "fixed", "capacity": 10.0, "cop_mode": "constant", "cop_value": 3.0}, {}),
    "battery": ({"mode": "fixed", "capacity": 10.0, "c_rate": 0.5, "efficiency_charge": 1.0,
                 "efficiency_discharge": 1.0, "loss_rate": 0.0}, {}),
    "heat_storage": ({"mode": "fixed", "capacity": 10.0, "c_rate": 0.5, "efficiency_charge": 1.0,
                      "efficiency_discharge": 1.0, "loss_rate": 0.0}, {}),
}


def model_connections(key):
    """(buses it takes from, buses it gives to) of the component, read from oemof."""

    from oemof.solph import Bus

    settings, series = SETTINGS[key]
    scenario = Scenario(components=[key], settings={key: settings}, time={"steps": STEPS}, series=series)
    selected, tech_inputs, input_data, solver = scenario.to_inputs()
    energy_system = build_model(build_config(selected, tech_inputs, input_data, solver), input_data)

    nodes = [n for n in energy_system.nodes if not isinstance(n, Bus)]
    assert len(nodes) == 1, f"{key}: expected one component in the model, found {len(nodes)}"

    (node,) = nodes
    return {str(bus.label) for bus in node.inputs}, {str(bus.label) for bus in node.outputs}


def test_the_settings_for_the_model_test_cover_every_component():
    assert set(SETTINGS) == set(INFO)


@pytest.mark.parametrize("key", list(INFO))
def test_the_connections_are_the_buses_and_directions_of_the_real_model(key):
    takes, gives = model_connections(key)

    spec_in = {c.bus for c in INFO[key].connections if c.direction in ("in", "both")}
    spec_out = {c.bus for c in INFO[key].connections if c.direction in ("out", "both")}

    assert takes == spec_in
    assert gives == spec_out


# ---------------------------------------------------------------------------
# in step with the Streamlit interface while both exist
# ---------------------------------------------------------------------------

def test_the_components_groups_and_names_match_the_streamlit_registry():
    from frontend.ui_registry import UI_REGISTRY

    assert set(INFO) == set(UI_REGISTRY)

    for key, info in INFO.items():
        assert info.group == UI_REGISTRY[key]["group"], key
        # the registry writes Title Case; here the labels are in sentence case
        assert info.label.lower() == UI_REGISTRY[key]["label"].lower(), key


def test_the_order_is_the_same_as_in_the_streamlit_interface():
    from frontend_nicegui.selection import components_by_group

    assert list(INFO) == [key for keys in components_by_group().values() for key in keys]


def test_labels_are_in_sentence_case_and_short_labels_fit_a_box():
    for key, info in INFO.items():
        for text in (info.label, info.short_label):
            first, *rest = text.split()
            assert first[0].isupper(), text
            assert all(word.islower() or word.isupper() for word in rest), text
        assert len(info.short_label) <= 12, key


def test_the_pv_specification_agrees_with_the_description():
    info = INFO["pv"]

    assert (PV.label, PV.group, PV.role, PV.connections) == (
        info.label, info.group, info.role, info.connections,
    )


# ---------------------------------------------------------------------------
# the description checks itself
# ---------------------------------------------------------------------------

def info(**changes):
    values = dict(key="x", label="X", short_label="X", group="G", role="source",
                  connections=(Connection(bus="electricity", direction="out"),))
    values.update(changes)
    return ComponentInfo(**values)


@pytest.mark.parametrize("role, direction", [
    ("source", "in"), ("sink", "out"), ("storage", "in"), ("converter", "out"),
])
def test_role_and_connections_must_agree(role, direction):
    with pytest.raises(ValidationError):
        info(role=role, connections=(Connection(bus="heat", direction=direction),))


def test_an_unknown_component_is_named():
    with pytest.raises(KeyError, match="unknown component 'fusion'"):
        get_info("fusion")
    with pytest.raises(KeyError, match="unknown component 'fusion'"):
        bus_balance(["demand", "fusion"])


# ---------------------------------------------------------------------------
# who supplies and who uses an energy carrier
# ---------------------------------------------------------------------------

def problems(keys):
    return {
        bus: ("unsupplied" if b.unsupplied else "unused" if b.unused else "ok")
        for bus, b in bus_balance(keys).items()
    }


def test_nothing_chosen_means_nothing_to_report():
    assert bus_balance([]) == {}


def test_a_source_without_a_use_is_unused():
    assert problems(["pv"]) == {"electricity": "unused"}


def test_a_demand_without_a_supply_is_unsupplied():
    assert problems(["demand"]) == {"electricity": "unsupplied"}


def test_supply_and_use_together_are_fine():
    assert problems(["demand", "grid"]) == {"electricity": "ok"}


def test_a_heat_pump_needs_electricity_before_it_supplies_heat():
    assert problems(["heat_demand", "heat_pump"]) == {"electricity": "unsupplied", "heat": "unsupplied"}
    assert problems(["heat_demand", "heat_pump", "grid"]) == {"electricity": "ok", "heat": "ok"}


def test_a_boiler_needs_gas():
    assert problems(["heat_demand", "gas_boiler"]) == {"gas": "unsupplied", "heat": "unsupplied"}
    assert problems(["heat_demand", "gas_boiler", "gas_import"]) == {"gas": "ok", "heat": "ok"}


def test_a_chp_plant_without_users_is_reported_for_both_of_its_outputs():
    assert problems(["chp", "gas_import"]) == {"gas": "ok", "electricity": "unused", "heat": "unused"}


def test_converters_in_a_chain():
    # gas -> chp -> electricity -> heat pump -> heat
    assert problems(["gas_import", "chp", "heat_pump", "heat_demand"]) == {
        "gas": "ok", "electricity": "ok", "heat": "ok",
    }


def test_a_storage_neither_supplies_nor_uses():
    balance = bus_balance(["battery"])["electricity"]

    assert balance.stores == ("battery",)
    assert not balance.unsupplied and not balance.unused
    assert problems(["demand", "battery"]) == {"electricity": "unsupplied"}


def test_the_order_of_the_choice_does_not_matter():
    keys = ["heat_demand", "heat_pump", "grid", "demand", "chp", "gas_import"]

    expected = bus_balance(keys)
    for shuffled in itertools.islice(itertools.permutations(keys), 40):
        assert bus_balance(list(shuffled)) == expected


@pytest.mark.parametrize("name", [
    "Electricity only", "PV system", "PV + battery", "PV + wind", "Gas heating",
    "Heat pump + PV", "Heat pump + heating rod", "CHP system", "Full system",
])
def test_every_template_is_structurally_complete(name):
    from frontend.ui_templates import TEMPLATES

    assert set(problems(TEMPLATES[name]).values()) == {"ok"}


# ---------------------------------------------------------------------------
# against the system check, on every possible choice of components (2^13 = 8192)
# ---------------------------------------------------------------------------

def every_choice():
    for size in range(len(INFO) + 1):
        yield from (list(combo) for combo in itertools.combinations(INFO, size))


def test_the_diagram_rule_is_never_silent_when_the_system_check_finds_no_supply():
    silent = []

    for keys in every_choice():
        errors = " ".join(f.message for f in check_system(keys, {}, {}) if f.level == "error")
        structural = "has no supply" in errors or "cannot be supplied" in errors
        flagged = any(b.unsupplied or b.unused for b in bus_balance(keys).values())

        if structural and not flagged:
            silent.append(keys)

    assert silent == []


def test_a_demand_on_an_unsupplied_bus_is_always_an_error_in_the_system_check():
    missing = []

    for keys in every_choice():
        balance = bus_balance(keys)
        errors = " ".join(f.message for f in check_system(keys, {}, {}) if f.level == "error")

        if "demand" in keys and balance["electricity"].unsupplied and "has no supply" not in errors:
            missing.append(("electricity", keys))
        if "heat_demand" in keys and balance["heat"].unsupplied and "cannot be supplied" not in errors:
            missing.append(("heat", keys))

    assert missing == []