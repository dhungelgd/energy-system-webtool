"""Ready-made starting points for a scenario, and how the components are grouped.

A system template is a list of component templates (the keys of `templates.py`)
that make a typical energy system. The Streamlit interface has the same lists in
`frontend/ui_templates.py`; a test keeps them equal while both exist.

Components are shown in groups (Demand, Grid & fuel, ...). The order of the groups,
and inside a group the order of `component_specs.INFO`, is also the order in which
the components are handed to the engine, so that the same choice gives the same
system in every interface.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

from backend.component_specs import INFO

GROUP_ORDER = ("Demand", "Grid & fuel", "Generation", "Conversion", "Storage")

SYSTEM_TEMPLATES = {
    "Electricity only": ("demand", "grid"),
    "PV system": ("demand", "grid", "grid_feedin", "pv"),
    "PV + battery": ("demand", "grid", "grid_feedin", "pv", "battery"),
    "PV + wind": ("demand", "grid", "grid_feedin", "pv", "wind"),
    "Gas heating": ("heat_demand", "gas_import", "gas_boiler"),
    "Heat pump + PV": ("demand", "heat_demand", "grid", "grid_feedin", "pv", "heat_pump"),
    "Heat pump + heating rod": (
        "demand", "heat_demand", "grid", "grid_feedin", "pv", "heat_pump", "heating_rod", "heat_storage",
    ),
    "CHP system": ("demand", "heat_demand", "grid", "grid_feedin", "gas_import", "chp", "gas_boiler"),
    "Full system": (
        "demand", "heat_demand",
        "grid", "grid_feedin", "gas_import",
        "pv", "wind",
        "gas_boiler", "heat_pump", "heating_rod", "chp",
        "battery", "heat_storage",
    ),
}


def components_by_group():
    """{group: [component keys]} in the order the groups are shown (empty groups left out)."""

    groups = {name: [] for name in GROUP_ORDER}

    for key, info in INFO.items():
        groups.setdefault(info.group, []).append(key)

    return {name: keys for name, keys in groups.items() if keys}


def in_order(keys):
    """The given component keys in the order of the groups, whatever order they came in."""

    wanted = set(keys)

    return [key for group in components_by_group().values() for key in group if key in wanted]