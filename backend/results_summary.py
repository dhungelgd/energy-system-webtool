from backend.postprocessing import (
    process_results,
    compute_energy_sums,
    get_active_bus_labels,
    timestep_hours,
)
from backend.plotting import plot_energy_flows_plotly, create_sankey
from backend.kpis import (
    supply_and_use,
    compute_key_figures,
    compute_cost_breakdown,
    build_capacity_table,
)
from backend.export import build_excel


def collect_results(results, meta_results, config, selected_techs, system_graph=None):
    """Turn the raw oemof results into plain Python objects, computed once.

    The returned dictionary contains everything a user interface needs to
    display the results (tables and figures). It does not depend on Streamlit,
    so any other frontend can reuse it.
    """

    buses = {}
    step_hours = 1.0
    n_steps = 0

    for bus in get_active_bus_labels(selected_techs, config):

        flows = process_results(results, bus_name=bus)

        if flows is None or flows.empty:
            continue

        energy_sums = compute_energy_sums(flows)
        supply, use = supply_and_use(energy_sums, bus)

        buses[bus] = {
            "flows": flows,
            "energy_sums": energy_sums,
            "supply": supply,
            "use": use,
            "flow_fig": plot_energy_flows_plotly(flows=flows, bus_name=bus),
            "sankey_fig": create_sankey(energy_sums),
        }

        step_hours = timestep_hours(flows.index)
        n_steps = len(flows.dropna(how="all"))   # without the empty end row

    objective = meta_results["objective"]
    horizon_hours = n_steps * step_hours

    output = {
        "objective": objective,
        "horizon_hours": horizon_hours,
        "system_graph": system_graph,
        "buses": buses,
        "key_figures": compute_key_figures(buses, objective, horizon_hours),
        "cost_breakdown": compute_cost_breakdown(
            results, config, buses, objective, step_hours
        ),
        "capacities": build_capacity_table(results, config),
    }

    # Excel file is built once here, so the download button costs nothing on reruns
    output["excel"] = build_excel(output)

    return output