from ui_blocks import PARAMS_BLOCK

UI_REGISTRY = {

    # electricity demand
    "demand": {
        "label": "Electricity Demand",

        "timeseries": {
            "key": "electricity_demand",
            "upload_label": "Upload demand timeseries data",
            "default_column": 2
        },

        "inputs": [
            {
                "key": "scaling_factor",
                "type": "number",
                "label": "Scaling Factor",
                "default": 30000.0,
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
            "default_column": 1
        },
        "inputs": [
            {
                "key": "scaling_factor",
                "type": "number",
                "label": "Scaling Factor",
                "default": 90000.0,
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
            *PARAMS_BLOCK
        ],

        "timeseries": {
            "key": "pv",
            "upload_label": "Upload PV profile timeseries data",
            "default_column": 3
        }
    },

    # # battery
    # "battery": {
    #     "label": "Battery Storage",
    #     "inputs": [
    #         *PARAMS_BLOCK
    #     ]
    # },

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
            *PARAMS_BLOCK
        ]
    },

    # heat pump
    "heat_pump": {
        "label": "Heat Pump",

        "inputs": [
            {
                "key": "cop_mode",
                "type": "selectbox",
                "label": "COP mode",
                "options": ["constant", "timeseries"]
            },

            {
                "key": "cop_value",
                "type": "number",
                "label": "COP (constant)",
                "visible_if": {"cop_mode": "constant"}
            },

            {
                "key": "cop_series",
                "type": "timeseries",
                "label": "COP profile",
                "visible_if": {"cop_mode": "timeseries"}
            },

            *PARAMS_BLOCK
        ],

            "timeseries": {
                "key": "cop_series",
                "upload_label": "Upload COP timeseries data",
                "default_column": 6
            }
    }
}