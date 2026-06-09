UI_REGISTRY = {

    # electricity demand
    "demand": {
        "label": "Electricity Demand",

        "timeseries": {
            "key": "electricity_demand",
            "upload_label": "Upload demand timeseries data",
            "default_column": 1
        },

        "inputs": [
            {
                "key": "scaling_factor",
                "type": "number",
                "label": "Scaling Factor",
                "default": 1.0,
                "step": 1.0
            }
        ]
    },

    # heating demand
    "heat_demand": {
        "label": "Heat Demand",

        "timeseries": {
            "key": "heat_demand",
            "upload_label": "Upload heat demand data",
            "default_column": 4
        },
        "inputs": [
            {
                "key": "scaling_factor",
                "type": "number",
                "label": "Scaling Factor",
                "default": 1.0,
                "step": 1.0
            }
        ]
    },

    # grid import
    "grid": {
        "label": "Electricity Grid",
        "inputs": [
            {
                "key": "variable_costs",
                "label": "Electricity Price (€/kWh)",
                "type": "number",
                "default": 0.3
            }
        ]
    },

    # grid feed-in
    "grid_feedin": {
        "label": "Grid Feed-in",
        "inputs": [
            {
                "key": "feedin_tariff",
                "label": "Feed-in Tariff (€/kWh)",
                "type": "number",
                "default": 0.078
            }
        ]
    },

    # pv system
    "pv": {
        "label": "PV System",
        "inputs": [
            {
                "key": "mode",
                "type": "selectbox",
                "label": "Mode",
                "options": ["fixed", "invest"]
            },
            {
                "key": "capacity",
                "type": "number",
                "label": "Capacity (kW)",
                "default": 10.0
            },
            {
                "key": "capex",
                "type": "number",
                "label": "CAPEX (€/kW)",
                "default": 1000.0
            },
            {
                "key": "opex",
                "type": "number",
                "label": "OPEX fraction",
                "default": 0.02
            },
            {
                "key": "lifetime",
                "type": "number",
                "label": "Lifetime (years)",
                "default": 20.0
            },
            {
                "key": "interest_rate",
                "type": "number",
                "label": "Interest rate",
                "default": 0.03
            },
            {
            "key": "maximum",
            "type": "number",
            "label": "Maximum installable capacity (kW)",
            "default": 100.0
        },
        ],

        "timeseries": {
            "key": "pv",
            "upload_label": "Upload PV profile timeseries data",
            "default_column": 0
        }
    },

    # battery
    "battery": {
        "label": "Battery Storage",
        "inputs": [
            {
                "key": "capacity",
                "type": "number",
                "label": "Capacity (kWh)",
                "default": 10.0
            },
            {
                "key": "loss_rate",
                "type": "number",
                "label": "Loss rate",
                "default": 0.01
            },
            {
                "key": "efficiency",
                "type": "number",
                "label": "Efficiency",
                "default": 0.95
            },
            {
                "key": "mode",
                "type": "selectbox",
                "label": "Mode",
                "options": ["fixed", "invest"]
            }
        ]
    },

    # gas import
        "gas_import": {
        "label": "Gas Import",
        "inputs": [
            {
                "key": "variable_costs",
                "type": "number",
                "label": "Gas Price (€/kWh)",
                "default": 0.10
            }
        ]
    },

    # gas boiler
    "gas_boiler": {
        "label": "Gas Boiler",
        "inputs": [
            {
                "key": "mode",
                "type": "selectbox",
                "label": "Mode",
                "options": ["fixed", "invest"]
            },
            {
                "key": "efficiency",
                "type": "number",
                "label": "Efficiency",
                "default": 0.9
            },
            {
                "key": "variable_costs",
                "type": "number",
                "label": "Variable Costs (€/kWh)",
                "default": 0.0
            },
            {
                "key": "capacity",
                "type": "number",
                "label": "Capacity (kW)",
                "default": 50.0
            },

            {
                "key": "capex",
                "type": "number",
                "label": "CAPEX (€/kW)",
                "default": 150.0
            },
            {
                "key": "opex",
                "type": "number",
                "label": "OPEX fraction",
                "default": 3.0
            },
            {
                "key": "lifetime",
                "type": "number",
                "label": "Lifetime (years)",
                "default": 20.0
            },
            {
                "key": "interest_rate",
                "type": "number",
                "label": "Interest rate",
                "default": 3.0
            },
            {
                "key": "maximum",
                "type": "number",
                "label": "Maximum installable capacity (kW)",
                "default": None
            }
        ]
    }
}