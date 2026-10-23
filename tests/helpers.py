"""Small helpers shared by the tests."""

import shutil

import pandas as pd
import pytest

from backend.config_builder import build_config
from backend.input_schema import SolverConfig
from backend.scenario_runner import run_scenario

# the model tests need the CBC solver (apt: coinor-cbc)
needs_cbc = pytest.mark.skipif(
    shutil.which("cbc") is None, reason="CBC solver is not installed"
)

# the model tests need the CBC solver (apt: coinor-cbc)
needs_cbc = pytest.mark.skipif(
    shutil.which("cbc") is None, reason="CBC solver is not installed"
)


def timeindex(hours):
    return pd.date_range("2021-01-01", periods=hours, freq="1h")


def solve(selected, tech_inputs, input_data):
    """Build and solve a model. Returns (results, meta_results, config)."""

    config = build_config(
        selected_techs=selected,
        tech_inputs=tech_inputs,
        input_data=input_data,
        solver_cfg=SolverConfig(name="cbc"),
    )
    _, results, meta, _ = run_scenario(config, input_data, selected_techs=selected)
    return results, meta, config