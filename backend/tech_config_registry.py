def demand_config(tech_inputs=None, input_data=None, **kwargs):

    tech_inputs = tech_inputs or {}
    input_data = input_data or {}
    demand = tech_inputs.get("demand", {})

    return {
        "type": "demand",
        "bus": "electricity_bus",
        "scaling_factor": demand.get("scaling_factor", 1.0),
        "profile_data": input_data.get("electricity_demand", [])
    }

def heat_demand_config(tech_inputs=None, input_data=None, **kwargs):

    tech_inputs = tech_inputs or {}
    input_data = input_data or {}
    heat_demand = tech_inputs.get("heat_demand", {})

    return {
        "type": "heat_demand",
        "bus": "heat_bus",
        "scaling_factor": heat_demand.get("scaling_factor", 1.0),
        "profile_data": input_data.get("heat_demand", [])
    }

def grid_config(tech_inputs=None, **kwargs):

    tech_inputs = tech_inputs or {}
    grid = tech_inputs.get("grid", {})

    return {
        "type": "grid",
        "bus": "electricity_bus",
        "variable_costs": grid.get("variable_costs", 0.3)
    }

def grid_feedin_config(tech_inputs, input_data):

    return {
        "type": "grid_feedin",
        "bus": "electricity_bus",
        "feedin_tariff": tech_inputs.get("feedin_tariff", 0.06)
    }

def pv_config(tech_inputs=None, input_data=None, **kwargs):

    pv = tech_inputs.get("pv", {}) if tech_inputs else {}

    return {
        "type": "pv",
        "bus": "electricity_bus",
        "mode": pv.get("mode", "fixed"),
        "capacity": pv.get("capacity", 10),
        "maximum": pv.get("maximum", 100),
        "profile_key": pv.get("profile_key", "pv"),
        "capex": pv.get("capex", 1200),
        "opex": pv.get("opex", 0.02),
        "lifetime": pv.get("lifetime", 20),
        "interest_rate": pv.get("interest_rate", 0.03),
    }


def battery_config(tech_inputs=None, **kwargs):

    bat = tech_inputs.get("battery", {}) if tech_inputs else {}

    return {
        "type": "battery",
        "bus": "electricity_bus",
        "capacity": bat.get("capacity", 10),
        "loss_rate": bat.get("loss_rate", 0.01),
        "inflow_conversion_factor": bat.get("inflow_conversion_factor", 0.95),
        "mode": bat.get("mode", "fixed"),
        "capex": bat.get("capex", 500),
        "opex": bat.get("opex", 0.01),
        "lifetime": bat.get("lifetime", 15),
        "interest_rate": bat.get("interest_rate", 0.06),
    }

def gas_import_config(tech_inputs=None, input_data=None, **kwargs):

    gi = tech_inputs.get("gas_import", {}) if tech_inputs else {}

    return {
        "type": "gas_import",
        "bus": "gas_bus",
        "variable_costs": gi.get("variable_costs", 0.1)
    }

def gas_boiler_config(tech_inputs=None, input_data=None, **kwargs):

    gb = tech_inputs.get("gas_boiler", {}) if tech_inputs else {}

    return {
        "type": "gas_boiler",
        "fuel_bus": "gas_bus",
        "heat_bus": "heat_bus",
        "efficiency": gb.get("efficiency", 0.9),
        "variable_costs": gb.get("variable_costs", 0.06),
        "capacity": gb.get("capacity", 50)
    }

TECH_CONFIG_REGISTRY = {
    "demand": demand_config,
    "heat_demand": heat_demand_config,
    "grid": grid_config,
    "grid_feedin": grid_feedin_config,
    "pv": pv_config,
    "battery": battery_config,
    "gas_import": gas_import_config,
    "gas_boiler": gas_boiler_config
}