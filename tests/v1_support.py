"""Support for the tests: build a layout 2 scenario from a layout 1 scenario.

Layout 1 is what the engine reads. This is NOT part of the tool: no real layout 1
scenario files exist (the Streamlit app never saves scenarios), nothing in the
tool converts in this direction. It exists for the tests: they take systems that
the tool already handles, derive their layout 2 form with this, run both and
compare (see test_scenario_convert_golden.py). It goes away with the old engine.

Rules of the conversion:

- percentages: layout 2 holds percentages, layout 1 fractions (95 and 0.95),
- a demand profile whose values add up to 1 over a whole year becomes "shares of
  the annual demand" with the scaling factor as annual demand; with a factor of 1
  it is absolute; any other full-year profile is multiplied out to absolute kW
  (the hourly numbers stay the same); a part of a year cannot be tested and is
  taken as shares,
- a price series is converted to EUR per kWh (layout 1 has a price unit),
- values that the engine does not use for the chosen mode (a constant COP while
  a COP series is used) are not carried over.
"""

from pydantic import ValidationError

from backend.component_specs import INFO
from backend.price_units import DEFAULT_PRICE_UNIT, PRICE_UNIT_FACTORS
from backend.scenario_convert import PRICE_UNIT
from backend.scenario_v2 import BUILT_IN_CARRIERS, ScenarioV2
from backend.templates import TEMPLATES

FULL_YEAR = 8760
SHARE_TOLERANCE = 0.01          # a profile that adds up to 1 within one percent counts as "shares"

CARRIER_LABELS = {"electricity": "Electricity", "heat": "Heat", "gas": "Gas"}

# settings of a layout 1 component that are not simple one-to-one links
OTHER_V1_KEYS = {
    "demand": {"scaling_factor"},
    "heat_demand": {"scaling_factor"},
    "grid": {"price_mode", "price_unit"},
    "heat_pump": {"cop_mode", "cop_value"},
}

# the series a layout 1 scenario can hold, by key
STANDARD_SLOTS = {slot.v1_key: slot for template in TEMPLATES.values() for slot in template.slots}


class ConversionError(ValueError):
    """A layout 1 scenario cannot be converted to layout 2."""


def to_percent(fraction):
    return None if fraction is None else round(fraction * 100, 9)


def set_path(values, path, value):
    parts = path.split(".")
    node = values
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def scenario_from_v1(old):
    """Convert a layout 1 Scenario to a ScenarioV2."""

    problems = []
    components = []
    series = {}
    carriers_used = set()

    for key in old.components:
        template = TEMPLATES[key]
        info = INFO[key]
        values = old.settings.get(key, {})

        known = (
            {link.v1_key for link in template.links}
            | {slot.v1_key for slot in template.slots}
            | OTHER_V1_KEYS.get(key, set())
        )
        for unknown in sorted(set(values) - known):
            problems.append(f"{key}: the setting '{unknown}' cannot be converted")

        blocks = {block: {} for block in template.blocks}
        for link in template.links:
            value = values.get(link.v1_key)
            if value is not None:
                set_path(blocks[link.block], link.field, to_percent(value) if link.percent else value)
        if template.rated_flow is not None:
            blocks["capacity"]["rated_flow"] = template.rated_flow

        _series_from_v1(key, template, values, old, blocks, series, problems)

        components.append({
            "id": key, "name": info.label, "template": key, "kind": info.role,
            "connections": [{"carrier": c.bus, "direction": c.direction} for c in info.connections],
            "blocks": blocks,
        })
        carriers_used.update(c.bus for c in info.connections)

    # series that nothing refers to are kept, so that nothing is lost
    for v1_key, data in old.series.items():
        slot = STANDARD_SLOTS.get(v1_key)
        if slot is None:
            problems.append(f"the time series '{v1_key}' is not known")
        elif slot.series_id not in series:
            series[slot.series_id] = {"unit": slot.unit, "values": list(data)}

    if problems:
        raise ConversionError("; ".join(problems))

    carriers = [
        {"id": carrier, "label": CARRIER_LABELS[carrier]}
        for carrier in BUILT_IN_CARRIERS if carrier in carriers_used
    ]

    try:
        return ScenarioV2(
            name=old.name,
            time=old.time.model_dump(),
            carriers=carriers,
            components=components,
            series=series,
            solver=old.solver.model_dump(),
        )
    except ValidationError as error:
        raise ConversionError(f"the scenario does not fit layout 2: {error}") from error


def _column(values, v1_key):
    """The name of the file column that layout 1 keeps under the series key."""

    name = values.get(v1_key)
    return {"file": None, "column": name} if isinstance(name, str) else None


def _add_series(series, series_id, unit, data, values, v1_key):
    series[series_id] = {"unit": unit, "values": data}
    source = _column(values, v1_key)
    if source:
        series[series_id]["source"] = source


def _series_from_v1(key, template, values, old, blocks, series, problems):
    for slot in template.slots:
        data = list(old.series.get(slot.v1_key) or [])

        if key in ("demand", "heat_demand"):
            _demand_from_v1(slot, values, data, blocks, series)

        elif key == "grid":
            if values.get("price_mode", "constant") not in ("constant", "timeseries"):
                problems.append(f"grid: unknown price mode '{values.get('price_mode')}'")
            elif values.get("price_mode", "constant") == "timeseries":
                unit = values.get("price_unit", DEFAULT_PRICE_UNIT)
                if unit not in PRICE_UNIT_FACTORS:
                    problems.append(f"grid: unknown price unit '{unit}'")
                    continue
                factor = PRICE_UNIT_FACTORS[unit]
                data = [None if v is None else v * factor for v in data]
                blocks["costs"][slot.field] = slot.series_id
                _add_series(series, slot.series_id, PRICE_UNIT, data, values, slot.v1_key)

        elif key == "heat_pump":
            mode = values.get("cop_mode", "constant")
            if mode not in ("constant", "timeseries"):
                problems.append(f"heat_pump: unknown COP mode '{mode}'")
                continue
            if mode == "timeseries":
                set_path(blocks["conversion"], slot.field, slot.series_id)
                _add_series(series, slot.series_id, slot.unit, data, values, slot.v1_key)
            elif values.get("cop_value") is not None:
                set_path(blocks["conversion"], "outputs.heat.ratio", values["cop_value"])

        else:                                   # pv and wind: a profile that is always used
            blocks[slot.block][slot.field] = slot.series_id
            _add_series(series, slot.series_id, slot.unit, data, values, slot.v1_key)


def _demand_kind(profile, factor):
    if not profile or factor is None:
        return "annual_share"
    if factor == 1.0:
        return "absolute"

    numbers = [v for v in profile if v is not None]
    if len(profile) < FULL_YEAR or len(numbers) != len(profile):
        return "annual_share"                   # a part of a year cannot be tested

    return "annual_share" if abs(sum(numbers) - 1.0) <= SHARE_TOLERANCE else "multiplied"


def _demand_from_v1(slot, values, profile, blocks, series):
    factor = values.get("scaling_factor")
    kind = _demand_kind(profile, factor)
    block = blocks["demand"]
    block["series"] = slot.series_id

    if kind == "annual_share":
        block["profile_type"] = "annual_share"
        if factor is not None:
            block["annual_demand"] = factor
        _add_series(series, slot.series_id, slot.unit, profile, values, slot.v1_key)
        return

    block["profile_type"] = "absolute"
    if kind == "multiplied":
        profile = [None if v is None else v * factor for v in profile]
    _add_series(series, slot.series_id, "kW", profile, values, slot.v1_key)