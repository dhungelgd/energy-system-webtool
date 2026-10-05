from pathlib import Path
import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
import plotly.graph_objects as go
import numpy as np

# ---------------------------------------------------------------------------
# energy system graph
#
# Layered diagram, read from left to right (fuel -> conversion -> buses -> use).
# The layout is computed from the model itself, so new technologies need no
# changes here. Only the look (colours, names) is defined in the tables below.
# ---------------------------------------------------------------------------

# FIXED colour per energy carrier: used for the bus and for every arrow
# that is connected to it (key = bus label)
CARRIER_COLORS = {
    "electricity": "#1F77B4",   # blue
    "heat": "#D62728",          # red
    "gas": "#8C6D31",           # brown
}
DEFAULT_COLOR = "#9AA5B1"

# colour of each component (key = component label in the model)
COMPONENT_COLORS = {
    "grid_import": "#6B7785",
    "grid_feedin": "#A3AEBB",
    "gas_import": "#C9A24B",
    "pv": "#F2B705",
    "wind": "#4CC9B0",
    "gas_boiler": "#E8873A",
    "heat_pump": "#9B5DE5",
    "heating_rod": "#F28482",
    "chp": "#2A9D8F",
    "battery": "#7FB069",
    "heat_storage": "#F4A6A0",
    "demand": "#B8D4EA",
    "heat_demand": "#F5C6C2",
}

# readable names for the diagram
NODE_NAMES = {
    "grid_import": "Grid import",
    "grid_feedin": "Grid feed-in",
    "gas_import": "Gas import",
    "pv": "PV",
    "wind": "Wind turbine",
    "gas_boiler": "Gas boiler",
    "heat_pump": "Heat pump",
    "heating_rod": "Heating rod",
    "chp": "CHP plant",
    "battery": "Battery",
    "heat_storage": "Heat storage",
    "demand": "Electricity demand",
    "heat_demand": "Heat demand",
}

# marker symbol per node kind
KIND_SYMBOLS = {
    "bus": "square",
    "source": "triangle-right",
    "sink": "triangle-right",
    "converter": "diamond",
    "storage": "hexagon",
}


def _node_kind(node):
    from oemof.solph import Bus
    from oemof.solph.components import Converter, GenericStorage, Sink, Source

    if isinstance(node, Bus):
        return "bus"
    if isinstance(node, GenericStorage):
        return "storage"
    if isinstance(node, Converter):
        return "converter"
    if isinstance(node, Source):
        return "source"
    if isinstance(node, Sink):
        return "sink"
    return "converter"


def _layers(kinds, edges):
    """Column index for every node (longest path from the left)."""

    # edges out of storages go back to the bus -> ignore them for the ordering
    forward = [(a, b) for a, b in edges if kinds[a] != "storage"]

    layer = {n: 0 for n in kinds}
    for _ in range(len(kinds)):
        changed = False
        for a, b in forward:
            if layer[b] < layer[a] + 1:
                layer[b] = layer[a] + 1
                changed = True
        if not changed:
            break

    # sources sit directly in front of what they feed
    for node, kind in kinds.items():
        if kind == "source":
            targets = [layer[b] for a, b in forward if a == node]
            if targets:
                layer[node] = min(targets) - 1

    # everything that only consumes (demand, export, storage) goes to the last column
    last = max(layer.values())
    for node, kind in kinds.items():
        if kind in ("sink", "storage"):
            layer[node] = last

    # keep layer numbers compact and starting at 0
    used = sorted(set(layer.values()))
    rank = {value: i for i, value in enumerate(used)}
    return {n: rank[v] for n, v in layer.items()}


def _order(layer, edges):
    """Vertical position inside each column.

    Sweeps left-to-right and right-to-left and puts every node at the average
    height of its neighbours, which keeps the number of crossing arrows low.
    """

    columns = {}
    for node, col in layer.items():
        columns.setdefault(col, []).append(node)
    order = sorted(columns)

    # start: sorted by name
    ypos = {}
    for col in order:
        for i, node in enumerate(sorted(columns[col])):
            ypos[node] = float(i)

    left = {n: [] for n in layer}
    right = {n: [] for n in layer}
    for a, b in edges:
        if layer[a] < layer[b]:
            left[b].append(a); right[a].append(b)
        elif layer[a] > layer[b]:
            left[a].append(b); right[b].append(a)

    def place(col, neighbours):
        def centre(node):
            values = [ypos[m] for m in neighbours[node]]
            return sum(values) / len(values) if values else ypos[node]

        ordered = sorted(columns[col], key=lambda n: (centre(n), n))
        count = len(ordered)
        for i, node in enumerate(ordered):
            ypos[node] = float(i) - (count - 1) / 2   # centred around 0

    for _ in range(6):
        for col in order[1:]:
            place(col, left)
        for col in reversed(order[:-1]):
            place(col, right)
    for col in order[1:]:          # finish with a forward sweep
        place(col, left)

    return ypos


