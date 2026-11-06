"""Solving with HiGHS and with CBC: the same answers, the same words for an error, an honest account of what ran."""

import logging
import math
import pickle
import types
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError
from pyomo.environ import ConcreteModel, NonNegativeReals, Var

from backend import service, service_v2, solving
from backend.input_schema import SolverConfig
from backend.scenario import SolverSettings
from backend.scenario_convert import scenario_to_v1
from backend.scenario_v2 import ScenarioV2, SeriesData
from backend.service import ScenarioError
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.forms import set_value
from tests.helpers import needs_cbc

needs_highs = pytest.mark.skipif(not solving.highs_available(), reason="highspy is not installed")

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"


def example(name, solver=None):
    scenario = ScenarioV2.load(EXAMPLES / f"{name}.json")
    if solver is not None:
        scenario.solver.name = solver
    return scenario


def many_components(steps=48):
    """A system with every component, all of them in investment mode without an upper limit."""

    draft = ScenarioDraft(steps=steps)
    draft.apply_template("Full system")
    for key in ("pv", "wind", "gas_boiler", "heating_rod", "chp", "heat_pump", "battery", "heat_storage"):
        set_value(draft.component(key), "capacity", "mode", "invest")
    set_value(draft.component("grid_feedin"), "costs", "revenue", 0.02)           # feeding in does not pay: bounded

    def shares(values):
        total = sum(values)
        return [v / total for v in values]

    hours = range(steps)
    draft.set_series("demand", SeriesData(values=shares([0.6 + 0.4 * max(0.0, math.sin((h % 24 - 6) / 12 * math.pi)) for h in hours])))
    draft.set_series("heat_demand", SeriesData(values=shares([1.2 + math.cos(h / 24) for h in hours])))
    draft.set_series("pv", SeriesData(values=[max(0.0, math.sin((h % 24 - 6) / 12 * math.pi)) * 0.6 for h in hours]))
    draft.set_series("wind", SeriesData(values=[0.3 + 0.2 * math.sin(h / 5) for h in hours]))

    return draft.scenario()


def unbounded_scenario():
    """PV without an upper limit, and feeding in pays far more than a plant costs: it would build for ever."""

    draft = ScenarioDraft(steps=24)
    draft.apply_template("PV system")
    draft.set("grid_feedin", True)
    set_value(draft.component("pv"), "capacity", "mode", "invest")
    set_value(draft.component("grid_feedin"), "costs", "revenue", 1.0)
    draft.set_series("demand", SeriesData(values=[1 / 24] * 24))
    draft.set_series("pv", SeriesData(values=[max(0.0, math.sin((h - 6) / 12 * math.pi)) for h in range(24)]))

    return draft.scenario()


def infeasible_scenario():
    """A demand and nothing that supplies it."""

    draft = ScenarioDraft(steps=24)
    draft.apply_template("Electricity only")
    draft.set("grid", False)
    draft.set_series("demand", SeriesData(values=[1 / 24] * 24))

    return draft.scenario()


def run(scenario, solver):
    scenario.solver.name = solver
    return service_v2.run(scenario)


def capacity_rows(result):
    return [(row[0], row[2]) for row in result.capacities.rows]


# ---------------------------------------------------------------------------
# which solver is the standard
# ---------------------------------------------------------------------------

def test_highs_is_the_standard_everywhere():
    assert solving.SOLVERS == ("highs", "cbc") and solving.DEFAULT_SOLVER == "highs"
    assert SolverSettings().name == "highs" and SolverConfig().name == "highs"
    assert ScenarioV2().solver.name == "highs" and ScenarioDraft().scenario().solver.name == "highs"


def test_the_schema_allows_exactly_the_solvers_of_the_module():
    assert get_args(SolverSettings.model_fields["name"].annotation) == solving.SOLVERS

    with pytest.raises(ValidationError):
        SolverSettings(name="gurobi")


def test_a_solver_that_does_not_exist_is_refused_before_anything_is_done():
    with pytest.raises(ValueError, match="unknown solver 'gurobi'; use one of highs, cbc"):
        solving.solve(object(), "gurobi")


# ---------------------------------------------------------------------------
# the same answers
# ---------------------------------------------------------------------------

