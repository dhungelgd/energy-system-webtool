import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from backend.scenario_runner import run_scenario
from backend.postprocessing import process_results, compute_energy_sums, get_active_bus_labels
from backend.plotting import plot_energy_flows
from backend.config_builder import build_config
from frontend.ui_inputs import build_ui
from frontend.ui_styles import load_global_styles

# ui styling
load_global_styles()

st.title("Energy System Web Tool (oemof)")

# session state
if "ready_confirmed" not in st.session_state:
    st.session_state.ready_confirmed = False

# ui input block
selected_techs, tech_inputs, input_data, solver_cfg = build_ui()

# system check
st.markdown("---")
st.subheader("System Check")

if not st.session_state.ready_confirmed:

    confirm = st.radio(
        "All components added?",
        ["Not yet", "Yes, ready"],
        index=0
    )

    if confirm == "Yes, ready":
        st.session_state.ready_confirmed = True
        st.rerun()

else:

    st.success("System confirmed. Ready to optimize.")

    run = st.button("Run Optimization")

    # execution
    if run:

        config = build_config(
            selected_techs=selected_techs,
            tech_inputs=tech_inputs,
            input_data=input_data,
            solver_cfg=solver_cfg
        )

        with st.spinner("Running optimization..."):

            es, results, meta_results, fig = run_scenario(
                config,
                input_data,
                plot_graph=True
            )

            # graph
            if fig is not None:
                st.pyplot(fig)

        st.success("Optimization completed")

        # results
        st.subheader("Results Summary")

        st.write(
            f"Annual system cost: {meta_results['objective']:.2f} €"
        )

        st.subheader("Energy System Results")

        active_buses = get_active_bus_labels(selected_techs, config)
        st.write(active_buses)
        for bus in active_buses:

            flows = process_results(results, bus_name=bus)

            if flows is None or flows.empty:
                continue

            st.markdown("---")
            st.subheader(f"{bus.capitalize()} Results")

            st.subheader("Flows")
            st.dataframe(flows)

            st.subheader("Energy Flow Summary")
            st.write(compute_energy_sums(flows))

            st.subheader("Visualization")

            for bus in active_buses:

                flows = process_results(results, bus_name=bus)

                if flows is None or flows.empty:
                    continue

                energy_flows_plot = plot_energy_flows(
                    flows=flows,
                    bus_name=bus
                )

                st.markdown(f"### {bus.capitalize()} Energy Flows")
                st.pyplot(energy_flows_plot)