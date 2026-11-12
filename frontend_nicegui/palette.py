"""The colours of the components: one colour for each, the same in every chart (flows, costs, Sankey diagram) and
on the tiles of the optimised system.

The colours are for the ids of the model (the names of NODE_NAMES: grid_import, pv, heat_pump ...); a name that
the backend writes for people ("Heat pump") is found through the same table. No NiceGUI code in here.
"""

from backend.plotting import NODE_NAMES

GREY = "#9AA5B1"                # what the palette does not know

COLORS = {
    "grid_import": "#7F8EA0",
    "grid_feedin": "#4C9BD8",
    "gas_import": "#A58BD6",
    "pv": "#C98200",
    "wind": "#1F6FB2",
    "gas_boiler": "#6B4FA3",
    "heating_rod": "#E58A6B",
    "chp": "#B04FA0",
    "heat_pump": "#D9482B",
    "battery": "#2A9D6B",
    "heat_storage": "#CF6A27",
    "demand": "#14202B",
    "heat_demand": "#14202B",
}

BUS_COLOR = "#44525F"           # the node of an energy carrier in the Sankey diagram (it is not a component)
DEMAND_LINE = "#14202B"         # the line of the demand in the chart of the flows

BY_NAME = {name: key for key, name in NODE_NAMES.items()}


def color_of_node(node):
    """The colour of a component by its id in the model ('pv', 'heat_pump'); grey for what is not known."""

    return COLORS.get(node, GREY)


def color_of_name(name):
    """The colour of a component by the name that the backend writes for people ('Heat pump')."""

    return color_of_node(BY_NAME.get(name))


def with_alpha(color, alpha):
    """'#RRGGBB' as 'rgba(r, g, b, alpha)' (a Sankey link and an area are drawn see-through)."""

    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))

    return f"rgba({red}, {green}, {blue}, {alpha})"