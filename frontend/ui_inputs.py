"""
UI input handling for the energy system webtool.
Separates UI rendering logic from business logic.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

from backend.input_schema import SolverConfig
from backend.constants import TechnologyType, FREQUENCY_MAP
from frontend.ui_registry import UI_REGISTRY
from frontend.ui_defaults import TECH_DEFAULTS


class TimeConfigHandler:
    """Handles time configuration UI inputs."""
    
    @staticmethod
    def render() -> pd.DatetimeIndex:
        """
        Render time configuration inputs in sidebar.
        
        Returns:
            DatetimeIndex for the simulation period
        """
        st.sidebar.header("Time Settings")
        
        start_date = st.sidebar.date_input(
            "Start date", 
            pd.to_datetime("2021-01-01")
        )
        
        days = st.sidebar.number_input(
            "Periods (Number of days)", 
            1, 
            366, 
            365
        )
        
        res_options = ["15min", "1h"]
        resolution = st.sidebar.selectbox(
            "Resolution",
            res_options,
            index=res_options.index("1h"),
            key="resolution"
        )
        
        periods = days * FREQUENCY_MAP[resolution]
        
        timeindex = pd.date_range(
            start=start_date,
            periods=periods,
            freq=resolution,
        )
        
        return timeindex


class ComponentSelector:
    """Handles component selection UI."""
    
    @staticmethod
    def render() -> List[str]:
        """
        Render component selection in sidebar.
        
        Returns:
            List of selected technology types
        """
        st.sidebar.header("System Components")
        
        return st.sidebar.multiselect(
            "Select components",
            list(UI_REGISTRY.keys())
        )


class SolverConfigHandler:
    """Handles solver configuration UI."""
    
    @staticmethod
    def render() -> SolverConfig:
        """
        Render solver configuration in sidebar.
        
        Returns:
            SolverConfig object
        """
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


class FieldVisibilityController:
    """Controls field visibility based on conditions."""
    
    @staticmethod
    def is_visible(field: Dict[str, Any], current_values: Dict[str, Any]) -> bool:
        """
        Check if a field should be visible based on conditions.
        
        Args:
            field: Field configuration
            current_values: Current values of other fields
            
        Returns:
            True if field should be visible
        """
        rule = field.get("visible_if")
        
        if not rule:
            return True
        
        for key, expected_value in rule.items():
            actual_value = current_values.get(key)
            if actual_value != expected_value:
                return False
        
        return True


class TimeseriesHandler:
    """Handles timeseries data upload and selection."""
    
    @staticmethod
    def render(cfg: Dict[str, Any], comp: str) -> Tuple[Optional[str], Optional[List[float]]]:
        """
        Render timeseries upload and selection UI.
        
        Args:
            cfg: Timeseries configuration
            comp: Component name
            
        Returns:
            Tuple of (selected_column, series_data)
        """
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


class ComponentRenderer:
    """Renders UI for a single component."""
    
    @staticmethod
    def render(component: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Render UI for a component.
        
        Args:
            component: Component name
            
        Returns:
            Tuple of (tech_inputs, input_data)
        """
        schema = UI_REGISTRY[component]
        
        st.subheader(schema["label"])
        
        tech_inputs = {component: {}}
        input_data = {}
        
        defaults = TECH_DEFAULTS.get(component, {})
        
        # Render control fields first (e.g., cop_mode)
        for field in schema.get("inputs", []):
            if field.get("key") == "cop_mode":
                value = defaults.get("cop_mode", "constant")
                
                tech_inputs[component]["cop_mode"] = st.selectbox(
                    field["label"],
                    field["options"],
                    index=field["options"].index(value) if value in field["options"] else 0,
                    key=f"{component}_cop_mode"
                )
        
        # Timeseries data
        ts_cfg = schema.get("timeseries")
        
        if ts_cfg:
            use_timeseries = True
            
            if component == "heat_pump":
                use_timeseries = (
                    tech_inputs[component].get(
                        "cop_mode",
                        defaults.get("cop_mode", "constant")
                    ) == "timeseries"
                )
            
            if use_timeseries:
                column, series = TimeseriesHandler.render(ts_cfg, component)
                
                if series is not None:
                    tech_inputs[component][ts_cfg["key"]] = column
                    if component == "heat_pump":
                        input_data["cop_series"] = series
                    else:
                        input_data[ts_cfg["key"]] = series
        
        # Static inputs
        for field in schema.get("inputs", []):
            key = field["key"]
            
            # Skip COP mode (already handled)
            if key == "cop_mode":
                continue
            
            # Visibility control
            if not FieldVisibilityController.is_visible(field, tech_inputs[component]):
                continue
            
            label = field["label"]
            ftype = field["type"]
            
            value = defaults.get(key, field.get("default", 0.0))
            
            # Number input
            if ftype == "number":
                tech_inputs[component][key] = st.number_input(
                    label,
                    value=value,
                    step=field.get("step", 0.1),
                    key=f"{component}_{key}"
                )
            
            # Selectbox
            elif ftype == "selectbox":
                tech_inputs[component][key] = st.selectbox(
                    label,
                    field.get("options", []),
                    key=f"{component}_{key}"
                )
            
            # Checkbox
            elif ftype == "checkbox":
                tech_inputs[component][key] = st.checkbox(
                    label,
                    value=field.get("default", False),
                    key=f"{component}_{key}"
                )
        
        return tech_inputs, input_data


class UIOrchestrator:
    """Orchestrates the entire UI building process."""
    
    @staticmethod
    def build() -> Tuple[List[str], Dict[str, Any], Dict[str, Any], SolverConfig]:
        """
        Build the complete UI and collect all inputs.
        
        Returns:
            Tuple of (selected_techs, all_tech_inputs, all_input_data, solver_cfg)
        """
        # Component selection
        selected_techs = ComponentSelector.render()
        
        # Initialize data containers
        all_tech_inputs = {}
        all_input_data = {}
        
        # Time configuration
        timeindex = TimeConfigHandler.render()
        all_input_data["timeindex"] = timeindex
        
        # Render each selected component
        for component in selected_techs:
            tech_inputs, input_data = ComponentRenderer.render(component)
            all_tech_inputs.update(tech_inputs)
            all_input_data.update(input_data)
        
        # Solver configuration
        solver_cfg = SolverConfigHandler.render()
        
        return (
            selected_techs,
            all_tech_inputs,
            all_input_data,
            solver_cfg
        )


# Backward compatible functions

def select_components() -> List[str]:
    """Select components (backward compatible)."""
    return ComponentSelector.render()


def time_input_block() -> pd.DatetimeIndex:
    """Time input block (backward compatible)."""
    return TimeConfigHandler.render()


def field_is_visible(field: Dict[str, Any], current_values: Dict[str, Any]) -> bool:
    """Check field visibility (backward compatible)."""
    return FieldVisibilityController.is_visible(field, current_values)


def render_timeseries(cfg: Dict[str, Any], comp: str) -> Tuple[Optional[str], Optional[List[float]]]:
    """Render timeseries (backward compatible)."""
    return TimeseriesHandler.render(cfg, comp)


def render_component(comp: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Render component (backward compatible)."""
    return ComponentRenderer.render(comp)


def solver_block() -> SolverConfig:
    """Solver block (backward compatible)."""
    return SolverConfigHandler.render()


def build_ui() -> Tuple[List[str], Dict[str, Any], Dict[str, Any], SolverConfig]:
    """Build UI (backward compatible)."""
    return UIOrchestrator.build()
