"""Checks of the input definitions of the user interface (no Streamlit needed)."""

import pytest

from frontend.ui_defaults import TECH_DEFAULTS
from frontend.ui_registry import UI_REGISTRY


def registry_fields(component):
    return {f["key"]: f for f in UI_REGISTRY[component].get("inputs", [])}


def test_every_default_has_a_single_source():
    # TECH_DEFAULTS overrides the registry. A value defined in both places
    # makes it unclear which one the user sees, so it may only live in one.
    doubles = [
        (component, key)
        for component, defaults in TECH_DEFAULTS.items()
        for key in defaults
        if "default" in registry_fields(component).get(key, {})
    ]
    assert doubles == []


@pytest.mark.parametrize("component", ["battery", "heat_storage"])
def test_storage_inputs_are_labelled_in_kwh(component):
    fields = registry_fields(component)

    assert "kWh" in fields["capacity"]["label"]
    assert "kWh" in fields["capex"]["label"]
    assert "kWh" in fields["maximum"]["label"]


def test_power_components_are_still_labelled_in_kw():
    assert "kW" in registry_fields("pv")["capacity"]["label"]
    assert "kWh" not in registry_fields("pv")["capacity"]["label"]


@pytest.mark.parametrize("component", ["battery", "heat_storage"])
def test_storage_has_a_c_rate_input(component):
    assert "c_rate" in registry_fields(component)


def test_heat_storage_self_discharge_default():
    assert registry_fields("heat_storage")["loss_rate"]["default"] == 0.001


def shown_default(component, field):
    return TECH_DEFAULTS.get(component, {}).get(field["key"], field.get("default"))


def test_number_inputs_show_their_default_exactly():
    # st.number_input shows 2 decimals unless a format is given, so a default
    # such as 0.001 would be displayed as 0.00.
    too_coarse = []
    for component, spec in UI_REGISTRY.items():
        for field in spec.get("inputs", []):
            value = shown_default(component, field)
            if field["type"] != "number" or value in (None, 0, 0.0):
                continue
            fmt = field.get("format", "%0.2f")
            if float(fmt % value) != pytest.approx(value, abs=1e-12):
                too_coarse.append((component, field["key"], value, fmt))
    assert too_coarse == []


def test_price_inputs_have_enough_decimals():
    for component, key in (("grid", "variable_costs"),
                           ("grid_feedin", "feedin_tariff"),
                           ("gas_import", "variable_costs")):
        fmt = registry_fields(component)[key]["format"]
        assert float(fmt % 0.2843) == pytest.approx(0.2843)
