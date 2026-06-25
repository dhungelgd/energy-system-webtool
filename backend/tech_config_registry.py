def demand_config(tech_inputs=None, input_data=None, **kwargs):

    tech_inputs = tech_inputs or {}
    input_data = input_data or {}
    demand = tech_inputs.get("demand", {})

    return {
        "type": "demand",
        "bus": "electricity_bus",
        "scaling_factor": demand.get("scaling_factor"),
        "profile_data": input_data.get("electricity_demand")
    }

def heat_demand_config(tech_inputs=None, input_data=None, **kwargs):

    tech_inputs = tech_inputs or {}
    input_data = input_data or {}
    heat_demand = tech_inputs.get("heat_demand", {})

    return {
        "type": "heat_demand",
        "bus": "heat_bus",
        "scaling_factor": heat_demand.get("scaling_factor"),
        "profile_data": input_data.get("heat_demand")
    }

def grid_config(tech_inputs=None, **kwargs):

    tech_inputs = tech_inputs or {}
    grid = tech_inputs.get("grid", {})

    return {
        "type": "grid",
        "bus": "electricity_bus",
        "variable_costs": grid.get("variable_costs")
    }

def grid_feedin_config(tech_inputs, input_data):

    grid_feedin = tech_inputs.get("grid_feedin", {})

    return {
        "type": "grid_feedin",
        "bus": "electricity_bus",
        "feedin_tariff": grid_feedin.get("feedin_tariff")
    }

def pv_config(tech_inputs=None, input_data=None, **kwargs):

    pv = tech_inputs.get("pv", {}) if tech_inputs else {}

    return {
        "type": "pv",
        "bus": "electricity_bus",
        "mode": pv.get("mode"),
        "capacity": pv.get("capacity"),
        "maximum": pv.get("maximum"),
        "profile_key": pv.get("profile_key", "pv"),
        "capex": pv.get("capex"),
        "opex": pv.get("opex"),
        "lifetime": pv.get("lifetime"),
        "interest_rate": pv.get("interest_rate"),
    }


def battery_config(tech_inputs=None, **kwargs):

    bat = tech_inputs.get("battery", {}) if tech_inputs else {}

    return {
        "type": "battery",
        "bus": "electricity_bus",
        "capacity": bat.get("capacity"),
        "loss_rate": bat.get("loss_rate"),
        "inflow_conversion_factor": bat.get("inflow_conversion_factor"),
        "mode": bat.get("mode"),
        "capex": bat.get("capex"),
        "opex": bat.get("opex"),
        "lifetime": bat.get("lifetime"),
        "interest_rate": bat.get("interest_rate"),
    }

def gas_import_config(tech_inputs=None, input_data=None, **kwargs):

    gi = tech_inputs.get("gas_import", {}) if tech_inputs else {}

    return {
        "type": "gas_import",
        "bus": "gas_bus",
        "variable_costs": gi.get("variable_costs")
    }

def gas_boiler_config(tech_inputs=None, input_data=None, **kwargs):

    gb = tech_inputs.get("gas_boiler", {}) if tech_inputs else {}

    return {
        "type": "gas_boiler",
        "fuel_bus": "gas_bus",
        "heat_bus": "heat_bus",
        "efficiency": gb.get("efficiency"),
        "variable_costs": gb.get("variable_costs"),
        "capacity": gb.get("capacity"),
        "mode": gb.get("mode"),
        "maximum": gb.get("maximum"),
        "capex": gb.get("capex"),
        "opex": gb.get("opex"),
        "lifetime": gb.get("lifetime"),
        "interest_rate": gb.get("interest_rate")

    }

def heat_pump_config(tech_inputs=None, input_data=None, **kwargs):

    hp = tech_inputs.get("heat_pump", {}) if tech_inputs else {}

    return {
        "type": "heat_pump",
        "electricity_bus": "electricity_bus",
        "heat_bus": "heat_bus",

        # COP handling
        "cop_mode": hp.get("cop_mode"),
        "cop_value": hp.get("cop_value"),

        # timeseries handling
        "cop_series": input_data.get("cop_series"),

        # investment / sizing
        "mode": hp.get("mode"),
        "capacity": hp.get("capacity"),
        "maximum": hp.get("maximum"),

        # economics
        "variable_costs": hp.get("variable_costs"),
        "capex": hp.get("capex"),
        "opex": hp.get("opex"),
        "lifetime": hp.get("lifetime"),
        "interest_rate": hp.get("interest_rate")
    }

TECH_CONFIG_REGISTRY = {
    "demand": demand_config,
    "heat_demand": heat_demand_config,
    "grid": grid_config,
    "grid_feedin": grid_feedin_config,
    "pv": pv_config,
    "battery": battery_config,
    "gas_import": gas_import_config,
    "gas_boiler": gas_boiler_config,
    "heat_pump": heat_pump_config
}