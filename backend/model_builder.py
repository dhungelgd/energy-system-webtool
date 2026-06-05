from oemof.solph import EnergySystem, Bus
from backend.oemof_components import TECH_MAPPING

def build_model(config, input_data):

    #create a timeindex
    timeindex = input_data["timeindex"]

    # initialize the energy system
    es = EnergySystem(timeindex=timeindex)

    # create bus
    bus_map = {}
    for bus_id, bus_data in config["buses"].items():
        bus = Bus(label=bus_data["label"])
        es.add(bus)
        bus_map[bus_id] = bus

    # components
    for tech_id, tech in config["technologies"].items():

        tech_type = tech["type"]

        if tech_type not in TECH_MAPPING:
            raise ValueError(f"Unknown technology type: {tech_type}")

        TECH_MAPPING[tech_type](
            es=es,
            buses=bus_map,
            cfg=tech,
            input_data=input_data
        )

    return es