# Ready-made starting points for the component selection.
#
# Each template is a list of component keys from UI_REGISTRY (ui_registry.py).
# To add or change a template, edit this dictionary; nothing else needs to change.
# The name is shown on the button in the sidebar.

TEMPLATES = {
    "Electricity only": [
        "demand", "grid",
    ],

    "PV system": [
        "demand", "grid", "grid_feedin", "pv",
    ],

    "PV + battery": [
        "demand", "grid", "grid_feedin", "pv", "battery",
    ],

    "PV + wind": [
        "demand", "grid", "grid_feedin", "pv", "wind",
    ],

    "Gas heating": [
        "heat_demand", "gas_import", "gas_boiler",
    ],

    "Heat pump + PV": [
        "demand", "heat_demand", "grid", "grid_feedin", "pv", "heat_pump",
    ],

    "Heat pump + heating rod": [
        "demand", "heat_demand", "grid", "grid_feedin", "pv", "heat_pump", "heating_rod", "heat_storage",
    ],

    "CHP system": [
        "demand", "heat_demand", "grid", "grid_feedin", "gas_import", "chp", "gas_boiler",
    ],

    "Full system": [
        "demand", "heat_demand",
        "grid", "grid_feedin", "gas_import",
        "pv", "wind",
        "gas_boiler", "heat_pump", "heating_rod", "chp",
        "battery", "heat_storage",
    ],
}