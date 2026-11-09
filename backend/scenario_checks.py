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

`check_period` warns about components in investment mode when the simulated period is shorter than a year: the
yearly cost of a plant is not scaled to the period, and the seasons differ, so the sizes are only reliable for a
whole year.

`check_unbounded` finds a way to an optimization without an end: a PV system or a wind turbine that may be
built without an upper limit and earns more from feeding in than it costs. Each plant that is added earns
money, so the optimizer builds without end and there is no result. It is an error, because nothing can be
run (HiGHS and CBC both stop with 'unbounded', after minutes for a year). The sum is the same as the model's:
the revenue of the feed-in for the output of one kW over the simulated period, minus the cost of one kW
(`calculate_epc`, which the model uses; it does not scale it to a period shorter than a year, and neither does
this). Checked against the solvers on random systems (tests/test_unbounded.py).

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from backend.blocks import get_path
from backend.findings import Fixed, SettingRef, coded, reference
from backend.oemof_components import calculate_epc

FULL_YEAR = 8760
NEARLY_FULL_YEAR = 8700               # from here on a run counts as a whole year (as in kpis.py)
PROFILE_SOURCES = ("pv", "wind")      # output = profile x installed capacity, at no running cost
MARGIN_TOLERANCE = 1e-9               # a gain this small is a rounding error, not a trap
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


def check_unbounded(scenario):
    """Errors for a plant that may be built without an upper limit and earns more than it costs."""

    revenue = _feedin_revenue(scenario)
    if revenue is None or revenue <= 0:
        return []

    findings = []

    for component in scenario.components:
        if component.template not in PROFILE_SOURCES:
            continue

        margin = _margin_per_kw(component, scenario, revenue)
        if margin is not None and margin > MARGIN_TOLERANCE:
            findings.append(coded(
                "error", "unbounded_plant",
                component=reference(component), margin=Fixed(margin, 2), revenue=revenue,
            ))

    return findings


def _feedin_revenue(scenario):
    """The revenue per kWh that feeding in earns, or None if there is no feed-in (or no revenue yet)."""

    for component in scenario.components:
        if component.template == "grid_feedin":
            return get_path(component.blocks.get("costs", {}), "revenue")

    return None


def _margin_per_kw(component, scenario, revenue):
    """What one kW of the plant earns from feeding in, minus what it costs, over the simulated period.

    None if the plant cannot be built without end (fixed size, or an upper limit) or if something that the
    sum needs is missing (that is reported by the other checks).
    """

    capacity = component.blocks.get("capacity", {})
    if capacity.get("mode") != "invest" or capacity.get("maximum") is not None:
        return None

    values = _values(component, scenario, "profile")
    costs = [capacity.get(key) for key in ("capex", "opex", "lifetime", "interest_rate")]
    if values is None or any(cost is None for cost in costs) or costs[2] <= 0:
        return None

    output = sum(v for v in values[:scenario.time.steps] if v is not None)

    return revenue * output - calculate_epc(*costs)


def check_period(scenario):
    """A warning if components are in investment mode and the simulated period is shorter than a year."""

    if scenario.time.steps >= NEARLY_FULL_YEAR:
        return []

    sized = [c for c in scenario.components if c.blocks.get("capacity", {}).get("mode") == "invest"]
    if not sized:
        return []

    return [coded("warning", "short_period_invest", components=[reference(c) for c in sized], n=len(sized))]