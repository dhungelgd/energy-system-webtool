"""Running the scenario that is being built, on the NiceGUI page (simulated user; the real solve needs CBC)."""

import asyncio
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("nicegui")
from nicegui import ElementFilter  # noqa: E402
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402

from backend.i18n import catalog  # noqa: E402
from backend.results import KeyFigure, ScenarioResult, SolverInfo, Table  # noqa: E402
from backend.scenario_v2 import ScenarioV2  # noqa: E402
from backend.service import ScenarioError  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"

needs_cbc = pytest.mark.skipif(shutil.which("cbc") is None, reason="CBC solver is not installed")

PRICE = "field-grid-costs-variable_costs"


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


def page():
    """The page module as the simulated app has loaded it (never import it at the top of a test file)."""

    return sys.modules["frontend_nicegui.app"]


def use_solver(monkeypatch, solver):
    monkeypatch.setattr(page(), "solve", solver)


def field(user: User, marker: str):
    return user.find(marker=marker).elements.pop()


def exists(user: User, marker: str):
    with user.client:
        return bool(list(ElementFilter(marker=marker)))


def run_button(user: User):
    return field(user, "draft-run")


async def settle():
    await asyncio.sleep(0.4)


def day_csv(values):
    rows = ["Zeit;Last"] + [f"2021-01-01 {h:02d}:00;{v}" for h, v in enumerate(values)]
    return ("\n".join(rows) + "\n").encode()


DAY = [round(1 + h / 10, 1) for h in range(24)]


async def give_demand(user: User, values=DAY):
    await field(user, "series-upload-demand").handle_uploads([SmallFileUpload("last.csv", "text/csv", day_csv(values))])
    await user.should_see(marker="series-prepare-demand")
    user.find(marker="series-use-demand").click()
    await user.should_see(marker="series-summary-demand")
    await settle()


async def build_draft(user: User, language=None, with_data=True):
    """Open the page and build a draft for one day: a demand, and the grid (with data if asked)."""

    await user.open("/" if language is None else f"/?lang={language}")
    user.find(marker="template-electricity-only").click()
    await user.should_see(marker="selection-count")
    user.find(marker="draft-steps").clear().type("24")
    await settle()
    if with_data:
        await give_demand(user)


async def switched_to(user: User, language: str):
    field(user, "language").value = language
    await user.should_see(marker="app-title", content=catalog(language)["app.title"])


# ---------------------------------------------------------------------------
# when the card to run is there
# ---------------------------------------------------------------------------

async def test_there_is_no_card_to_run_while_the_check_finds_errors(user: User):
    await build_draft(user, with_data=False)                          # the demand has no data

    await user.should_see("Fix the errors above")
    assert not exists(user, "draft-run")
    await user.should_not_see("Run the optimization")


async def test_a_draft_without_errors_offers_to_run(user: User):
    await build_draft(user)

    await user.should_see("Run the optimization")
    assert exists(user, "draft-run") and run_button(user).enabled


async def test_the_card_goes_away_when_the_data_is_taken_away_and_comes_back_with_it(user: User):
    await build_draft(user)
    assert exists(user, "draft-run")

    user.find(marker="series-remove-demand").click()
    await settle()
    assert not exists(user, "draft-run")

    await give_demand(user)
    assert exists(user, "draft-run")


async def test_nothing_is_offered_when_nothing_is_chosen(user: User):
    await user.open("/")

    assert not exists(user, "draft-run") and not exists(user, "draft-results")


# ---------------------------------------------------------------------------
# what is run, and what is shown
# ---------------------------------------------------------------------------

async def test_the_solver_gets_the_scenario_that_was_built(user: User, monkeypatch):
    received = []

    async def solver(scenario):
        received.append(scenario)
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-name").clear().type("My system")
    await settle()

    user.find(marker="draft-run").click()
    await user.should_see("72 €")

    assert len(received) == 1 and isinstance(received[0], ScenarioV2)
    scenario = received[0]
    assert scenario.name == "My system" and scenario.time.steps == 24
    assert [c.id for c in scenario.components] == ["demand", "grid"]
    assert scenario.series["electricity_demand"].values == DAY


async def test_a_scenario_without_a_name_is_run_with_the_default_name_in_the_language_of_the_page(user: User, monkeypatch):
    received = []

    async def solver(scenario):
        received.append(scenario.name)
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user, language="de")

    user.find(marker="draft-run").click()
    await user.should_see("72 €")

    assert received == [catalog("de")["scenario.default_name"]]


