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


def scenario_without_findings():
    """The bytes of a scenario file that the check has nothing to say about: the example without its PV system
    (a demand and the grid, for a day). The example itself is a day with an investment and so has the warning for
    a short period."""

    from backend.scenario_v2 import ScenarioV2
    from examples.make_examples_v2 import EXAMPLES

    values = EXAMPLES["pv_and_grid"]().model_dump()
    values["components"] = [c for c in values["components"] if c["id"] != "pv"]
    values["series"] = {k: v for k, v in values["series"].items() if k != "pv_profile"}

    return ScenarioV2(**values).model_dump_json().encode()