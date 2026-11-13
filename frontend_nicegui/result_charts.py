"""The charts of a result: the cost items, the flows of a bus over time, and the energy of a bus as a Sankey diagram.

They are made from a ScenarioResult (plain numbers), with the words in the language of the reader and the colour
of each component from palette.py (the same colour in every chart). They give Plotly figures and do not use NiceGUI,
so they are easy to test (the figures are data: traces with names, colours and values).
"""

import plotly.graph_objects as go

from backend.i18n import ENGLISH
from frontend_nicegui.chart_style import BOLD, FONT_FAMILY, TEXT_SIZE, style_figure
from frontend_nicegui.palette import BUS_COLOR, DEMAND_LINE, color_of_name, color_of_node, with_alpha
from frontend_nicegui.ranges import view_frame
from frontend_nicegui.result_terms import bus_label, node_label, term

NEGLIGIBLE = 0.005            # a cost item below half a cent is not drawn
ZERO_FLOW = 1e-9              # a flow that never rises above this is not drawn
GRID = "#E3E8ED"              # the lines of the grid behind a chart
AREA_OPACITY = 0.85           # how solid an area of the flows is drawn
PRECISION = "float32"         # the flows are sent as single precision numbers (7 digits are plenty for a power in kW):
                              # half the size of double precision, which is what makes a year of every value light

DAY_MS = 86_400_000           # a day in milliseconds (the spacing of the ticks of a time axis is measured in it)


def cost_figure(result, tr=ENGLISH):
    """A horizontal bar chart of the cost items, each in the colour of its component; revenues point to the
    left. None if there is nothing to draw."""

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
            marker_color=[color_of_name(row[item]) for row in part],
            text=[f"{tr.localize(f'{row[cost]:,.0f}')} €" for row in part],
            textposition="auto",
            textfont=dict(size=TEXT_SIZE, family=FONT_FAMILY, weight=BOLD),
            hovertemplate="%{y}<br>" + term(tr, name) + "<br>%{text}<extra></extra>",
        ))

    figure.update_layout(
        template="plotly_white",
        height=max(260, 70 * len(rows) + 120),
        xaxis_title=tr("result.chart.cost_axis"),
        yaxis_title=None,
        showlegend=False,                       # the colour says which component; the category is in the hover text
        margin=dict(l=10, r=10, t=30, b=10),
    )

    return style_figure(figure)


def time_axis(tr):
    """The time axis of the flows: it says the date, and the time as well where the ticks are closer than a day.

    The label of a tick depends on how far the visitor has zoomed in, so that a day out of a year can be read:
    ticks of less than a day have the time and the date under it, ticks of a day or more have the date. The month
    is a number, not a name. Pointing at a value says the date and the time.
    """

    date = tr("result.chart.date_format")

    return dict(
        title=tr("result.chart.time"),
        tickformatstops=[
            dict(dtickrange=[None, DAY_MS - 1], value=f"%H:%M<br>{date}"),
            dict(dtickrange=[DAY_MS, None], value=date),
        ],
        hoverformat=f"{date} %H:%M",
        gridcolor=GRID,
    )


def split_flows(columns, bus):
    """The flows of a bus by what they do: supplies to it, the use that is the demand, any other use."""

    supply = sorted(c for c in columns if c.endswith(f"-->{bus}"))
    uses = [c for c in columns if c.startswith(f"{bus}-->")]
    demand = [c for c in uses if "demand" in c.lower()]
    other = sorted(c for c in uses if c not in demand)

    return supply, demand, other


