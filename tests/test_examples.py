"""The example scenarios must stay in line with the code."""

from pathlib import Path

import pytest

from backend.scenario import Scenario
from backend.service import check, run
from examples.make_examples import EXAMPLES, FOLDER
from tests.helpers import needs_cbc


def saved(name):
    return Scenario.load(FOLDER / f"{name}.json")


def test_every_example_file_comes_from_the_generator_and_the_other_way_round():
    files = {path.stem for path in Path(FOLDER).glob("*.json")}

    assert files == set(EXAMPLES)


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_the_saved_file_equals_what_the_generator_makes(name):
    # if this fails, run: python -m examples.make_examples
    assert saved(name) == EXAMPLES[name]()


def errors(findings):
    return [f.message for f in findings if f.level == "error"]


def warnings(findings):
    return [f.message for f in findings if f.level == "warning"]


def test_the_two_working_examples_have_no_findings():
    assert check(saved("grid_only_24h")) == []
    assert check(saved("pv_battery_week")) == []


def test_the_example_with_problems_has_one_error_and_one_warning():
    findings = check(saved("with_problems_24h"))

    assert len(errors(findings)) == 1 and "10 values" in errors(findings)[0]
    assert len(warnings(findings)) == 1 and "cannot be exported" in warnings(findings)[0]


@needs_cbc
def test_the_grid_only_example_costs_72_euro():
    assert run(saved("grid_only_24h")).objective == pytest.approx(72.0)


@needs_cbc
def test_the_pv_and_battery_week_is_cheaper_than_buying_everything():
    scenario = saved("pv_battery_week")
    grid_only = Scenario(
        components=["demand", "grid"],
        settings={"demand": scenario.settings["demand"], "grid": scenario.settings["grid"]},
        time=scenario.time.model_dump(),
        series={"electricity_demand": scenario.series["electricity_demand"]},
    )

    with_pv = run(scenario)

    assert with_pv.solver.termination == "optimal"
    assert with_pv.objective < 0.6 * run(grid_only).objective


@needs_cbc
def test_the_example_with_problems_is_refused_by_run():
    from backend.service import ScenarioNotReady

    with pytest.raises(ScenarioNotReady):
        run(saved("with_problems_24h"))