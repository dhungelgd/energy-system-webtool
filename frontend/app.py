import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd

from backend.scenario_runner import run_scenario
from backend.input_schema import SolverConfig

st.title("Energy System Web Tool (oemof)")

# csv upload
st.header("Demand Profile Upload")

df = None
demand_column = None

uploaded_file = st.file_uploader("Upload demand CSV", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    st.write("Preview:")
    st.dataframe(df)

    demand_column = st.selectbox("Select demand column", df.columns)

# other inputs
price = st.number_input("Electricity Price (€/kWh)", value=0.3)

solver_name = st.selectbox("Solver", ["cbc", "gurobi"])
tee = st.checkbox("Show solver output", value=False)

run = st.button("Run Optimization")

# run model
if run:

    # safety check
    if df is None or demand_column is None:
        st.error("Please upload a CSV and select a demand column.")
        st.stop()

    config = {
        "buses": {
            "electricity_bus": {"label": "electricity"}
        },

        "technologies": {
            "demand_el": {
                "type": "demand",
                "bus": "electricity_bus",
                "scaling_factor": 1
            },

            "grid": {
                "type": "grid",
                "bus": "electricity_bus",
                "profile_data": df[demand_column].tolist(),
                "variable_costs": price,
                "feedin_tariff": 0.06
            }
        },

        "solver": SolverConfig(
            name=solver_name,
            tee=tee
        )
    }

    input_data = {
        "electricity_demand": df[demand_column].tolist()
    }

    with st.spinner("Running optimization..."):

        es, results, meta_results = run_scenario(config, input_data)

    st.success("Optimization completed")
    st.subheader("Results")

    # show structure safely
    total_costs = meta_results["objective"]
    st.write (f"The annual costs for electricty supply is {total_costs:.2f} €.")
