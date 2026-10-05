import streamlit as st


def render_results(output, outdated=False):
    """Show the stored results of the last optimization run.

    `output` is the dictionary created by backend.results_summary.collect_results.
    Nothing is calculated here, so this function is cheap to run on every rerun.
    """

    st.markdown("---")
    st.subheader("Results")

    if outdated:
        st.warning(
            "The inputs have changed since the last run, so these results are "
            "outdated. Press 'Run Optimization' to update them."
        )

    st.metric("Annual system cost", f"{output['objective']:.2f} €")

    buses = output["buses"]

    # one tab per result group
    labels = []
    if output["system_graph"] is not None:
        labels.append("System graph")
    labels += [bus.capitalize() for bus in buses]
    labels.append("Investments")

    tabs = dict(zip(labels, st.tabs(labels)))

    # system graph
    if output["system_graph"] is not None:
        with tabs["System graph"]:
            st.plotly_chart(output["system_graph"], width="stretch", key="system_graph")

    # one tab per bus
    for bus, data in buses.items():

        with tabs[bus.capitalize()]:

            st.markdown("#### Energy flows")
            st.plotly_chart(
                data["flow_fig"], width="stretch", theme=None, key=f"flows_{bus}"
            )

            st.markdown("#### Sankey diagram")
            st.plotly_chart(data["sankey_fig"], width="stretch", key=f"sankey_{bus}")

            with st.expander("Flow table"):
                st.dataframe(data["flows"])

            with st.expander("Energy flow summary"):
                st.write(data["energy_sums"])

    # investment results
    with tabs["Investments"]:

        if output["investments"].empty:
            st.info(
                "No investment decisions in this run (all components are in "
                "'fixed' mode)."
            )
        else:
            st.dataframe(output["investments"], hide_index=True)