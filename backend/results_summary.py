import pandas as pd

from backend.postprocessing import (
    process_results,
    compute_energy_sums,
    get_active_bus_labels,
    get_investment_capacities,
)
from backend.plotting import plot_energy_flows_plotly, create_sankey


def collect_results(results, meta_results, config, selected_techs, system_graph=None):
    """Turn the raw oemof results into plain Python objects, computed once.

    The returned dictionary contains everything a user interface needs to
    display the results (tables and figures). It does not depend on Streamlit,
    so any other frontend can reuse it.
    """

    buses = {}

    for bus in get_active_bus_labels(selected_techs, config):

        flows = process_results(results, bus_name=bus)

        if flows is None or flows.empty:
            continue

        energy_sums = compute_energy_sums(flows)

        buses[bus] = {
            "flows": flows,
            "energy_sums": energy_sums,
            "flow_fig": plot_energy_flows_plotly(flows=flows, bus_name=bus),
            "sankey_fig": create_sankey(energy_sums),
        }

    capacities = get_investment_capacities(results)

    investments = pd.DataFrame(
        {
            "Component": list(capacities.keys()),
            "Invested capacity": list(capacities.values()),
        }
    )

    return {
        "objective": meta_results["objective"],
        "system_graph": system_graph,
        "buses": buses,
        "investments": investments,
    }