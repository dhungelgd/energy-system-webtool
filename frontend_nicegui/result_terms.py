"""The words of a result, in the language of the reader.

The backend writes the labels of a result in English (kpis.py and plotting.py): the headline figures and their help
texts, the columns of the tables, the names of the components, the cost categories, the units. They are a fixed set
of texts, so they are translated from a table; a text that is not in the table is shown as it is. A test goes
through everything that the backend can write and finds what is missing (tests/test_result_terms.py).

No NiceGUI code in here, so it is easy to test.
"""

from backend.i18n import ENGLISH
from backend.plotting import NODE_NAMES

# the English text of the backend -> the key of the text in the catalogs
TERMS = {
    # headline figures
    "Annual system cost": "result.term.annual_system_cost",
    "System cost (simulated period)": "result.term.system_cost_period",
    "Electricity consumption": "result.term.electricity_consumption",
    "Peak grid import": "result.term.peak_grid_import",
    "Own generation": "result.term.own_generation",
    "Self-consumption": "result.term.self_consumption",
    "Self-sufficiency": "result.term.self_sufficiency",
    # what the headline figures mean
    "Objective of the optimization: annualised investment and fixed O&M plus energy costs, minus feed-in revenue. "
    "Negative means a net revenue.": "result.help.system_cost",
    "Electricity demand plus electricity used by heat pump and heating rod.": "result.help.electricity_consumption",
    "Electricity bought from the grid.": "result.help.grid_import",
    "Highest power drawn from the grid in a single time step.": "result.help.peak_grid_import",
    "Electricity sold to the grid.": "result.help.grid_feedin",
    "Electricity from PV, wind and CHP.": "result.help.own_generation",
    "Share of the own generation that is not fed into the grid.": "result.help.self_consumption",
    "Share of the electricity consumption that is not bought from the grid.": "result.help.self_sufficiency",
    "Heat that has to be supplied.": "result.help.heat_demand",
    # the columns of the tables
    "Item": "result.term.item",
    "Category": "result.term.category",
    "Cost (€)": "result.term.cost",
    "Component": "result.term.component",
    "Mode": "result.term.mode",
    "Capacity": "result.term.capacity",
    "Unit": "result.term.unit",
    "Annualised cost (€/a)": "result.term.annualised_cost",
    "Energy (kWh)": "result.term.energy",
    "Share (%)": "result.term.share",
    # the categories of the costs, and how a size was found
    "Investment and fixed O&M": "result.term.category_investment",
    "Energy purchase": "result.term.category_energy",
    "Revenue": "result.term.category_revenue",
    "optimized": "result.term.mode_optimized",
    "fixed (input)": "result.term.mode_fixed",
    # units (kW and kWh are the same in every language and are not in the table)
    "kW (heat)": "result.term.unit_kw_heat",
    "kW (electric)": "result.term.unit_kw_electric",
    # the names of the components and of what they are connected to (NODE_NAMES of plotting.py)
    "Grid import": "result.term.grid_import",
    "Grid feed-in": "result.term.grid_feedin",
    "Gas import": "result.term.gas_import",
    "PV": "result.term.pv",
    "Wind turbine": "result.term.wind",
    "Gas boiler": "result.term.gas_boiler",
    "Heat pump": "result.term.heat_pump",
    "Heating rod": "result.term.heating_rod",
    "CHP plant": "result.term.chp",
    "Battery": "result.term.battery",
    "Heat storage": "result.term.heat_storage",
    "Electricity demand": "result.term.demand",
    "Heat demand": "result.term.heat_demand",
    # the line of the demand in the chart of the flows
    "Demand": "result.term.demand_line",
}

# the number of decimals of a column of a table (a column that is not listed is shown as it is)
DECIMALS = {
    "Cost (€)": 0,
    "Annualised cost (€/a)": 0,
    "Energy (kWh)": 0,
    "Share (%)": 1,
    "Capacity": 1,
}

# the columns of text that are translated cell by cell
TEXT_COLUMNS = ("Item", "Category", "Component", "Mode", "Unit")


def term(tr, text):
    """The text of the backend in the language of the reader (the text itself if there is no translation)."""

    key = TERMS.get(text)

    return tr(key) if key is not None else text


def bus_label(tr, bus):
    """The name of an energy carrier (electricity, heat, gas) as the name of a tab; a carrier of its own as it is."""

    key = f"result.bus.{bus}"

    return tr(key) if tr.has(key) else bus.replace("_", " ").capitalize()


def node_label(tr, node):
    """The name of what a flow comes from or goes to (a component or a bus), from its id in the model."""

    if node in NODE_NAMES:
        return term(tr, NODE_NAMES[node])

    return bus_label(tr, node) if tr.has(f"result.bus.{node}") else node.replace("_", " ").title()


def cell_text(column, value, tr=ENGLISH):
    """One cell of a table as text: a number with the decimals of its column and the separators of the
    language, a text translated, an empty cell as a dash."""

    if value is None:
        return "-"

    if isinstance(value, str):
        return term(tr, value) if column in TEXT_COLUMNS else value

    decimals = DECIMALS.get(column)
    if decimals is None:
        return tr.number(value)

    return tr.localize(f"{value:,.{decimals}f}")


def table_for_display(table, tr=ENGLISH):
    """A Table of a result as the columns and rows of a table on the page, in the language of the reader.

    Gives (columns, rows) as ui.table wants them; a cell is looked up by the position of its column, so that
    any name of a column works.
    """

    columns = [
        {
            "name": str(position), "label": term(tr, name), "field": str(position),
            "align": "left" if name in TEXT_COLUMNS else "right",
        }
        for position, name in enumerate(table.columns)
    ]
    rows = [
        {str(position): cell_text(name, value, tr) for position, (name, value) in enumerate(zip(table.columns, row))}
        for row in table.rows
    ]

    return columns, rows