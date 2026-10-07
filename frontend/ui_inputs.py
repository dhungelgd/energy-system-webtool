import streamlit as st
import pandas as pd
from backend.input_schema import SolverConfig
from frontend.ui_registry import UI_REGISTRY
from frontend.ui_defaults import TECH_DEFAULTS
from frontend.ui_selection import select_components

# time configuration
# the model always covers exactly one year (365 days) in hourly resolution
DAYS_PER_YEAR = 365
RESOLUTION = "1h"
STEPS_PER_YEAR = DAYS_PER_YEAR * 24

def time_input_block():

    st.sidebar.header("Time Settings")
    start_date = st.sidebar.date_input("Start date", pd.to_datetime("2021-01-01"))
    st.sidebar.caption(
        f"Simulated period: {DAYS_PER_YEAR} days, hourly resolution "
        f"({STEPS_PER_YEAR} time steps per time series)"
    )

    timeindex = pd.date_range(
        start=start_date,
        periods=STEPS_PER_YEAR,
        freq=RESOLUTION,
    )

    return timeindex

def field_is_visible(field, current_values):

    rule = field.get("visible_if")

    if not rule:
        return True

    for key, expected_value in rule.items():

        actual_value = current_values.get(key)
        if actual_value != expected_value:
            return False

    return True

# shared upload: one CSV with all time series, uploaded once
def shared_upload_block():

    st.sidebar.header("Time Series Data")

    uploaded_file = st.sidebar.file_uploader(
        "Upload one CSV with all time series",
        type=["csv"],
        key="shared_ts_csv"
    )

    if uploaded_file is not None:
        st.session_state["shared_ts_df"] = pd.read_csv(uploaded_file)
    else:
        st.session_state.pop("shared_ts_df", None)

    df = st.session_state.get("shared_ts_df")

    if df is not None:
        st.sidebar.caption(f"{len(df)} rows, {len(df.columns)} columns")


# generic timeseries handler
def render_timeseries(cfg, comp):

    shared_df = st.session_state.get("shared_ts_df")

    # optional: a separate file for this component only
    with st.expander(
        "Use a separate file for this component",
        expanded=shared_df is None
    ):
        uploaded_file = st.file_uploader(
            cfg.get("upload_label", f"Upload {comp} timeseries data"),
            type=["csv"],
            key=f"{comp}_csv"
        )

    if uploaded_file is not None:
        st.session_state[f"{comp}_df"] = pd.read_csv(uploaded_file)

    # own file first, otherwise the shared file
    df = st.session_state.get(f"{comp}_df")

    if df is None:
        df = shared_df

    if df is None:
        return None, None

    default_col = cfg.get("default_column", 0)

    if len(df.columns) <= default_col:
        default_col = 0

    column = st.selectbox(
        f"Select {comp} column",
        df.columns,
        index=default_col,
        # new key when the columns change, so the preselection is recalculated
        key=f"{comp}_col_{abs(hash(tuple(df.columns)))}"
    )
    st.write(df.head())

    return column, df[column].tolist()

# generic component renderer
def render_component(comp):

    schema = UI_REGISTRY[comp]

    tech_inputs = {comp: {}}
    input_data = {}

    defaults = TECH_DEFAULTS.get(comp, {})

    # control fields first (e.g. cop_mode, price_mode): they decide what else is shown
    for field in schema.get("inputs", []):

        if not field.get("control"):
            continue

        key = field["key"]
        value = defaults.get(key, field["options"][0])

        tech_inputs[comp][key] = st.selectbox(
            field["label"],
            field["options"],
            index=field["options"].index(value)
            if value in field["options"] else 0,
            key=f"{comp}_{key}"
        )

    # timeseries data (only when its condition is met, e.g. price_mode == "timeseries")
    ts_cfg = schema.get("timeseries")

    if ts_cfg:

        use_timeseries = all(
            tech_inputs[comp].get(key, defaults.get(key)) == expected
            for key, expected in ts_cfg.get("active_if", {}).items()
        )

        if use_timeseries:

            column, series = render_timeseries(ts_cfg, comp)

            if series is not None:

                tech_inputs[comp][ts_cfg["key"]] = column
                input_data[ts_cfg["key"]] = series

    # static inputs
    for field in schema.get("inputs", []):

        key = field["key"]

        # control fields were already rendered above
        if field.get("control"):
            continue

        # visibility control
        if not field_is_visible(field, tech_inputs[comp]):
            continue

        label = field["label"]
        ftype = field["type"]

        value = defaults.get(key, field.get("default", 0.0))

        # number input
        if ftype == "number":

            tech_inputs[comp][key] = st.number_input(
                label,
                value=value,
                step=field.get("step", 0.1),
                key=f"{comp}_{key}"
            )

        # selectbox
        elif ftype == "selectbox":

            options = field.get("options", [])

            tech_inputs[comp][key] = st.selectbox(
                label,
                options,
                index=options.index(defaults[key])
                if defaults.get(key) in options else 0,
                key=f"{comp}_{key}"
            )

        # checkbox
        elif ftype == "checkbox":

            tech_inputs[comp][key] = st.checkbox(
                label,
                value=field.get("default", False),
                key=f"{comp}_{key}"
            )

    return tech_inputs, input_data


# solver block (CBC is the only solver offered)
def solver_block():

    st.sidebar.header("Solver")
    st.sidebar.caption("Solver: CBC")

    return SolverConfig(
        name="cbc",
        tee=st.sidebar.checkbox(
            "Show solver output",
            value=False,
            key="solver_tee"
        )
    )


# ui orchestrator
def build_ui():

    selected_techs = select_components()

    all_tech_inputs = {}
    all_input_data = {}

    # time definition
    timeindex = time_input_block()
    all_input_data["timeindex"] = timeindex

    # one CSV with all time series (optional)
    shared_upload_block()

    # one tab per selected component
    if selected_techs:

        tabs = st.tabs([UI_REGISTRY[c]["label"] for c in selected_techs])

        for component, tab in zip(selected_techs, tabs):
            with tab:
                tech_inputs, input_data = render_component(component)
                all_tech_inputs.update(tech_inputs)
                all_input_data.update(input_data)

    else:
        st.info("Select the components of your energy system in the sidebar.")

    solver_cfg = solver_block()

    return (
        selected_techs,
        all_tech_inputs,
        all_input_data,
        solver_cfg
    )