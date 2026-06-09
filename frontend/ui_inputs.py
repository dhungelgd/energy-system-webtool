import streamlit as st
import pandas as pd
from backend.input_schema import SolverConfig
from frontend.ui_registry import UI_REGISTRY
from frontend.ui_defaults import TECH_DEFAULTS

# component selector
def select_components():

    st.sidebar.header("System Components")

    return st.sidebar.multiselect(
        "Select components",
        list(UI_REGISTRY.keys())
    )

# time configuration
def time_input_block():

    st.sidebar.header("Time Settings")
    start_date = st.sidebar.date_input("Start date", pd.to_datetime("2025-01-01"))
    days = st.sidebar.number_input("Periods (Number of days)", 1, 366, 365)
    freq_map = {"1h": 24,"15min": 96}

    res_options = ["15min", "1h"]

    resolution = st.sidebar.selectbox(
        "Resolution",
        res_options,
        index=res_options.index("1h"),
        key="resolution"
    )

    periods = days * freq_map[resolution]

    timeindex = pd.date_range(
        start=start_date,
        periods=periods,
        freq=resolution,
    )

    return timeindex

# generic timeseries handler
def render_timeseries(cfg, comp):

    uploaded_file = st.file_uploader(
        cfg.get("upload_label", f"Upload {comp} timeseries data"),
        type=["csv"],
        key=f"{comp}_csv"
    )

    if uploaded_file is not None:
        st.session_state[f"{comp}_df"] = pd.read_csv(uploaded_file)

    df = st.session_state.get(f"{comp}_df")

    if df is None:
        return None, None

    default_col = cfg.get("default_column", 0)

    if len(df.columns) <= default_col:
        default_col = 0

    column = st.selectbox(
        f"Select {comp} column",
        df.columns,
        index=default_col,
        key=f"{comp}_col"
    )
    st.write(df.head())

    return column, df[column].tolist()

# generic component renderer
def render_component(comp):

    schema = UI_REGISTRY[comp]

    st.subheader(schema["label"])

    tech_inputs = {comp: {}}
    input_data = {}

    defaults = TECH_DEFAULTS.get(comp, {})

    #timeseries data
    ts_cfg = schema.get("timeseries")

    if ts_cfg:
        column, series = render_timeseries(ts_cfg, comp)

        if series is not None:
            tech_inputs[comp]["column"] = column
            input_data[ts_cfg["key"]] = series

    # static inputs
    for field in schema.get("inputs", []):

        key = field["key"]
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

            tech_inputs[comp][key] = st.selectbox(
                label,
                field.get("options", []),
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


# solver block
def solver_block():

    st.sidebar.header("Solver")

    return SolverConfig(
        name=st.sidebar.selectbox(
            "Solver",
            ["cbc", "gurobi", "glpk"],
            key="solver_name"
        ),

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

    for component in selected_techs:
        tech_inputs, input_data = render_component(component)
        all_tech_inputs.update(tech_inputs)
        all_input_data.update(input_data)

    solver_cfg = solver_block()

    return (
        selected_techs,
        all_tech_inputs,
        all_input_data,
        solver_cfg
    )