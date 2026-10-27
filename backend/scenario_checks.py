"""Checks of the data of a layout 2 scenario.

These look at what the time series say, not at the structure (that is checked when
a scenario is created) and not at whether the engine can run it (see
`service_v2.py`). All of them are warnings: the scenario can still be run, but the
result is probably not what the user means.

- A demand profile of "shares of the annual demand" has to add up to 1 over a year.
  Only a whole year can be tested; a part of a year says nothing about the total.
- A generation profile is a capacity factor, at most 1 (output per installed kW).
  A profile downloaded for a larger system has values above 1.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from backend.blocks import BLOCKS
from backend.system_check import Finding

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

    absolute = BLOCKS["demand"].fields[0].option_labels["absolute"]
    return [Finding(
        "warning",
        f"{component.name}: the demand profile adds up to {total:.3f}, but shares of the "
        f"annual demand must add up to 1 over a year. Check the profile, or choose "
        f"'{absolute}'.",
    )]


def _generation_profile(component, scenario):
    values = _values(component, scenario, "profile")
    numbers = [v for v in (values or []) if v is not None]

    if not numbers or max(numbers) <= 1.0 + CAPACITY_FACTOR_TOLERANCE:
        return []

    return [Finding(
        "warning",
        f"{component.name}: the generation profile has values up to {max(numbers):.2f}, but a "
        f"capacity factor is at most 1 (output per installed kW). A profile downloaded for a "
        f"larger system has to be divided by its size.",
    )]