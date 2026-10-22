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