from oemof.solph import views

# Extract flows from a bus
def get_bus_flows(results, bus_name):

    flows = views.node(results, bus_name)["sequences"]

    return flows

# Flatten column names
def flatten_flows(df):
    # convert multi-index columns to simple string names
    # e.g. (("pv", "electricity"), "flow")  --> "pv_electricity"

    df_flat = df.copy()
    df_flat.columns = [
        f"{col[0][0]}_{col[0][1]}" for col in df.columns
    ]

    return df_flat

# Get supply and demand columns automatically
def split_supply_demand(flows, bus_name):
    # split flows into supply (to bus) and demand (from bus)

    supply_cols = [c for c in flows.columns if c.endswith(f"_{bus_name}")]
    demand_cols = [c for c in flows.columns if c.startswith(f"{bus_name}_")]

    return supply_cols, demand_cols

# compute total energy per flow
def compute_energy_sums(flows):

    return flows.sum()


# full processing pipeline
def process_results(results, bus_name):

    flows = get_bus_flows(results, bus_name)
    flows = flatten_flows(flows)

    return flows
