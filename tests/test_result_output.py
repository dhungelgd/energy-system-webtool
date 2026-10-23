"""A saved result must give back what the results page and the Excel export need."""

import io

import pandas as pd
import pytest

from backend.config_builder import build_config
from backend.results import ScenarioResult
from backend.results_summary import collect_results
from backend.scenario import Scenario
from backend.scenario_runner import run_scenario
from tests.helpers import needs_cbc

pytestmark = needs_cbc


def scenario():
    # 10 kW for 24 hours, 5 kW of it from a fixed PV plant
    return Scenario(
        components=["demand", "grid", "pv", "gas_import", "gas_boiler", "heat_demand"],
        settings={
            "demand": {"scaling_factor": 10.0},
            "heat_demand": {"scaling_factor": 4.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
            "pv": {"mode": "fixed", "capacity": 5.0},
            "gas_import": {"variable_costs": 0.10},
            "gas_boiler": {"mode": "fixed", "capacity": 10.0, "efficiency": 0.9},
        },
        time={"steps": 24},
        series={
            "electricity_demand": [1.0] * 24,
            "heat_demand": [1.0] * 24,
            "pv": [1.0] * 24,
        },
    )


@pytest.fixture(scope="module")
def original():
    selected, tech_inputs, input_data, solver = scenario().to_inputs()
    config = build_config(selected, tech_inputs, input_data, solver)
    _, results, meta, _ = run_scenario(config, input_data, selected_techs=selected)
    output = collect_results(results, meta, config, selected)
    return output, meta


@pytest.fixture(scope="module")
def rebuilt(original, tmp_path_factory):
    """Run -> result -> file -> load -> rebuilt output: the whole way."""

    output, meta = original
    path = tmp_path_factory.mktemp("saved") / "result.json"

    ScenarioResult.from_output(output, meta).save(path)

    return ScenarioResult.load(path).to_output()


# ---------------------------------------------------------------------------

def test_the_same_parts_as_the_original(original, rebuilt):
    output, _ = original

    assert set(rebuilt) == set(output)
    for bus in output["buses"]:
        assert set(rebuilt["buses"][bus]) == set(output["buses"][bus])


def test_numbers_and_period(original, rebuilt):
    output, _ = original

    assert rebuilt["objective"] == pytest.approx(output["objective"])
    assert rebuilt["horizon_hours"] == output["horizon_hours"]
    assert rebuilt["key_figures"] == [
        {**figure, "value": pytest.approx(figure["value"])} for figure in output["key_figures"]
    ]


def test_the_tables_are_identical(original, rebuilt):
    output, _ = original

    pd.testing.assert_frame_equal(rebuilt["cost_breakdown"], output["cost_breakdown"], check_exact=True)
    pd.testing.assert_frame_equal(rebuilt["capacities"], output["capacities"], check_exact=True)

    for bus, data in output["buses"].items():
        again = rebuilt["buses"][bus]
        pd.testing.assert_frame_equal(again["flows"], data["flows"], check_exact=True)
        pd.testing.assert_frame_equal(again["supply"], data["supply"], check_exact=True)
        pd.testing.assert_frame_equal(again["use"], data["use"], check_exact=True)
        pd.testing.assert_series_equal(again["energy_sums"], data["energy_sums"], check_exact=True)


def test_the_figures_are_drawn_again_identically(original, rebuilt):
    output, _ = original

    for bus, data in output["buses"].items():
        assert rebuilt["buses"][bus]["flow_fig"].to_json() == data["flow_fig"].to_json()
        assert rebuilt["buses"][bus]["sankey_fig"].to_json() == data["sankey_fig"].to_json()


def test_the_excel_file_has_the_same_content(original, rebuilt):
    output, _ = original

    def sheets(content):
        return pd.read_excel(io.BytesIO(content), sheet_name=None)

    before, after = sheets(output["excel"]), sheets(rebuilt["excel"])

    assert list(after) == list(before)
    for name in before:
        pd.testing.assert_frame_equal(after[name], before[name], check_exact=True)


def test_only_the_system_diagram_is_missing(rebuilt):
    assert rebuilt["system_graph"] is None


def test_a_result_without_flows_cannot_be_shown_and_says_why(original):
    output, meta = original
    light = ScenarioResult.from_output(output, meta, include_flows=False)

    with pytest.raises(ValueError, match="without the hourly flows"):
        light.to_output()


def test_the_real_results_page_shows_a_saved_result(original, tmp_path):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    output, meta = original
    path = tmp_path / "result.json"
    ScenarioResult.from_output(output, meta).save(path)

    def page(result_file):
        from backend.results import ScenarioResult
        from frontend.ui_results import render_results

        render_results(ScenarioResult.load(result_file).to_output(), outdated=False)

    app = AppTest.from_function(page, args=(str(path),), default_timeout=60)
    app.run()

    assert not app.exception
    assert any("System cost" in metric.label for metric in app.metric)