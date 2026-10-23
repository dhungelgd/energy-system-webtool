PARAMS_BLOCK = [
    {"key": "mode", "type": "selectbox", "label": "Mode", "options": ["fixed", "invest"]},
    {"key": "capacity", "type": "number", "label": "Capacity (kW)"},
    {"key": "capex", "type": "number", "label": "CAPEX (€/kW)"},
    {"key": "opex", "type": "number", "label": "Fixed OPEX fraction (% of CAPEX)"},
    {"key": "lifetime", "type": "number", "label": "Lifetime (years)"},
    {"key": "interest_rate", "type": "number", "label": "Interest rate"},
    {"key": "maximum", "type": "number", "label": "Maximum capacity"}
]

# a storage is sized in kWh (energy), not in kW
STORAGE_UNIT_LABELS = {
    "capacity": "Capacity (kWh)",
    "capex": "CAPEX (€/kWh)",
    "maximum": "Maximum capacity (kWh)",
}
STORAGE_PARAMS_BLOCK = [
    {**field, "label": STORAGE_UNIT_LABELS.get(field["key"], field["label"])}
    for field in PARAMS_BLOCK
]