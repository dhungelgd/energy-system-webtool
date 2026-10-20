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


# oemof treats N timestamps as N-1 time steps, so the model currently simulates
# one hour less than the user asks for. Tests whose expected value assumes the
# full period are marked with this. After the fix (Change 6) they pass, and
# because the marker is strict, pytest then asks to remove it.
known_time_step_bug = pytest.mark.xfail(
    strict=True,
    reason="model simulates N-1 hours for N timestamps (fix planned in Change 6)",
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