def _polygon(kind, x, y):
    """Outline of a node (data coordinates).

    bus        small filled circle
    source     trapezium, wide side at the bottom
    sink       trapezium, wide side at the top
    converter  rectangle
    storage    square
    """
    import math

    if kind == "bus":
        r = 0.22
        pts = [(x + r * math.cos(a * math.pi / 18), y + r * math.sin(a * math.pi / 18)) for a in range(37)]
    elif kind == "converter":                      # rectangle (wider than high)
        w, h = .42, .30
        pts = [(x - w, y - h), (x + w, y - h), (x + w, y + h), (x - w, y + h), (x - w, y - h)]
    elif kind == "storage":                        # square (same width and height)
        q = .30
        pts = [(x - q, y - q), (x + q, y - q), (x + q, y + q), (x - q, y + q), (x - q, y - q)]
    else:                                          # source / sink: trapezium
        wide, narrow, h = .44, .24, .3
        top, bottom = (narrow, wide) if kind == "source" else (wide, narrow)
        # y axis points downwards, so "top" is y - h
        pts = [(x - top, y - h), (x + top, y - h), (x + bottom, y + h), (x - bottom, y + h), (x - top, y - h)]
    return [p[0] for p in pts], [p[1] for p in pts]


def plot_energy_system_graph(energy_system, selected_techs=None):
    """Interactive diagram of the energy system (Plotly figure), coloured by
    energy carrier and drawn with the node shapes of the oemof documentation."""

    nodes = {str(n.label): n for n in energy_system.nodes}

    edges = []
    for node in energy_system.nodes:
        for target in node.outputs:
            edges.append((str(node.label), str(target.label)))

    # buses without any connection (e.g. the gas bus in an all-electric system)
    connected = {n for edge in edges for n in edge}
    kinds = {name: _node_kind(node) for name, node in nodes.items() if name in connected}
    edges = [(a, b) for a, b in edges if a in kinds and b in kinds]

    fig = go.Figure()
    if not kinds:
        return fig

    layer = _layers(kinds, edges)
    ypos = _order(layer, edges)
    gap = 1.25

    def xy(name):
        return layer[name] * 2.0, ypos[name] * gap

    # buses and arrows: fixed carrier colour; components: their own colour
    carrier_colors = {n: CARRIER_COLORS.get(n, DEFAULT_COLOR) for n, k in kinds.items() if k == "bus"}
    colors = {
        n: carrier_colors[n] if k == "bus" else COMPONENT_COLORS.get(n, DEFAULT_COLOR)
        for n, k in kinds.items()
    }

    # connections (one arrow; two arrowheads if the flow can go both ways)
    # an arrow that would run through another node is bent around it
    points = {n: xy(n) for n in kinds}

    def bend(a, b):
        (x0, y0), (x1, y1) = points[a], points[b]
        dx, dy = (x1 - x0) * 75, (y1 - y0) * 100          # rough pixel scale
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        push = 0.0
        for n, (px, py) in points.items():
            if n in (a, b):
                continue
            ex, ey = (px - x0) * 75, (py - y0) * 100
            t = (ex * dx + ey * dy) / length ** 2
            if not 0.05 < t < 0.95:
                continue
            side = (ex * dy - ey * dx) / length            # signed distance to the line
            if abs(side) < 45:
                push += -1.0 if side >= 0 else 1.0
        if push == 0:
            return None
        offset = 70 * (1 if push > 0 else -1)
        nx_, ny_ = -dy / length, dx / length                # unit normal (pixels)
        mx, my = (x0 + x1) / 2 + nx_ * offset / 75, (y0 + y1) / 2 + ny_ * offset / 100
        return mx, my

    drawn = set()
    for a, b in edges:
        if (a, b) in drawn:
            continue
        both = (b, a) in edges
        drawn.add((a, b))
        drawn.add((b, a))

        x0, y0 = points[a]
        x1, y1 = points[b]
        # edge colour: the bus it touches
        bus = a if kinds[a] == "bus" else b if kinds[b] == "bus" else None
        color = carrier_colors.get(bus, DEFAULT_COLOR)

        control = bend(a, b)
        if control is None:
            tail = (x0, y0)
        else:
            cx, cy = control
            steps = [i / 24 for i in range(25)]
            xs = [(1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1 for t in steps]
            ys = [(1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1 for t in steps]
            fig.add_trace(go.Scatter(
                x=xs[3:-3], y=ys[3:-3], mode="lines", hoverinfo="skip", showlegend=False,
                line=dict(color=color, width=2.5),
            ))
            tail = (xs[-4], ys[-4])        # the arrowhead continues the curve

        # arrowhead at the target
        fig.add_annotation(
            x=x1, y=y1, ax=tail[0], ay=tail[1], xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2.5,
            arrowcolor=color, standoff=26,
            startstandoff=26 if control is None else 0,
            startarrowhead=0, opacity=0.9,
        )
        # flows that can go both ways (storages): second arrowhead at the start
        if both:
            if control is None:     # short stub, so the line itself is not drawn twice
                back = (x0 + (x1 - x0) * 0.25, y0 + (y1 - y0) * 0.25)
            else:
                back = (xs[4], ys[4])
            fig.add_annotation(
                x=x0, y=y0, ax=back[0], ay=back[1],
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2.5,
                arrowcolor=color, standoff=26, opacity=0.9,
            )

    # nodes (oemof shapes, filled with the carrier colour)
    for kind in ("source", "sink", "converter", "storage", "bus"):
        for n in [n for n, k in kinds.items() if k == kind]:
            px, py = xy(n)
            xs, ys = _polygon(kind, px, py)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", fill="toself",
                fillcolor=colors[n],
                line=dict(color="#2B3A47", width=2),
                hovertext=f"{NODE_NAMES.get(n, n)} ({kind})", hoverinfo="text",
                showlegend=False,
            ))

    # labels (drawn last, on a light background so arrows never cut through the text)
    for name, kind in kinds.items():
        x, y = xy(name)
        fig.add_annotation(
            x=x, y=y, xref="x", yref="y", showarrow=False,
            text=f"<b>{NODE_NAMES.get(name, name.replace('_', ' ').capitalize())}</b>",
            yshift=-42 if kind != "bus" else 30,
            font=dict(size=13, color="#1F2D3A"),
            bgcolor="rgba(255,255,255,0.85)", borderpad=2,
        )

    columns = max(layer.values()) + 1
    rows = max(abs(y) for y in ypos.values()) * gap * 2 + 2
    x_range = [-1, columns * 2 - 1]
    y_range = [-rows / 2 - 0.6, rows / 2 + 0.6]

    fig.update_xaxes(visible=False, range=x_range, constrain="domain")
    # equal scaling on both axes so that the circles stay round
    fig.update_yaxes(visible=False, range=y_range[::-1], scaleanchor="x", scaleratio=1, constrain="domain")
    fig.update_layout(
        height=max(380, int((y_range[1] - y_range[0]) / (x_range[1] - x_range[0]) * 1000) + 40),
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    return fig

def apply_publication_style(ax):

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    ax.spines['left'].set_linewidth(3.0)
    ax.spines['bottom'].set_linewidth(3.0)

    ax.tick_params(axis='both',
                   which='major',
                   labelsize=11,
                   width=3,
                   length=7)

    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontweight('bold')

    ax.grid(axis='y', linestyle='--', alpha=0.3)

# plot energy flows
def plot_energy_flows(flows, bus_name, start=None, end=None):

    # select time range
    if start is not None and end is not None:
        flows = flows.loc[start:end]

    # identify supply and demand
    supply_cols = [c for c in flows.columns if c.endswith(f"-->{bus_name}")]
    demand_cols = [c for c in flows.columns if c.startswith(f"{bus_name}-->")]

    bus_outflows = [c for c in flows.columns if c.startswith(f"{bus_name}-->")]
    demand_cols = [c for c in bus_outflows if "demand" in c.lower()]
    sink_cols = [c for c in bus_outflows if c not in demand_cols]

    if not supply_cols and not demand_cols:
        raise ValueError(f"No flows found for bus '{bus_name}'")

    # sort supply for cleaner plots
    supply_cols = sorted(supply_cols)
    sink_cols = sorted(sink_cols)

    # stack
    x = flows.index

    fig, ax = plt.subplots(figsize=(12, 6))

    # positive supply stack
    positive_baseline = np.zeros(len(flows))

    for col in supply_cols:
        values = flows[col].values

        ax.fill_between(
            x,
            positive_baseline,
            positive_baseline + values,
            step="pre",
            label=col.replace(f"_{bus_name}", "")
        )

        positive_baseline += values

    # demand line
    if demand_cols:
        demand = flows[demand_cols].sum(axis=1)

        ax.step(
            x,
            demand,
            where="pre",
            color="black",
            linewidth=2,
            label="Demand"
        )

    # negative stack
    negative_baseline = np.zeros(len(flows))

    for col in sink_cols:
        values = flows[col].values

        label = (
            col.replace(f"{bus_name}-->", "")
            .replace("_", " ")
            .title()
        )

        ax.fill_between(
            x,
            negative_baseline,
            negative_baseline - values,
            step="pre",
            label=label
        )

        negative_baseline -= values

    apply_publication_style(ax)
    ax.set_xlabel("Time", fontsize=14, fontweight="bold")
    ax.set_ylabel("Power (kW)", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend()

    fig.autofmt_xdate()
    fig.tight_layout()

    return fig


def plot_energy_flows_plotly(flows, bus_name, start=None, end=None):

    # -----------------------------------
    # Select time range
    # -----------------------------------
    if start is not None and end is not None:
        flows = flows.loc[start:end]

    # -----------------------------------
    # Incoming flows -> supply
    # -----------------------------------
    supply_cols = [
        c for c in flows.columns
        if c.endswith(f"-->{bus_name}")
    ]

    # -----------------------------------
    # Outgoing flows
    # -----------------------------------
    bus_outflows = [
        c for c in flows.columns
        if c.startswith(f"{bus_name}-->")
    ]

    # actual demand
    demand_cols = [
        c for c in bus_outflows
        if "demand" in c.lower()
    ]

    # charging, export, feed-in, etc.
    sink_cols = [
        c for c in bus_outflows
        if c not in demand_cols
    ]

    if not supply_cols and not demand_cols and not sink_cols:
        raise ValueError(
            f"No flows found for bus '{bus_name}'"
        )

    supply_cols = sorted(supply_cols)
    sink_cols = sorted(sink_cols)

    fig = go.Figure()

    # ===================================
    # Positive supply stack
    # ===================================
    for col in supply_cols:

        label = (
            col.replace(f"-->{bus_name}", "")
            .replace("_", " ")
            .title()
        )

        fig.add_trace(
            go.Scatter(
                x=flows.index,
                y=flows[col],
                mode="lines",
                name=label,
                stackgroup="positive",
                hovertemplate=f"{label}<br>%{{x}}<br>%{{y:.2f}} kW<extra></extra>"
            )
        )

    # ===================================
    # Demand line
    # ===================================
    if demand_cols:

        demand = flows[demand_cols].sum(axis=1)

        fig.add_trace(
            go.Scatter(
                x=flows.index,
                y=demand,
                mode="lines",
                name="Demand",
                line=dict(color="black", width=3),
                hovertemplate="Demand<br>%{x}<br>%{y:.2f} kW<extra></extra>"
            )
        )

    # ===================================
    # Negative stack
    # ===================================
    for col in sink_cols:

        label = (
            col.replace(f"{bus_name}-->", "")
            .replace("_", " ")
            .title()
        )

        fig.add_trace(
            go.Scatter(
                x=flows.index,
                y=-flows[col],
                mode="lines",
                name=label,
                stackgroup="negative",
                hovertemplate=f"{label}<br>%{{x}}<br>%{{y:.2f}} kW<extra></extra>"
            )
        )

    # ===================================
    # Layout
    # ===================================
    fig.update_layout(

        template="plotly_white",

        width=1200,
        height=700,

        title=dict(
            text= "", # f"{bus_name.replace('_', ' ').title()} Energy Balance",
            font=dict(size=22, family="Arial Black", color="black")
        ),

        # X-axis styling
        xaxis=dict(
            title=dict(
                text="Time",
                font=dict(size=18, family="Arial Black", color="black")
            ),
            tickfont=dict(size=16, family="Arial Black", color="black"),
            showline=True,
            linewidth=4,
            linecolor="black",
            mirror=False,
        ),

        # Y-axis styling
        yaxis=dict(
            title=dict(
                text="Power (kW)",
                font=dict(size=18, family="Arial Black", color="black")
            ),
            tickfont=dict(size=16, family="Arial Black", color="black"),
            showline=True,
            linewidth=4,
            linecolor="black",
            mirror=False,
        ),

        # grid + interaction
        hovermode="x unified",

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(size=12)
        )
    )

    return fig

def create_sankey(flow_sums):

    nodes = set()

    for flow in flow_sums.keys():
        source, target = flow.split("-->")
        nodes.add(source)
        nodes.add(target)

    nodes = list(nodes)

    node_index = {
        node: idx
        for idx, node in enumerate(nodes)
    }

    sources = []
    targets = []
    values = []

    for flow, value in flow_sums.items():

        source, target = flow.split("-->")

        if value <= 0:
            continue

        sources.append(node_index[source])
        targets.append(node_index[target])
        values.append(value)

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=25,
                    thickness=35,
                    line=dict(
                        color="white",
                        width=2
                    ),
                    label=nodes
                ),

                link=dict(
                    source=sources,
                    target=targets,
                    value=values
                )
            )
        ]
    )

    fig.update_layout(
        title="Annual Energy Flow Sankey Diagram",
        font=dict(
            size=14
        ),
        height=700
    )

    return fig