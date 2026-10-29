"""The 13 curated components as data: templates.

A template says what a curated component is (its kind and connections, from
`component_specs.INFO`), which blocks it has, the defaults of its settings, and
how its settings correspond to the settings of a layout 1 scenario, which the
engine still reads (`backend/scenario_convert.py` uses this to run a layout 2
scenario on the old engine).

Defaults are in the units of layout 2: percentages as percentages. A test keeps
them equal to the defaults of the Streamlit interface while both exist.

The links to layout 1 (`links`, `slots`) are temporary: they exist for the adapter
to the old engine and go away with it. Everything else stays.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

import copy
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from backend.component_specs import INFO
from backend.scenario_v2 import BUILT_IN_CARRIERS, Component, Connection


class Link(BaseModel):
    """A setting of a block that corresponds to one setting of a layout 1 component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    block: str
    field: str                      # a setting of the block, or a path such as "outputs.heat.efficiency"
    v1_key: str
    percent: bool = False           # layout 2 holds a percentage, layout 1 a fraction


class SeriesSlot(BaseModel):
    """A time series the component uses: where it is referenced, and under which key layout 1 holds it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    block: str
    field: str
    v1_key: str
    series_id: str                  # the id used in layout 2 when a layout 1 scenario is converted
    unit: str


class Template(BaseModel):
    """One curated component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    blocks: tuple[str, ...]
    defaults: dict[str, dict[str, Any]]
    links: tuple[Link, ...] = ()
    slots: tuple[SeriesSlot, ...] = ()
    rated_flow: Optional[str] = None


# ---------------------------------------------------------------------------
# the building pieces
# ---------------------------------------------------------------------------

def capacity_links():
    return tuple(
        Link(block="capacity", field=key, v1_key=key)
        for key in ("mode", "capacity", "maximum", "capex", "opex", "lifetime", "interest_rate")
    )


def storage_links():
    return capacity_links() + (
        Link(block="storage", field="c_rate", v1_key="c_rate"),
        Link(block="storage", field="efficiency_charge", v1_key="efficiency_charge", percent=True),
        Link(block="storage", field="efficiency_discharge", v1_key="efficiency_discharge", percent=True),
        Link(block="storage", field="loss_rate", v1_key="loss_rate", percent=True),
    )


def capacity_defaults(capex, opex, lifetime):
    return {"mode": "fixed", "capex": capex, "opex": opex, "lifetime": lifetime, "interest_rate": 3.0}


def storage(capex, opex, c_rate):
    return {
        "capacity": capacity_defaults(capex, opex, 15.0),
        "storage": {"c_rate": c_rate, "efficiency_charge": 95.0, "efficiency_discharge": 95.0, "loss_rate": 0.1},
    }


def converter_template(key, defaults, extra_links=(), rated_flow="heat", slots=()):
    return Template(
        key=key,
        blocks=("capacity", "conversion"),
        defaults=defaults,
        links=capacity_links() + tuple(extra_links),
        slots=tuple(slots),
        rated_flow=rated_flow,
    )


def efficiency_link(carrier, v1_key):
    return Link(block="conversion", field=f"outputs.{carrier}.efficiency", v1_key=v1_key, percent=True)