async def test_the_headline_figures_are_shown_below_the_check(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)

    user.find(marker="draft-run").click()

    await user.should_see("System cost (simulated period)")
    await user.should_see("72 €")
    await user.should_see("240 kWh")
    await user.should_see("Solver: optimal in 1.5 s")
    assert len(user.find(marker="headline").elements) == 2
    results = list(user.client.content.descendants())
    assert results.index(field(user, "draft-findings")) < results.index(field(user, "draft-run")) \
        < results.index(field(user, "draft-results")) < results.index(field(user, "form-demand"))
    assert not exists(user, "draft-outdated")


async def test_the_button_is_blocked_while_it_runs_and_so_is_the_language_and_both_are_free_afterwards(
    user: User, monkeypatch
):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)

    user.find(marker="draft-run").click()
    await user.should_see("Running the optimization...")
    assert not run_button(user).enabled
    assert not field(user, "language").enabled
    await user.should_not_see("System cost")

    release.set()
    await user.should_see("72 €")

    assert run_button(user).enabled and field(user, "language").enabled
    await user.should_not_see("Running the optimization...")


async def test_pressing_twice_at_once_runs_once(user: User, monkeypatch):
    release = asyncio.Event()
    calls = []

    async def solver(scenario):
        calls.append(1)
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)

    user.find(marker="draft-run").click()
    user.find(marker="draft-run").click()
    await user.should_see("Running the optimization...")
    release.set()
    await user.should_see("72 €")

    assert len(calls) == 1


async def test_pressing_again_replaces_the_old_result(user: User, monkeypatch):
    costs = iter([72.0, 36.0])

    async def solver(scenario):
        return fake_result(cost=next(costs))

    use_solver(monkeypatch, solver)
    await build_draft(user)

    user.find(marker="draft-run").click()
    await user.should_see("72 €")
    user.find(marker="draft-run").click()
    await user.should_see("36 €")

    await user.should_not_see("72 €")
    assert len(user.find(marker="headline").elements) == 2


# ---------------------------------------------------------------------------
# a result belongs to the scenario that was run
# ---------------------------------------------------------------------------