@needs_cbc
@needs_highs
def test_both_solvers_give_the_same_answer_for_the_example():
    highs, cbc = run(example("pv_and_grid"), "highs"), run(example("pv_and_grid"), "cbc")

    assert highs.objective == pytest.approx(cbc.objective, rel=1e-6)
    assert [row[0] for row in capacity_rows(highs)] == [row[0] for row in capacity_rows(cbc)]
    assert [row[1] for row in capacity_rows(highs)] == pytest.approx([row[1] for row in capacity_rows(cbc)], abs=1e-6)


@needs_cbc
@needs_highs
def test_both_solvers_give_the_same_answer_for_a_system_with_every_component():
    highs, cbc = run(many_components(), "highs"), run(many_components(), "cbc")

    assert highs.objective == pytest.approx(cbc.objective, rel=1e-6)
    assert [row[1] for row in capacity_rows(highs)] == pytest.approx([row[1] for row in capacity_rows(cbc)], abs=1e-4)
    assert [f.value for f in highs.key_figures] == pytest.approx([f.value for f in cbc.key_figures], rel=1e-6, abs=1e-6)
    assert any(size > 0 for _, size in capacity_rows(highs))                  # something was built: the test says something


@needs_highs
def test_the_hand_calculated_cost_comes_out_exactly_with_highs():
    result = run(example("pv_and_grid"), "highs")

    assert result.objective == pytest.approx(72.0, abs=1e-9)


@needs_highs
def test_a_zero_is_written_as_a_zero_and_not_as_minus_zero():
    result = run(many_components(), "highs")
    values = [size for _, size in capacity_rows(result)] + [f.value for f in result.key_figures if f.value is not None]

    zeros = [v for v in values if v == 0]
    assert zeros, "the system should leave something unbuilt"
    assert all(math.copysign(1.0, v) > 0 for v in zeros)


def test_a_zero_that_a_solver_wrote_with_a_rounding_error_becomes_a_zero():
    model = ConcreteModel()
    model.v = Var(range(6), domain=NonNegativeReals)
    for i, value in enumerate([-0.0, -1e-12, 1e-12, 1e-6, 5.0, None]):
        if value is not None:
            model.v[i].set_value(value, skip_validation=True)

    solving._clean_zeros(model)

    values = [model.v[i].value for i in range(6)]
    assert values[:3] == [0.0, 0.0, 0.0] and all(math.copysign(1.0, v) > 0 for v in values[:3])
    assert values[3:5] == [1e-6, 5.0] and values[5] is None


# ---------------------------------------------------------------------------
# what ran, and how long it took
# ---------------------------------------------------------------------------

@needs_highs
def test_the_standard_solver_runs_and_the_result_says_so():
    result = run(example("pv_and_grid"), "highs")

    assert result.solver.name == "highs" and result.solver.termination == "optimal"
    assert result.solver.seconds is not None and result.solver.seconds >= 0


@needs_cbc
def test_a_scenario_that_asks_for_cbc_is_run_by_cbc():
    result = run(example("pv_and_grid"), "cbc")

    assert result.solver.name == "cbc" and result.objective == pytest.approx(72.0, rel=1e-6)


@needs_cbc
@needs_highs
@pytest.mark.parametrize("solver", ["highs", "cbc"])
def test_the_time_is_measured_here_for_every_solver(monkeypatch, solver):
    clock = iter([100.0, 102.5])
    monkeypatch.setattr(solving, "time", types.SimpleNamespace(perf_counter=lambda: next(clock)))

    result = run(example("pv_and_grid"), solver)

    assert result.solver.seconds == 2.5


@needs_cbc
def test_without_highs_cbc_runs_instead_and_the_result_and_the_log_say_so(monkeypatch, caplog):
    monkeypatch.setattr(solving, "highs_available", lambda: False)

    with caplog.at_level(logging.WARNING, logger="backend.solving"):
        result = run(example("pv_and_grid"), "highs")

    assert result.solver.name == "cbc" and result.objective == pytest.approx(72.0, rel=1e-6)
    assert [r.getMessage() for r in caplog.records if r.name == "backend.solving"] == [
        "HiGHS (the package highspy) is not installed: the model is solved with CBC instead"]


