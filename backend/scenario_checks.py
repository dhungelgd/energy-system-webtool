"""Checks of the data of a layout 2 scenario.

`check_data` looks at what the time series say, not at the structure (that is checked
when a scenario is created) and not at whether the engine can run it (see
`service_v2.py`). All of them are warnings: the scenario can still be run, but the
result is probably not what the user means.

`check_required` looks for settings that are not filled in. A scenario can hold an empty
setting (a form can leave one empty); the engine cannot run without it. Each of them is an
error, so that the run is refused with a sentence instead of stopping with an error that
nobody can read, or running with a value of 0 that nobody chose.

The findings are codes plus parameters (see findings.py); the sentences are in the
catalogs of backend/i18n.

- A demand profile of "shares of the annual demand" has to add up to 1 over a year.
  Only a whole year can be tested; a part of a year says nothing about the total.
- A generation profile is a capacity factor, at most 1 (output per installed kW).
  A profile downloaded for a larger system has values above 1.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from backend.blocks import get_path
from backend.findings import Fixed, SettingRef, coded, reference

FULL_YEAR = 8760
SHARE_TOLERANCE = 0.01              # a profile that adds up to 1 within one percent is fine
CAPACITY_FACTOR_TOLERANCE = 1e-9


def check_data(scenario):
    """Warnings about the time series of a ScenarioV2, in the order of the components."""

    findings = []

    for component in scenario.components:
        findings.extend(_demand_profile(component, scenario))
        findings.extend(_generation_profile(component, scenario))

    return findings


# What a component needs that the system check does not ask for. (It asks for a fixed or an invested
# size, the efficiency of a heating rod and of a CHP plant, a COP and a C-rate.)
STORAGE_REQUIRED = (
    ("storage", "efficiency_charge"), ("storage", "efficiency_discharge"), ("storage", "loss_rate"),
)
REQUIRED = {
    "gas_boiler": (("conversion", "outputs.heat.efficiency"),),
    "battery": STORAGE_REQUIRED,
    "heat_storage": STORAGE_REQUIRED,
    "grid_feedin": (("costs", "revenue"),),
    "gas_import": (("costs", "variable_costs"),),
}


def required_settings(component):
    """The (block, setting) pairs that a component needs, besides what the system check asks for."""

    required = list(REQUIRED.get(component.template, ()))

    if component.template == "grid" and component.blocks.get("costs", {}).get("variable_costs_series") is None:
        required.append(("costs", "variable_costs"))                    # a price series replaces the price

    demand = component.blocks.get("demand", {})
    if component.template in ("demand", "heat_demand") and demand.get("profile_type", "annual_share") == "annual_share":
        required.append(("demand", "annual_demand"))                    # a demand in kW does not need it

    return required


def check_required(scenario):
    """Errors for the settings that are not filled in, in the order of the components."""

    findings = []

    for component in scenario.components:
        for block, key in required_settings(component):
            if get_path(component.blocks.get(block, {}), key) is None:
                findings.append(coded(
                    "error", "value_missing",
                    component=reference(component), setting=SettingRef(block, key, component.template),
                ))

    return findings


def _values(component, scenario, block, key="series"):
    """The values of the series a block refers to, or None if there is none."""

    series_id = component.blocks.get(block, {}).get(key)
    if series_id is None or series_id not in scenario.series:
        return None
    return scenario.series[series_id].values


def _demand_profile(component, scenario):
    demand = component.blocks.get("demand")
    values = _values(component, scenario, "demand")

    if demand is None or values is None:
        return []
    if demand.get("profile_type", "annual_share") != "annual_share":
        return []
    if len(values) < FULL_YEAR or any(v is None for v in values):
        return []                                       # a part of a year cannot be tested

    total = sum(values)
    if abs(total - 1.0) <= SHARE_TOLERANCE:
        return []

    return [coded("warning", "profile_shares", component=reference(component), total=Fixed(total, 3))]


def _generation_profile(component, scenario):
    values = _values(component, scenario, "profile")
    numbers = [v for v in (values or []) if v is not None]

    if not numbers or max(numbers) <= 1.0 + CAPACITY_FACTOR_TOLERANCE:
        return []

    return [coded("warning", "capacity_factor", component=reference(component), maximum=Fixed(max(numbers), 2))]