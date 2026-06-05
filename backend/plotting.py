from pathlib import Path
import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
import plotly.graph_objects as go
import numpy as np

# plot energy system graph
def plot_energy_system_graph(energy_system):

    graph = create_nx_graph(energy_system)
    plt.figure(figsize=(10, 6))
    pos = nx.spring_layout(graph, seed=42)
    nx.draw(graph, pos, with_labels=True, node_size=2000, node_color="lightblue", edge_color="gray",
            font_size=9, font_weight="bold")
    return plt.gcf()

# plot energy flows
def plot_energy_flows(flows, bus_name, start=None, end=None):

    # select time range
    if start is not None and end is not None:
        flows = flows.loc[start:end]

    # identify supply and demand
    supply_cols = [c for c in flows.columns if c.endswith(f"-->{bus_name}")]
    demand_cols = [c for c in flows.columns if c.startswith(f"{bus_name}-->")]

    if not supply_cols and not demand_cols:
        raise ValueError(f"No flows found for bus '{bus_name}'")

    # sort supply for cleaner plots
    supply_cols = sorted(supply_cols)

    # stack
    x = flows.index
    baseline = np.zeros(len(flows))

    fig, ax = plt.subplots(figsize=(12, 6))

    # supply stack
    for col in supply_cols:
        values = flows[col].values

        ax.fill_between(
            x,
            baseline,
            baseline + values,
            step="pre",
            label=col.replace(f"_{bus_name}", "")
        )

        baseline += values

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

    ax.set_xlabel("Time")
    ax.set_ylabel("Power (kW)")
    ax.grid(True, alpha=0.3)
    ax.legend()

    fig.autofmt_xdate()
    fig.tight_layout()

    return fig