@needs_cbc
@needs_highs
@pytest.mark.parametrize("asked, installed, expected", [
    ("highs", True, "highs"),
    ("cbc", True, "cbc"),
    ("highs", False, "cbc"),          # HiGHS is asked for but not installed
    ("cbc", False, "cbc"),
])
def test_the_solver_that_is_called_is_the_one_that_the_result_names(monkeypatch, asked, installed, expected):
    # watch which program is really called: the name in the result must not say something else
    called = []
    for name in ("highs", "cbc"):
        original = getattr(solving, f"_solve_{name}")
        monkeypatch.setattr(solving, f"_solve_{name}", lambda model, tee, n=name, f=original: (called.append(n), f(model, tee))[1])
    monkeypatch.setattr(solving, "highs_available", lambda: installed)

    result = run(example("pv_and_grid"), asked)

    assert called == [expected] and result.solver.name == expected


@needs_highs
def test_highs_is_not_replaced_when_it_is_installed(caplog):
    with caplog.at_level(logging.WARNING, logger="backend.solving"):
        result = run(example("pv_and_grid"), "highs")

    assert result.solver.name == "highs" and not [r for r in caplog.records if r.name == "backend.solving"]


# ---------------------------------------------------------------------------
# when there is no optimum: the same words for both solvers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("solver", [pytest.param("highs", marks=needs_highs), pytest.param("cbc", marks=needs_cbc)])
@pytest.mark.parametrize("make, word", [(unbounded_scenario, "unbounded"), (infeasible_scenario, "infeasible")])
def test_a_problem_without_an_optimum_is_explained_in_the_same_words_by_both_solvers(solver, make, word):
    with pytest.raises(ScenarioError) as raised:
        service.run(scenario_to_v1(_with_solver(make(), solver)), check_first=False)

    message = str(raised.value)
    assert message.startswith("The solver did not return an optimal solution. Instead the optimization ended with")
    assert f"termination condition: {word}" in message
    assert raised.value.termination == word                              # the reason, to be explained in other words
    assert isinstance(raised.value.__cause__, solving.NotOptimal)


def _with_solver(scenario, solver):
    scenario.solver.name = solver
    return scenario


@needs_highs
def test_the_solver_does_not_leave_the_model_changed_for_the_post_processing():
    # the interface of HiGHS needs two attributes of the model removed while it solves; they are back afterwards
    result = run(many_components(), "highs")

    assert result.solver.termination == "optimal" and result.capacities.rows        # the tables are made from the solution


# ---------------------------------------------------------------------------
# the reason that a solver gave
# ---------------------------------------------------------------------------

def test_the_reason_of_a_failed_run_comes_with_the_error_and_survives_the_trip_between_processes():
    # a run happens in another process: the error is sent back by pickle and must keep its reason
    error = ScenarioError("no optimum", termination="unbounded")
    copy = pickle.loads(pickle.dumps(error))

    assert (str(copy), copy.termination) == ("no optimum", "unbounded")
    assert pickle.loads(pickle.dumps(ScenarioError("plain"))).termination is None
    assert ScenarioError("plain").termination is None


def test_not_optimal_has_status_and_reason_and_survives_pickle_too():
    error = solving.NotOptimal("warning", "unbounded")
    copy = pickle.loads(pickle.dumps(error))

    assert (copy.status, copy.termination, str(copy)) == ("warning", "unbounded", str(error))
    assert isinstance(error, RuntimeError)                               # the callers that catch RuntimeError still do


def test_an_error_of_oemof_that_gives_no_reason_is_not_changed():
    class Model:
        def solve(self, **options):
            raise RuntimeError("something else went wrong")

    with pytest.raises(RuntimeError, match="something else went wrong") as raised:
        solving._solve_cbc(Model(), False)

    assert not isinstance(raised.value, solving.NotOptimal)


def test_the_reason_is_taken_from_the_words_of_oemof():
    class Model:
        def solve(self, **options):
            raise RuntimeError(
                "The solver did not return an optimal solution. Instead the optimization ended with\n"
                "       - status: warning\n       - termination condition: unbounded")

    with pytest.raises(solving.NotOptimal) as raised:
        solving._solve_cbc(Model(), False)

    assert (raised.value.status, raised.value.termination) == ("warning", "unbounded")