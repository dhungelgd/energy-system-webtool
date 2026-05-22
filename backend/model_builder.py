import pandas as pd
from oemof.solph import EnergySystem, Bus, Flow
import oemof.solph.components as cmp


def build_model(config: dict):

    es = EnergySystem()

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

            index = pd.RangeIndex(8760)

            demand_series = pd.Series([1] * 8760, index=index)

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