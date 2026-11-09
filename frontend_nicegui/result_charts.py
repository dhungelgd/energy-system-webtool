"""The charts of a result: the cost items, the flows of a bus over time, and the energy of a bus as a Sankey diagram.

They are made from a ScenarioResult (plain numbers), with the words in the language of the reader. They give
Plotly figures and do not use NiceGUI, so they are easy to test (the figures are data: traces with names and values).
"""

import plotly.graph_objects as go

from backend.kpis import CATEGORY_ENERGY, CATEGORY_INVEST, CATEGORY_REVENUE
from backend.i18n import ENGLISH
from frontend_nicegui.result_terms import bus_label, node_label, term

# one colour for each category of the costs (the family of the system graph: blue, orange, teal)
CATEGORY_COLORS = {
    CATEGORY_INVEST: "#1F77B4",
    CATEGORY_ENERGY: "#E8873A",
    CATEGORY_REVENUE: "#2A9D8F",
}
OTHER_COLOR = "#9AA5B1"

NEGLIGIBLE = 0.005            # a cost item below half a cent is not drawn
ZERO_FLOW = 1e-9              # a flow that never rises above this is not drawn


def cost_figure(result, tr=ENGLISH):
    """A horizontal bar chart of the cost items; revenues point to the left. None if there is nothing to draw."""

    table = result.cost_breakdown
    if not {"Item", "Category", "Cost (€)"} <= set(table.columns):
        return None

    item, category, cost = (table.columns.index(name) for name in ("Item", "Category", "Cost (€)"))
    rows = sorted(
        (row for row in table.rows if row[cost] is not None and abs(row[cost]) > NEGLIGIBLE),
        key=lambda row: row[cost],
    )
    if not rows:
        return None

    figure = go.Figure()
    for name in dict.fromkeys(row[category] for row in rows):                 # in the order of first appearance
        part = [row for row in rows if row[category] == name]
        figure.add_trace(go.Bar(
            y=[term(tr, row[item]) for row in part],
            x=[row[cost] for row in part],
            name=term(tr, name),
            orientation="h",
            marker_color=CATEGORY_COLORS.get(name, OTHER_COLOR),
            text=[f"{tr.localize(f'{row[cost]:,.0f}')} €" for row in part],
            textposition="auto",
            hovertemplate="%{y}<br>%{text}<extra></extra>",
        ))

    figure.update_layout(
        template="plotly_white",
        height=max(260, 70 * len(rows) + 120),
        xaxis_title=tr("result.chart.cost_axis"),
        yaxis_title=None,
        legend_title_text=None,
        margin=dict(l=10, r=10, t=30, b=10),
    )

    return figure


def _split(columns, bus):
    """The flows of a bus by what they do: supplies to it, the use that is the demand, any other use."""

    supply = sorted(c for c in columns if c.endswith(f"-->{bus}"))
    uses = [c for c in columns if c.startswith(f"{bus}-->")]
    demand = [c for c in uses if "demand" in c.lower()]
    other = sorted(c for c in uses if c not in demand)

    return supply, demand, other


def flows_figure(bus, summary, tr=ENGLISH):
    """The flows of a bus over time (kW): what supplies it stacked upwards, other uses (charging, feed-in,
    conversion) stacked downwards, and the demand as a black line. None if the result has no hourly flows.

    A flow that is zero all the time is left out: it would only fill the legend. A bus through which nothing
    flows gives a figure without traces (the page says so in words instead of drawing an empty chart).
    """

    if summary.flows is None or not summary.flows.columns:
        return None

    frame = summary.flows.to_frame(with_end_row=False)
    supply, demand, other = _split(frame.columns, bus)

    def drawn(columns):
        return [c for c in columns if frame[c].abs().max() > ZERO_FLOW]

    figure = go.Figure()
    unit = "kW"

    for column in drawn(supply):
        name = node_label(tr, column.split("-->")[0])
        figure.add_trace(go.Scatter(
            x=frame.index, y=frame[column], mode="lines", name=name, stackgroup="supply",
            hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.2f}} {unit}<extra></extra>",
        ))

    demand = drawn(demand)
    if demand:
        total = frame[demand].sum(axis=1)
        name = term(tr, "Demand")
        figure.add_trace(go.Scatter(
            x=frame.index, y=total, mode="lines", name=name, line=dict(color="black", width=3),
            hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.2f}} {unit}<extra></extra>",
        ))

    for column in drawn(other):
        name = node_label(tr, column.split("-->")[1])
        figure.add_trace(go.Scatter(
            x=frame.index, y=-frame[column], mode="lines", name=name, stackgroup="use",
            hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.2f}} {unit}<extra></extra>",
        ))

    figure.update_layout(
        template="plotly_white",
        height=450,
        xaxis_title=tr("result.chart.time"),
        yaxis_title=tr("result.chart.power"),
        hovermode="x unified",
        legend_title_text=None,
        margin=dict(l=10, r=10, t=30, b=10),
    )

    return figure


def sankey_figure(bus, summary, tr=ENGLISH):
    """What supplies a bus and what uses it, over the whole period (kWh), as a Sankey diagram. None if no energy
    flows through the bus."""

    def entries(table):
        if "Component" not in table.columns or "Energy (kWh)" not in table.columns:
            return []
        name, energy = table.columns.index("Component"), table.columns.index("Energy (kWh)")
        return [(term(tr, row[name]), row[energy]) for row in table.rows if row[energy] and row[energy] > 0]

    supplies, uses = entries(summary.supply), entries(summary.use)
    if not supplies and not uses:
        return None

    labels = [name for name, _ in supplies] + [bus_label(tr, bus)] + [name for name, _ in uses]
    middle = len(supplies)
    sources = list(range(len(supplies))) + [middle] * len(uses)
    targets = [middle] * len(supplies) + [middle + 1 + n for n in range(len(uses))]
    values = [energy for _, energy in supplies] + [energy for _, energy in uses]

    figure = go.Figure(go.Sankey(
        node=dict(pad=25, thickness=30, line=dict(color="white", width=2), label=labels),
        link=dict(source=sources, target=targets, value=values),
    ))
    figure.update_layout(
        title=tr("result.chart.sankey_title", bus=bus_label(tr, bus)),
        font=dict(size=14),
        height=max(380, 60 * max(len(supplies), len(uses)) + 160),
        margin=dict(l=10, r=10, t=60, b=10),
    )

    return figure