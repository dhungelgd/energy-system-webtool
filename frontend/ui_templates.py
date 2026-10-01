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

    "Gas heating": [
        "heat_demand", "gas_import", "gas_boiler",
    ],

    "Heat pump + PV": [
        "demand", "heat_demand", "grid", "grid_feedin", "pv", "heat_pump",
    ],

    "Full system": [
        "demand", "heat_demand",
        "grid", "grid_feedin", "gas_import",
        "pv",
        "gas_boiler", "heat_pump",
        "battery", "heat_storage",
    ],
}