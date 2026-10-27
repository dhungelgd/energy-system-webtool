"""Adapter from scenario layout 2 to what the engine reads (layout 1). TEMPORARY.

    scenario_to_v1(new)      layout 2 -> layout 1, or NotSupportedByEngine
    engine_gaps(new)         what the engine cannot run yet, as sentences

The engine still reads layout 1 (`backend/scenario.py`). This is how a layout 2
scenario gets run until the generic engine replaces the old one; then this module,
the old engine and layout 1 are deleted.

It only works for what the engine can run today: the curated components, one of
each, with the settings it knows. Everything else is reported and is never dropped
silently. A layout 2 scenario holds percentages and the demand as shares of the
annual demand or in kW; the engine gets fractions and a scaling factor.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from backend.blocks import BLOCKS
from backend.component_specs import INFO
from backend.price_units import DEFAULT_PRICE_UNIT
from backend.scenario import Scenario
from backend.scenario_v2 import BUILT_IN_CARRIERS
from backend.templates import TEMPLATES

PRICE_UNIT = "€ per kWh"

# the key a layout 1 scenario uses for a series, by the standard id of layout 2
SERIES_IDS = {
    slot.series_id: slot.v1_key for template in TEMPLATES.values() for slot in template.slots
}


class NotSupportedByEngine(ValueError):
    """A layout 2 scenario holds something the engine cannot run yet. `gaps` lists it."""

    def __init__(self, gaps):
        self.gaps = list(gaps)

        numbered = " ".join(f"({n}) {gap}" for n, gap in enumerate(self.gaps, 1))
        super().__init__(f"The engine cannot run this scenario yet. {numbered}")

    def __reduce__(self):
        # so that it can be sent between processes (pickle)
        return (type(self), (self.gaps,))


def from_percent(percent):
    return None if percent is None else percent / 100


def flatten(values, prefix=""):
    """{path: value} of everything that is filled in, nested settings as dotted paths."""

    found = {}
    for key, value in values.items():
        if isinstance(value, dict):
            found.update(flatten(value, f"{prefix}{key}."))
        elif value is not None:
            found[f"{prefix}{key}"] = value
    return found


def engine_gaps(scenario):
    """Everything in a layout 2 scenario that the engine cannot run yet, as sentences."""

    return _to_v1(scenario)[3]


def scenario_to_v1(scenario):
    """Convert a ScenarioV2 to a layout 1 Scenario, or raise NotSupportedByEngine."""

    keys, settings, series, gaps = _to_v1(scenario)

    if gaps:
        raise NotSupportedByEngine(gaps)

    return Scenario(
        name=scenario.name,
        components=keys,
        settings=settings,
        time=scenario.time.model_dump(),
        series=series,
        solver=scenario.solver.model_dump(),
    )


def _to_v1(scenario):
    gaps = []
    settings, series, keys = {}, {}, []

    for carrier in scenario.carriers:
        if carrier.id not in BUILT_IN_CARRIERS:
            gaps.append(
                f"The carrier '{carrier.id}' is user-defined; the engine only knows "
                f"electricity, heat and gas"
            )

    by_template = {}
    for component in scenario.components:
        if component.template is None:
            gaps.append(f"'{component.id}' is a custom component; the engine only runs the curated components")
        elif component.template not in TEMPLATES:
            gaps.append(f"'{component.id}' uses the unknown template '{component.template}'")
        else:
            by_template.setdefault(component.template, []).append(component)

    for key, found in by_template.items():
        if len(found) > 1:
            gaps.append(
                f"The engine can only run one {INFO[key].label} "
                f"(found {', '.join(c.id for c in found)})"
            )
            continue

        converted = _component_to_v1(found[0], TEMPLATES[key], scenario, gaps)
        if converted is not None:
            keys.append(key)
            settings[key], more_series = converted
            series.update(more_series)

    # series that nothing refers to, under a known id, go back to where they came from
    for series_id, data in scenario.series.items():
        v1_key = SERIES_IDS.get(series_id)
        if v1_key is not None and v1_key not in series:
            series[v1_key] = list(data.values)

    return keys, settings, series, gaps


def _component_to_v1(component, template, scenario, gaps):
    name, info = component.id, INFO[template.key]

    wanted = {(c.bus, c.direction) for c in info.connections}
    found = {(c.carrier, c.direction) for c in component.connections}
    if component.kind != info.role or found != wanted:
        gaps.append(f"'{name}' was changed from its template (kind or connections)")
        return None

    remaining = {block: flatten(values) for block, values in component.blocks.items()}

    for block in list(remaining):
        if block not in template.blocks:
            spec = BLOCKS.get(block)
            if spec is not None and not spec.engine_supported:
                gaps.append(f"'{name}': {spec.label} is not supported by the engine yet")
            else:
                gaps.append(f"'{name}': the block '{block}' is not part of {info.label}")
            remaining.pop(block)

    v1, series = {}, {}

    for link in template.links:
        value = remaining.get(link.block, {}).pop(link.field, None)
        if value is not None:
            v1[link.v1_key] = from_percent(value) if link.percent else value

    rated = remaining.get("capacity", {}).pop("rated_flow", None)
    if rated is not None and rated != template.rated_flow:
        gaps.append(f"'{name}': the size refers to '{rated}', but the engine uses '{template.rated_flow}'")

    _specials_to_v1(template.key, remaining, v1)

    for slot in template.slots:
        series_id = remaining.get(slot.block, {}).pop(slot.field, None)
        if series_id is None:
            continue

        data = scenario.series[series_id]
        if slot.v1_key == "grid_price" and data.unit not in ("", PRICE_UNIT):
            gaps.append(f"'{name}': the price series must be in {PRICE_UNIT}, not '{data.unit}'")

        series[slot.v1_key] = list(data.values)
        if data.source is not None and data.source.column:
            v1[slot.v1_key] = data.source.column

    for block, left in remaining.items():
        for path in left:
            gaps.append(f"'{name}': the setting '{block}.{path}' is not supported by the engine yet")

    return v1, series


def _specials_to_v1(key, remaining, v1):
    if key in ("demand", "heat_demand"):
        block = remaining.get("demand", {})
        profile_type = block.pop("profile_type", "annual_share")
        annual = block.pop("annual_demand", None)
        v1["scaling_factor"] = 1.0 if profile_type == "absolute" else annual
        if v1["scaling_factor"] is None:
            del v1["scaling_factor"]

    elif key == "grid":
        v1["price_mode"] = "timeseries" if "variable_costs_series" in remaining.get("costs", {}) else "constant"
        v1["price_unit"] = DEFAULT_PRICE_UNIT

    elif key == "heat_pump":
        block = remaining.get("conversion", {})
        ratio = block.pop("outputs.heat.ratio", None)
        if "outputs.heat.ratio_series" in block:
            v1["cop_mode"] = "timeseries"
        else:
            v1["cop_mode"] = "constant"
            if ratio is not None:
                v1["cop_value"] = ratio