import pandas as pd
from oemof.solph import EnergySystem, Bus, Flow
import oemof.solph.components as cmp
import numpy as np
import pandas as pd


def build_model(config, input_data):

    #create a timeindex
    timeindex = pd.date_range(start="2021-01-01", periods=8760, freq="h")

    es = EnergySystem(timeindex=timeindex)

    # create bus
    bus_map = {}

    for bus_id, bus_data in config["buses"].items():
        bus = Bus(label=bus_data["label"])
        es.add(bus)
        bus_map[bus_id] = bus

    # technologies
    for tech_id, tech in config["technologies"].items():

        # demand
        if tech["type"] == "demand":

            profile_data = input_data["electricity_demand"]

            demand_series = pd.Series(
                profile_data,
                index=timeindex[:len(profile_data)]
            )

            es.add(
                cmp.Sink(
                    label=tech_id,
                    inputs={
                        bus_map[tech["bus"]]: Flow(
                            fix=demand_series,
                            nominal_value=tech["scaling_factor"]
                        )
                    }
                )
            )

        # grid
        elif tech["type"] == "grid":

            es.add(
                cmp.Source(
                    label=tech_id,
                    outputs={
                        bus_map[tech["bus"]]: Flow(
                            variable_costs=tech["variable_costs"]
                        )
                    }
                )
            )

    return es