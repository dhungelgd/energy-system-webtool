from ui_blocks import PARAMS_BLOCK

UI_REGISTRY = {

    # electricity demand
    "demand": {
        "label": "Electricity Demand",
        "group": "Demand",

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
        "group": "Demand",

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
        "group": "Grid & fuel",
        "inputs": [
            {
                "key": "variable_costs",
                "label": "Electricity Price (€/kWh)",
                "type": "number",
                "default": 0.3,
                "step": 0.01
            }
        ]
    },

    # grid feed-in
    "grid_feedin": {
        "label": "Grid Feed-in",
        "group": "Grid & fuel",
        "inputs": [
            {
                "key": "feedin_tariff",
                "label": "Feed-in Tariff (€/kWh)",
                "type": "number",
                "default": 0.078,
                "step": 0.01,
            }
        ]
    },

    # pv system
    "pv": {
        "label": "PV System",
        "group": "Generation",
        "inputs": [
            *PARAMS_BLOCK
        ],

        "timeseries": {
            "key": "pv",
            "upload_label": "Upload PV profile timeseries data",
            "default_column": 3
        }
    },

    # wind turbine
    "wind": {
        "label": "Wind Turbine",
        "group": "Generation",
        "inputs": [
            *PARAMS_BLOCK
        ],

        "timeseries": {
            "key": "wind",
            "upload_label": "Upload wind profile timeseries data",
            "default_column": 4
        }
    },

    # battery
    "battery": {
        "label": "Battery Storage",
        "group": "Storage",
        "inputs": [
            *PARAMS_BLOCK,

            {
                "key": "efficiency_charge",
                "type": "number",
                "label": "Charge efficiency",
                "default": 0.95
            },
            {
                "key": "efficiency_discharge",
                "type": "number",
                "label": "Discharge efficiency",
                "default": 0.95
            },
            {
                "key": "loss_rate",
                "type": "number",
                "label": "Self-discharge rate (/h)",
                "default": 0.001
            },
        ]
    },

    # heat storage
    "heat_storage": {
        "label": "Heat Storage",
        "group": "Storage",
        "inputs": [
            *PARAMS_BLOCK,

            {
                "key": "efficiency_charge",
                "type": "number",
                "label": "Charge efficiency",
                "default": 0.95
            },
            {
                "key": "efficiency_discharge",
                "type": "number",
                "label": "Discharge efficiency",
                "default": 0.95
            },
            {
                "key": "loss_rate",
                "type": "number",
                "label": "Self-discharge rate (/h)",
                "default": 0.001
            },
        ]
    },


    # gas import
        "gas_import": {
        "label": "Gas Import",
        "group": "Grid & fuel",
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
        "group": "Conversion",
        "inputs": [
            *PARAMS_BLOCK,
            {
                "key": "efficiency",
                "type": "number",
                "label": "Efficiency"
            },
        ]
    },

    # heating rod (electric heater)
    "heating_rod": {
        "label": "Heating Rod",
        "group": "Conversion",
        "inputs": [
            *PARAMS_BLOCK,
            {
                "key": "efficiency",
                "type": "number",
                "label": "Efficiency (heat out / electricity in)"
            },
        ]
    },

    # CHP plant (combined heat and power, gas fired)
    "chp": {
        "label": "CHP Plant",
        "group": "Conversion",
        "inputs": [
            *PARAMS_BLOCK,
            {
                "key": "efficiency_el",
                "type": "number",
                "label": "Electrical efficiency"
            },
            {
                "key": "efficiency_th",
                "type": "number",
                "label": "Thermal efficiency"
            },
        ]
    },

    # heat pump
    "heat_pump": {
        "label": "Heat Pump",
        "group": "Conversion",

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


# order of the groups in the component selection (sidebar)
GROUP_ORDER = ["Demand", "Grid & fuel", "Generation", "Conversion", "Storage"]