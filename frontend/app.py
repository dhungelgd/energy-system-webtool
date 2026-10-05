import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from backend.scenario_runner import run_scenario
from backend.config_builder import build_config
from backend.results_summary import collect_results
from backend.system_check import check_system
from frontend.ui_inputs import build_ui
from frontend.ui_checks import component_labels, render_findings
from frontend.ui_results import render_results
from frontend.ui_styles import load_global_styles

# ui styling
load_global_styles()
st.set_page_config(layout="wide")

st.title("Energy System Web Tool (oemof)")

# session state
if "run_output" not in st.session_state:
    st.session_state.run_output = None      # results of the last run
    st.session_state.run_signature = None   # inputs used for the last run

# ui input block
selected_techs, tech_inputs, input_data, solver_cfg = build_ui()

# fingerprint of the current inputs (used to detect outdated results)
current_signature = repr((selected_techs, tech_inputs, input_data, solver_cfg))

# system check (runs automatically on every change)
st.markdown("---")
st.subheader("System Check")

findings = check_system(
    selected_techs,
    tech_inputs,
    input_data,
    labels=component_labels()
)

blocked = (not selected_techs) or any(f.level == "error" for f in findings)

if not selected_techs:

    st.caption("Select components in the sidebar to start.")

else:

    render_findings(findings)

    if not findings:
        st.success("System check passed. Ready to optimize.")
    elif blocked:
        st.caption("Fix the errors above to enable the optimization.")
    else:
        st.info("The system check found warnings but no errors. You can run the optimization.")

run = st.button("Run Optimization", disabled=blocked)

# execution
if run:

    config = build_config(
        selected_techs=selected_techs,
        tech_inputs=tech_inputs,
        input_data=input_data,
        solver_cfg=solver_cfg
    )

    try:
        with st.spinner("Running optimization..."):

            es, results, meta_results, fig = run_scenario(
                config,
                input_data,
                selected_techs=selected_techs,
                plot_graph=True
            )

            # compute tables and figures once and keep them
            st.session_state.run_output = collect_results(
                results,
                meta_results,
                config,
                selected_techs,
                system_graph=fig
            )
            st.session_state.run_signature = current_signature

    except (ValueError, RuntimeError) as err:
        # ValueError: input problems raised by the backend (e.g. missing capacity)
        # RuntimeError: the solver found no optimal solution (infeasible / unbounded)
        st.session_state.run_output = None
        st.session_state.run_signature = None
        st.error(f"The optimization could not be completed:\n\n{err}")
        st.caption(
            "Typical causes: a missing input (e.g. capacity in fixed mode), or a "
            "system that cannot be balanced (e.g. surplus PV or wind electricity without "
            "a grid feed-in, or an investment option without a maximum capacity)."
        )

    else:
        st.success("Optimization completed")

# results of the last successful run (stay visible when inputs change)
if st.session_state.run_output is not None:
    render_results(
        st.session_state.run_output,
        outdated=(st.session_state.run_signature != current_signature)
    )