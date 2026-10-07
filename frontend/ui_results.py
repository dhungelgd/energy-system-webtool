import streamlit as st
import plotly.graph_objects as go

from backend.kpis import CATEGORY_INVEST, CATEGORY_ENERGY, CATEGORY_REVENUE

# colour per cost category (same blue / orange / teal family as the system graph)
CATEGORY_COLORS = {
    CATEGORY_INVEST: "#1F77B4",
    CATEGORY_ENERGY: "#E8873A",
    CATEGORY_REVENUE: "#2A9D8F",
    "Other": "#9AA5B1",
}


def format_value(value, unit):
    """Readable text for one key figure."""

    if unit == "%":
        return f"{value:.0f} %"
    if unit == "€":
        return f"{value:,.0f} €"
    if unit == "kW":
        return f"{value:,.1f} kW"
    if unit == "kWh":
        if abs(value) >= 10000:
            return f"{value / 1000:,.1f} MWh"
        return f"{value:,.0f} kWh"

    return f"{value:,.2f} {unit}"


def cost_figure(table):
    """Horizontal bar chart of the cost items (revenues point to the left)."""

    table = table[table["Cost (€)"].abs() > 0.005].sort_values("Cost (€)")

    fig = go.Figure()

    for category, color in CATEGORY_COLORS.items():

        part = table[table["Category"] == category]

        if part.empty:
            continue

        fig.add_trace(go.Bar(
            y=part["Item"],
            x=part["Cost (€)"],
            name=category,
            orientation="h",
            marker_color=color,
            text=[f"{v:,.0f} €" for v in part["Cost (€)"]],
            textposition="auto",
            hovertemplate="%{y}<br>%{x:,.0f} €<extra></extra>",
        ))

    fig.update_layout(
        template="plotly_white",
        height=max(260, 70 * len(table) + 120),
        xaxis_title="Cost (€)  –  negative values are revenues",
        yaxis_title=None,
        legend_title_text=None,
        margin=dict(l=10, r=10, t=30, b=10),
    )

    return fig


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

    # key figures, four per row
    figures = output["key_figures"]

    for start in range(0, len(figures), 4):

        for column, figure in zip(st.columns(4), figures[start:start + 4]):
            column.metric(
                figure["label"],
                format_value(figure["value"], figure["unit"]),
                help=figure["help"],
            )

    if output["horizon_hours"] < 8700:
        st.caption(
            f"The simulated period is {output['horizon_hours'] / 24:.0f} days. "
            "Investment costs are annualised (full year), while energy costs "
            "cover only the simulated period, so the system cost is not an annual figure."
        )

    st.download_button(
        "Download results (Excel)",
        data=output["excel"],
        file_name="energy_system_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    buses = output["buses"]

    # one tab per result group
    labels = []
    if output["system_graph"] is not None:
        labels.append("System graph")
    labels += [bus.capitalize() for bus in buses]
    labels += ["Costs", "Capacities"]

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

            st.markdown("#### Supply and use")
            supply_col, use_col = st.columns(2)

            for column, title, table in (
                (supply_col, "Supply", data["supply"]),
                (use_col, "Use", data["use"]),
            ):
                column.markdown(f"**{title}**")
                column.dataframe(
                    table,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Energy (kWh)": st.column_config.NumberColumn(format="%.0f"),
                        "Share (%)": st.column_config.NumberColumn(format="%.1f"),
                    },
                )

            st.markdown("#### Sankey diagram")
            st.plotly_chart(data["sankey_fig"], width="stretch", key=f"sankey_{bus}")

            with st.expander("Flow table (kW per time step)"):
                st.dataframe(data["flows"])

    # costs
    with tabs["Costs"]:

        table = output["cost_breakdown"]

        if table.empty:
            st.info("No cost items in this run.")
        else:
            st.markdown("#### Where the system cost comes from")
            st.plotly_chart(cost_figure(table), width="stretch", key="cost_breakdown")

            st.dataframe(
                table,
                hide_index=True,
                width="stretch",
                column_config={
                    "Cost (€)": st.column_config.NumberColumn(format="%.0f"),
                },
            )

    # capacities
    with tabs["Capacities"]:

        capacities = output["capacities"]

        if capacities.empty:
            st.info("No components with a capacity in this system.")
        else:
            st.dataframe(
                capacities,
                hide_index=True,
                width="stretch",
                column_config={
                    "Capacity": st.column_config.NumberColumn(format="%.1f"),
                    "Annualised cost (€/a)": st.column_config.NumberColumn(format="%.0f"),
                },
            )
            if (capacities["Mode"] == "fixed (input)").any():
                st.caption(
                    "Components in fixed mode have no capital cost in the optimization."
                )