def flows_figure(bus, summary, tr=ENGLISH, view=None):
    """The flows of a bus over time (kW): what supplies it stacked upwards, other uses (charging, feed-in,
    conversion) stacked downwards, and the demand as a black line. None if the result has no hourly flows.

        `view` is (mode, position) for a window of time (see ranges.py: 'day', 'week', 'month', 'all' and which
    window); without it every time step is drawn. A flow that is zero all the time is left out: it would only
    fill the legend. A bus through which nothing flows gives a figure without traces (the page says so in words
    instead of drawing an empty chart).
    """

    if summary.flows is None or not summary.flows.columns:
        return None

    mode = None if view is None else view[0]
    if view is None:
        frame = summary.flows.to_frame(with_end_row=False)
    else:
        frame, _ = view_frame(summary.flows, mode, view[1])
    supply, demand, other = split_flows(frame.columns, bus)

    # every value has its time from a start and a step: a time stamp for each value would be most of what is sent
    start = frame.index[0].to_pydatetime()
    step = summary.flows.step_hours * 3_600_000  # milliseconds

    def values(series):
        return series.to_numpy(dtype=PRECISION)

    def drawn(columns):
        return [c for c in columns if frame[c].abs().max() > ZERO_FLOW]

    def area(column, node, series, group):
        color = color_of_node(node)
        name = node_label(tr, node)
        return go.Scatter(
            x0=start, dx=step, y=values(series), mode="lines", name=name, stackgroup=group,
            line=dict(width=0.6, color=color), fillcolor=with_alpha(color, AREA_OPACITY),
            hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.2f}} kW<extra></extra>",
        )

    figure = go.Figure()

    for column in drawn(supply):
        figure.add_trace(area(column, column.split("-->")[0], frame[column], "supply"))

    demand = drawn(demand)
    if demand:
        name = term(tr, "Demand")
        figure.add_trace(go.Scatter(
            x0=start, dx=step, y=values(frame[demand].sum(axis=1)), mode="lines", name=name,
            line=dict(color=DEMAND_LINE, width=2.5),
            hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.2f}} kW<extra></extra>",
        ))

    for column in drawn(other):
        figure.add_trace(area(column, column.split("-->")[1], -frame[column], "use"))

    figure.update_layout(
        template="plotly_white",
        height=450,
        xaxis=time_axis(tr),
        yaxis=dict(title=tr("result.chart.power"), gridcolor=GRID, zerolinecolor="#8795A3"),
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.22, title_text=""),
        margin=dict(l=10, r=10, t=30, b=10),
    )

    return style_figure(figure)


def sankey_figure(bus, summary, tr=ENGLISH):
    """What supplies a bus and what uses it, over the whole period (kWh), as a Sankey diagram: the nodes and the
    bands in the colours of the components. None if no energy flows through the bus."""

    def entries(table):
        if "Component" not in table.columns or "Energy (kWh)" not in table.columns:
            return []
        name, energy = table.columns.index("Component"), table.columns.index("Energy (kWh)")
        return [(row[name], row[energy]) for row in table.rows if row[energy] and row[energy] > 0]

    supplies, uses = entries(summary.supply), entries(summary.use)
    if not supplies and not uses:
        return None

    def kwh(value):
        return f"{tr.localize(f'{value:,.0f}')} kWh"

    # the value is on every node, so every band can be read without pointing at it (a node has exactly one band)
    total = sum(energy for _, energy in supplies) or sum(energy for _, energy in uses)
    labels = (
        [f"{term(tr, name)}, {kwh(energy)}" for name, energy in supplies]
        + [f"{bus_label(tr, bus)}, {kwh(total)}"]
        + [f"{term(tr, name)}, {kwh(energy)}" for name, energy in uses]
    )
    middle = len(supplies)
    sources = list(range(len(supplies))) + [middle] * len(uses)
    targets = [middle] * len(supplies) + [middle + 1 + n for n in range(len(uses))]
    values = [energy for _, energy in supplies] + [energy for _, energy in uses]
    node_colors = [color_of_name(n) for n, _ in supplies] + [BUS_COLOR] + [color_of_name(n) for n, _ in uses]
    link_colors = [with_alpha(color_of_name(n), 0.35) for n, _ in supplies + uses]

    figure = go.Figure(go.Sankey(
        node=dict(pad=18, thickness=22, line=dict(color="white", width=1), label=labels, color=node_colors),
        link=dict(source=sources, target=targets, value=values, color=link_colors),
        textfont=dict(size=TEXT_SIZE, family=FONT_FAMILY, weight=BOLD),
    ))
    figure.update_layout(
        title=tr("result.chart.sankey_title", bus=bus_label(tr, bus)),
        height=max(380, 64 * max(len(supplies), len(uses)) + 160),
        margin=dict(l=10, r=10, t=60, b=10),
    )

    return style_figure(figure)