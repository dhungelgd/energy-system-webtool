from oemof.solph import views
import pandas as pd

# Extract flows from a bus
def get_bus_flows(results, bus_name):

    try:
        node = views.node(results, bus_name)

        if node is None:
            return pd.DataFrame()

        flows = node.get("sequences")

        if flows is None or len(flows) == 0:
            return pd.DataFrame()

        return flows

    except Exception:
        return pd.DataFrame()

# Flatten column names
def flatten_flows(df):
    # convert multi-index columns to simple string names
    # e.g. (("pv", "electricity"), "flow")  --> "pv_electricity"

    if df is None or df.empty:
        return df

    df_flat = df.copy()
    df_flat.columns = [
        f"{col[0][0]}-->{col[0][1]}" for col in df.columns
    ]

    return df_flat

# Get supply and demand columns automatically
def split_supply_demand(flows, bus_name):
    # split flows into supply (to bus) and demand (from bus)

    if flows is None or flows.empty:
        return [], []

    supply_cols = [c for c in flows.columns if c.endswith(f"-->{bus_name}")]
    demand_cols = [c for c in flows.columns if c.startswith(f"{bus_name}-->")]

    return supply_cols, demand_cols

# compute total energy per flow
def compute_energy_sums(flows):

    return flows.sum()

# full processing pipeline
def process_results(results, bus_name):

    flows = get_bus_flows(results, bus_name)
    flows = flatten_flows(flows)

    return flows

# active bus detection
def get_active_bus_labels(selected_techs, config):

    active_buses = set()

    for tech in selected_techs:

        tech_cfg = config["technologies"].get(tech, {})
        bus_id = tech_cfg.get("bus")

        if bus_id:
            bus_label = config["buses"][bus_id]["label"]
            active_buses.add(bus_label)

    return sorted(active_buses)

# extract investment capacities from results
def get_investment_capacities(results):

    capacities = {}

    for (comp, bus), data in results.items():

        if not hasattr(comp, "label"):
            continue

        tech = comp.label

        scalars = data.get("scalars")

        if scalars is None:
            continue

        invest_val = None

        try:
            invest_val = scalars.get("invest", None)
        except Exception:
            pass

        if invest_val is None:
            try:
                for item in scalars:
                    if isinstance(item, tuple) and item[0] == "invest":
                        invest_val = item[1]
                        break
            except Exception:
                pass

        if invest_val is not None:
            capacities[tech] = float(invest_val)

    return capacities