def _build():
    return (
        Template(
            key="demand", blocks=("demand",),
            defaults={"demand": {"profile_type": "annual_share", "annual_demand": 30000.0}},
            slots=(SeriesSlot(block="demand", field="series", v1_key="electricity_demand",
                              series_id="electricity_demand", unit="share of the annual demand"),),
        ),
        Template(
            key="heat_demand", blocks=("demand",),
            defaults={"demand": {"profile_type": "annual_share", "annual_demand": 90000.0}},
            slots=(SeriesSlot(block="demand", field="series", v1_key="heat_demand",
                              series_id="heat_demand", unit="share of the annual demand"),),
        ),
        Template(
            key="grid", blocks=("costs",),
            defaults={"costs": {"variable_costs": 0.3}},
            links=(Link(block="costs", field="variable_costs", v1_key="variable_costs"),),
            slots=(SeriesSlot(block="costs", field="variable_costs_series", v1_key="grid_price",
                              series_id="grid_price", unit="€ per kWh"),),
        ),
        Template(
            key="grid_feedin", blocks=("costs",),
            defaults={"costs": {"revenue": 0.078}},
            links=(Link(block="costs", field="revenue", v1_key="feedin_tariff"),),
        ),
        Template(
            key="gas_import", blocks=("costs",),
            defaults={"costs": {"variable_costs": 0.1}},
            links=(Link(block="costs", field="variable_costs", v1_key="variable_costs"),),
        ),
        Template(
            key="pv", blocks=("capacity", "profile"),
            defaults={"capacity": capacity_defaults(1200.0, 2.0, 25.0)},
            links=capacity_links(),
            slots=(SeriesSlot(block="profile", field="series", v1_key="pv",
                              series_id="pv_profile", unit="capacity factor"),),
        ),
        Template(
            key="wind", blocks=("capacity", "profile"),
            defaults={"capacity": capacity_defaults(1600.0, 3.0, 20.0)},
            links=capacity_links(),
            slots=(SeriesSlot(block="profile", field="series", v1_key="wind",
                              series_id="wind_profile", unit="capacity factor"),),
        ),
        converter_template(
            "gas_boiler",
            defaults={"capacity": capacity_defaults(175.0, 3.0, 20.0),
                      "conversion": {"outputs": {"heat": {"efficiency": 90.0}}}},
            extra_links=(efficiency_link("heat", "efficiency"),),
        ),
        converter_template(
            "heating_rod",
            defaults={"capacity": capacity_defaults(100.0, 1.0, 20.0),
                      "conversion": {"outputs": {"heat": {"efficiency": 99.0}}}},
            extra_links=(efficiency_link("heat", "efficiency"),),
        ),
        converter_template(
            "chp",
            defaults={"capacity": capacity_defaults(1000.0, 4.0, 20.0),
                      "conversion": {"outputs": {"electricity": {"efficiency": 35.0},
                                                 "heat": {"efficiency": 50.0}}}},
            extra_links=(efficiency_link("electricity", "efficiency_el"),
                         efficiency_link("heat", "efficiency_th")),
            rated_flow="electricity",
        ),
        converter_template(
            "heat_pump",
            defaults={"capacity": capacity_defaults(1200.0, 1.0, 20.0),
                      "conversion": {"outputs": {"heat": {"ratio": 3.5}}}},
            slots=(SeriesSlot(block="conversion", field="outputs.heat.ratio_series", v1_key="cop_series",
                              series_id="cop_profile", unit="ratio"),),
        ),
        Template(
            key="battery", blocks=("capacity", "storage"),
            defaults=storage(400.0, 1.0, 0.5),
            links=storage_links(),
        ),
        Template(
            key="heat_storage", blocks=("capacity", "storage"),
            defaults=storage(40.0, 1.0, 0.25),
            links=storage_links(),
        ),
    )


TEMPLATES = {template.key: template for template in _build()}


def new_component(template_key, component_id=None, name=None):
    """A new component of a template, with the defaults filled in.

    Time series are not referenced yet: there is no series until one is added.
    """

    template = TEMPLATES[template_key]
    info = INFO[template_key]

    blocks = {block: copy.deepcopy(template.defaults.get(block, {})) for block in template.blocks}
    if template.rated_flow is not None:
        blocks["capacity"]["rated_flow"] = template.rated_flow

    return Component(
        id=component_id or template_key,
        name=name or info.label,
        template=template_key,
        kind=info.role,
        connections=[Connection(carrier=c.bus, direction=c.direction) for c in info.connections],
        blocks=blocks,
    )

CARRIER_LABELS = {"electricity": "Electricity", "heat": "Heat", "gas": "Gas"}

def carriers_for(components):
    """The built-in carriers that the components connect to, as the list a scenario needs.

    In the usual order (electricity, heat, gas); a carrier that no component uses is left out.
    """

    used = {connection.carrier for component in components for connection in component.connections}

    return [{"id": carrier, "label": CARRIER_LABELS[carrier]} for carrier in BUILT_IN_CARRIERS if carrier in used]