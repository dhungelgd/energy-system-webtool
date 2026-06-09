TECH_DEFAULTS = {
    "pv": {
        "capacity": 10.0,
        "capex": 1200.0,
        "opex": 2.0,
        "lifetime": 25.0,
        "interest_rate": 3.0,
        "maximum": None
    },

    "gas_boiler": {
        "capacity": 50.0,
        "capex": 150.0,
        "opex": 2.0,
        "lifetime": 20.0,
        "interest_rate": 3.0,
        "maximum": None,
        "efficiency": 0.9,
        "variable_costs": 0.1
    },

    "battery": {
        "capacity": 10.0,
        "capex": 400.0,
        "opex": 1,
        "lifetime": 15.0,
        "interest_rate": 3.0,
        "maximum": None,
        "loss_rate": 0.01,
        "efficiency": 0.95
    },

    "grid": {
        "variable_costs": 0.3
    },

    "grid_feedin": {
        "feedin_tariff": 0.08
    }
}