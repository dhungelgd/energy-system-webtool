"""The Run button of the NiceGUI interface (needs NiceGUI; the real solves need CBC)."""

import asyncio
import shutil
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("nicegui")
from nicegui import run  # noqa: E402
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402

from backend import service  # noqa: E402
from backend.results import KeyFigure, ScenarioResult, SolverInfo, Table  # noqa: E402
from backend.scenario import Scenario  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios"

needs_cbc = pytest.mark.skipif(shutil.which("cbc") is None, reason="CBC solver is not installed")


def fake_result(cost=72.0, seconds=1.5):
    return ScenarioResult(
        objective=cost, horizon_hours=24,
        solver=SolverInfo(status="ok", termination="optimal", seconds=seconds),
        key_figures=[
            KeyFigure(label="System cost (simulated period)", value=cost, unit="€", help="The objective."),
            KeyFigure(label="Grid import", value=240.0, unit="kWh"),
        ],
        cost_breakdown=Table(columns=[]), capacities=Table(columns=[]),
    )


async def open_example(user: User, name: str):
    await user.open("/")
    upload = user.find(marker="upload").elements.pop()
    content = (EXAMPLES / f"{name}.json").read_bytes()
    await upload.handle_uploads([SmallFileUpload(f"{name}.json", "application/json", content)])
    await user.should_see(marker="scenario-name")


def run_button(user: User):
    return user.find(marker="run").elements.pop()


def page():
    """The page module as the simulated app has loaded it.

    Never import frontend_nicegui.app at the top of a test file: NiceGUI removes
    the registered pages before every test and loads the main file again, which
    only registers the pages if the module is not already imported.
    """

    return sys.modules["frontend_nicegui.app"]


def use_solver(monkeypatch, solver):
    monkeypatch.setattr(page(), "solve", solver)


# ---------------------------------------------------------------------------
# when the button is there
# ---------------------------------------------------------------------------

async def test_a_scenario_without_errors_offers_to_run(user: User):
    await open_example(user, "grid_only_24h")

    await user.should_see("Run the optimization")
    await user.should_see(marker="run")


async def test_a_scenario_with_errors_does_not_offer_to_run(user: User):
    await open_example(user, "with_problems_24h")

    await user.should_see("Fix the errors above")
    await user.should_not_see(marker="run")
    await user.should_not_see("Run the optimization")


async def test_a_scenario_with_only_warnings_can_be_run(user: User):
    import json

    scenario = json.loads((EXAMPLES / "with_problems_24h.json").read_text(encoding="utf-8"))
    scenario["series"]["electricity_demand"] = [1.0] * 24

    await user.open("/")
    upload = user.find(marker="upload").elements.pop()
    await upload.handle_uploads([SmallFileUpload("w.json", "application/json", json.dumps(scenario).encode())])

    await user.should_see(marker="run")


# ---------------------------------------------------------------------------
# what happens when it is pressed (fast fake solver)
# ---------------------------------------------------------------------------

