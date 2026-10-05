TECH_DEFAULTS = {
    "pv": {
        "capacity": None,
        "capex": 1200.0,
        "opex": 2.0,
        "lifetime": 25.0,
        "interest_rate": 3.0,
        "maximum": None
    },

    "wind": {
        "capacity": None,
        "capex": 1600.0,
        "opex": 3.0,
        "lifetime": 20.0,
        "interest_rate": 3.0,
        "maximum": None
    },

    "gas_boiler": {
        "capacity": None,
        "capex": 175.0,
        "opex": 3.0,
        "lifetime": 20.0,
        "interest_rate": 3.0,
        "maximum": None,
        "efficiency": 0.9,
        "variable_costs": None
    },

    "battery": {
        "capacity": None,
        "capex": 400.0,
        "opex": 1.0,
        "lifetime": 15.0,
        "interest_rate": 3.0,
        "maximum": None,
        "loss_rate": 0.01,
        "efficiency": 0.95
    },

    "heat_storage": {
        "capacity": None,
        "capex": 40.0,
        "opex": 1.0,
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
    },

    "heating_rod": {
        "capacity": None,
        "capex": 100.0,
        "opex": 1.0,
        "lifetime": 20.0,
        "interest_rate": 3.0,
        "maximum": None,
        "efficiency": 0.99
    },

    "chp": {
        "capacity": None,
        "capex": 1000.0,
        "opex": 4.0,
        "lifetime": 20.0,
        "interest_rate": 3.0,
        "maximum": None,
        "efficiency_el": 0.35,
        "efficiency_th": 0.50
    },

    "heat_pump": {
        "cop_mode": "constant",
        "cop_value": 3.5,
        "capacity": None,
        "maximum": None,
        "capex": 1200.0,
        "opex": 1.0,
        "lifetime": 20.0,
        "interest_rate": 3.0,
        "variable_costs": None
    }
}