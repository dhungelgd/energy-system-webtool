from pathlib import Path
import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
import plotly.graph_objects as go
import numpy as np

# plot energy system graph
def plot_energy_system_graph(energy_system, selected_techs=None):

    graph = create_nx_graph(energy_system)

    plt.figure(figsize=(12, 6))

    pos = nx.spring_layout(graph, seed=42, k=2.0)

    nx.draw(
        graph,
        pos,
        with_labels=True,

        node_size=5000,
        node_color="#90EE90",
        edge_color="black",

        font_size=14,
        font_weight="bold",

        width=2,

        arrows=True,
        arrowstyle='-|>',
        arrowsize=20
    )

    #plt.tight_layout()

    return plt.gcf()

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