async def test_the_headline_figures_are_shown(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_example(user, "grid_only_24h")

    user.find(marker="run").click()

    await user.should_see("System cost (simulated period)")
    await user.should_see("72 €")
    await user.should_see("240 kWh")
    await user.should_see("Solver: optimal in 1.5 s")
    assert len(user.find(marker="headline").elements) == 2


async def test_the_solver_gets_the_scenario_that_was_opened(user: User, monkeypatch):
    received = []

    async def solver(scenario):
        received.append(scenario)
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_example(user, "grid_only_24h")
    user.find(marker="run").click()
    await user.should_see("72 €")

    assert len(received) == 1
    assert isinstance(received[0], Scenario)
    assert received[0].name == "Grid only, 24 hours"


async def test_the_button_is_blocked_while_it_runs_and_free_again_afterwards(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_example(user, "grid_only_24h")

    user.find(marker="run").click()
    await user.should_see("Running the optimization...")
    assert not run_button(user).enabled
    await user.should_not_see("System cost")

    release.set()
    await user.should_see("72 €")

    assert run_button(user).enabled
    await user.should_not_see("Running the optimization...")


async def test_pressing_again_replaces_the_old_result(user: User, monkeypatch):
    costs = iter([72.0, 36.0])

    async def solver(scenario):
        return fake_result(cost=next(costs))

    use_solver(monkeypatch, solver)
    await open_example(user, "grid_only_24h")

    user.find(marker="run").click()
    await user.should_see("72 €")
    user.find(marker="run").click()
    await user.should_see("36 €")

    await user.should_not_see("72 €")
    assert len(user.find(marker="headline").elements) == 2


async def test_a_problem_found_by_the_optimization_is_explained(user: User, monkeypatch):
    async def solver(scenario):
        raise service.ScenarioError("the solver found no solution")

    use_solver(monkeypatch, solver)
    await open_example(user, "grid_only_24h")

    user.find(marker="run").click()

    await user.should_see("The optimization could not be completed: the solver found no solution")
    await user.should_not_see(marker="headline")
    assert run_button(user).enabled


async def test_an_unexpected_failure_keeps_the_page_alive_and_hides_the_details(
    user: User, monkeypatch, caplog
):
    async def solver(scenario):
        raise RuntimeError("secret internal detail")

    use_solver(monkeypatch, solver)
    await open_example(user, "grid_only_24h")

    user.find(marker="run").click()

    await user.should_see("The optimization stopped unexpectedly.")
    await user.should_not_see("secret internal detail")
    assert run_button(user).enabled
    assert "secret internal detail" in caplog.text        # but it is logged for the developers
    caplog.clear()                                         # the log entry is expected here


async def test_a_new_file_removes_the_old_result(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await open_example(user, "grid_only_24h")
    user.find(marker="run").click()
    await user.should_see("72 €")

    upload = user.find(marker="upload").elements.pop()
    content = (EXAMPLES / "pv_battery_week.json").read_bytes()
    await upload.handle_uploads([SmallFileUpload("pv.json", "application/json", content)])

    await user.should_see("PV and battery, one week in June")
    await user.should_not_see("72 €")


# ---------------------------------------------------------------------------
# the real thing: another process
# ---------------------------------------------------------------------------

async def test_the_processes_are_started_the_safe_way_on_every_system(user: User, monkeypatch):
    monkeypatch.setattr(page().ui, "run", lambda **kwargs: None)
    monkeypatch.setattr(run, "process_pool_start_method", None)

    page().run_server()

    assert run.process_pool_start_method == "spawn"


@needs_cbc
async def test_a_real_run_in_another_process_gives_the_hand_calculated_cost(user: User):
    await open_example(user, "grid_only_24h")

    user.find(marker="run").click()

    # starting the process takes a moment
    await user.should_see("72 €", retries=200)
    await user.should_see("Solver: optimal")


def year_scenario():
    return Scenario(
        components=["demand", "grid"],
        settings={"demand": {"scaling_factor": 100.0},
                  "grid": {"price_mode": "constant", "variable_costs": 0.3}},
        series={"electricity_demand": [0.5 + (i % 24) / 48 for i in range(8760)]},
    )


@needs_cbc
async def test_the_page_stays_responsive_while_a_year_is_solved(user: User):
    await user.open("/")
    ticks = 0
    finished = False

    async def heartbeat():
        nonlocal ticks
        while not finished:
            await asyncio.sleep(0.05)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    started = time.perf_counter()
    result = await page().solve(year_scenario())
    seconds = time.perf_counter() - started
    finished = True
    await beat

    possible = seconds / 0.05
    assert result.solver.termination == "optimal"
    # a solve inside the loop would leave a handful of ticks, not most of them
    assert ticks > 0.6 * possible, f"only {ticks} of about {possible:.0f} ticks"