async def test_a_change_after_the_run_keeps_the_result_but_says_that_it_is_outdated(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("72 €")
    assert not exists(user, "draft-outdated")

    user.find(marker=PRICE).clear().type("0.35")
    await settle()

    await user.should_see("You changed the scenario after this run.")
    await user.should_see("72 €")                                         # the result stays to look at

    user.find(marker="draft-run").click()                                 # a new run makes it current again
    await settle()
    assert not exists(user, "draft-outdated")


async def test_a_change_while_the_optimization_runs_makes_the_result_outdated_when_it_arrives(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("Running the optimization...")

    user.find(marker=PRICE).clear().type("0.35")                          # the form can be used while it runs
    await settle()
    release.set()
    await user.should_see("72 €")

    await user.should_see("You changed the scenario after this run.")      # the result is for the scenario as it was run


async def test_the_name_of_the_scenario_does_not_make_the_result_outdated(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("72 €")

    user.find(marker="draft-name").clear().type("Another name")
    await settle()

    assert not exists(user, "draft-outdated")


async def test_a_result_stays_when_a_change_leaves_errors_and_the_card_to_run_goes(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("72 €")

    user.find(marker="series-remove-demand").click()
    await settle()

    assert not exists(user, "draft-run")                                   # nothing to run now ...
    await user.should_see("72 €")                                          # ... but the result is still there
    await user.should_see("You changed the scenario after this run.")


async def test_clearing_the_selection_removes_the_result(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("72 €")

    user.find(marker="clear-selection").click()
    await settle()
    user.find(marker="template-electricity-only").click()
    await user.should_see(marker="selection-count")

    assert not exists(user, "draft-results")


async def test_the_result_stays_when_the_language_changes_and_its_numbers_follow_the_language(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result(cost=1234.0)

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("1,234 €")

    await switched_to(user, "de")

    await user.should_see("Ergebnisse")
    await user.should_see("1.234 €")
    await user.should_see("Solver: optimal in 1,5 s")
    assert not exists(user, "draft-outdated")                              # a change of the language is no change
    assert len(user.find(marker="headline").elements) == 2


# ---------------------------------------------------------------------------
# when it does not work
# ---------------------------------------------------------------------------

async def test_a_problem_found_by_the_optimization_is_explained_and_the_button_is_free_again(user: User, monkeypatch):
    async def solver(scenario):
        raise ScenarioError("the solver found no solution")

    use_solver(monkeypatch, solver)
    await build_draft(user)

    user.find(marker="draft-run").click()

    await user.should_see("The optimization could not be completed: the solver found no solution")
    assert not exists(user, "headline") and run_button(user).enabled and field(user, "language").enabled


async def test_a_problem_with_the_run_is_explained_in_german(user: User, monkeypatch):
    async def solver(scenario):
        raise ScenarioError("no solution")

    use_solver(monkeypatch, solver)
    await build_draft(user, language="de")

    user.find(marker="draft-run").click()

    await user.should_see("Die Optimierung konnte nicht abgeschlossen werden: no solution")


async def test_an_unexpected_failure_keeps_the_page_alive_and_hides_the_details(user: User, monkeypatch, caplog):
    async def solver(scenario):
        raise RuntimeError("secret internal detail")

    use_solver(monkeypatch, solver)
    await build_draft(user)

    user.find(marker="draft-run").click()

    await user.should_see("The optimization stopped unexpectedly.")
    await user.should_not_see("secret internal detail")
    assert run_button(user).enabled
    assert "secret internal detail" in caplog.text                          # but it is logged for the developers
    caplog.clear()                                                          # the log entry is expected here


async def test_the_error_of_an_earlier_version_is_not_shown_after_a_change(user: User, monkeypatch):
    async def solver(scenario):
        raise ScenarioError("the solver found no solution")

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("the solver found no solution")

    user.find(marker=PRICE).clear().type("0.35")
    await settle()

    await user.should_not_see("the solver found no solution")


# ---------------------------------------------------------------------------
# the draft and an opened file
# ---------------------------------------------------------------------------

async def open_example(user: User, name: str):
    content = (EXAMPLES / f"{name}.json").read_bytes()
    await field(user, "upload").handle_uploads([SmallFileUpload(f"{name}.json", "application/json", content)])
    await user.should_see(marker="scenario-name")


async def test_the_run_of_the_draft_and_the_run_of_an_opened_file_are_separate(user: User, monkeypatch):
    costs = iter([72.0, 36.0])

    async def solver(scenario):
        return fake_result(cost=next(costs))

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("72 €")

    await open_example(user, "pv_and_grid")
    await user.should_not_see("36 €")                                     # the file has not been run
    user.find(marker="run").click()
    await user.should_see("36 €")

    await user.should_see("72 €")                                         # and the result of the draft is still there
    assert len(user.find(marker="headline").elements) == 4


async def test_while_the_draft_runs_the_opened_file_cannot_be_run_and_shows_no_spinner(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    await open_example(user, "pv_and_grid")

    user.find(marker="draft-run").click()
    await user.should_see("Running the optimization...")

    assert not field(user, "run").enabled
    assert len(user.find(content="Running the optimization...").elements) == 1      # one spinner text, in the draft

    release.set()
    await user.should_see("72 €")
    assert field(user, "run").enabled


async def test_while_the_opened_file_runs_the_draft_cannot_be_run_and_shows_no_spinner(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    await open_example(user, "pv_and_grid")

    user.find(marker="run").click()
    await user.should_see("Running the optimization...")

    assert not run_button(user).enabled
    assert len(user.find(content="Running the optimization...").elements) == 1      # one spinner text, in the file

    release.set()
    await user.should_see("72 €")
    assert run_button(user).enabled


# ---------------------------------------------------------------------------
# the real thing: another process, with a cost that can be calculated by hand
# ---------------------------------------------------------------------------

@needs_cbc
async def test_a_real_run_of_the_draft_gives_the_hand_calculated_cost(user: User):
    await build_draft(user, with_data=False)
    field(user, "field-demand-demand-profile_type").value = "absolute"        # a demand in kW
    await settle()
    await give_demand(user, values=[10.0] * 24)                               # 10 kW for a day
    user.find(marker=PRICE).clear().type("0.3")                               # at 0.30 EUR per kWh
    await settle()

    user.find(marker="draft-run").click()

    # starting the process takes a moment: 24 h x 10 kW x 0.30 EUR/kWh = 72 EUR, and 240 kWh from the grid
    await user.should_see("72 €", retries=200)
    await user.should_see("240 kWh")
    await user.should_see("Solver: optimal")
    assert not exists(user, "draft-outdated")