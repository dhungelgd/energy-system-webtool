"""The two things a frontend needs from the backend: check a scenario, run it.

Both frontends (Streamlit now, NiceGUI later) call these functions and nothing
else, so the order of the steps (check, build the model, solve, collect the
numbers) lives in one place.

    findings = check(scenario)        # problems and warnings, before a run
    result = run(scenario)            # a ScenarioResult, or a ScenarioError

This module does not use Streamlit, so any frontend can use it.
"""

from backend.config_builder import build_config
from backend.results import ScenarioResult
from backend.results_summary import collect_results
from backend.scenario_runner import run_scenario
from backend.system_check import check_system


class ScenarioError(Exception):
    """The optimization could not be completed. The message is for the user."""


class ScenarioNotReady(ScenarioError):
    """The system check found errors, so the optimization was not started.

    `findings` holds the errors (Finding objects, as `check` returns them).
    """

    def __init__(self, findings):
        self.findings = list(findings)

        problems = " ".join(f"({n}) {f.message}" for n, f in enumerate(self.findings, 1))
        super().__init__(f"The system check found errors. {problems}")


def check(scenario, labels=None):
    """The findings of the system check for a scenario (errors first).

    labels: readable component names for the messages, e.g. {"pv": "PV System"}.
    """

    selected, tech_inputs, input_data, _ = scenario.to_inputs()

    return check_system(selected, tech_inputs, input_data, labels=labels)


def run(scenario, include_flows=True, check_first=True):
    """Check a scenario, optimize it, and return the numbers as a ScenarioResult.

    include_flows=False leaves out the hourly flows (a much smaller result).
    check_first=False skips the system check; problems then show up as a
    ScenarioError from the model itself.

    Raises ScenarioNotReady if the system check finds errors, and ScenarioError
    if the model cannot be built or solved (for example a missing capacity, or a
    system that cannot be balanced).
    """

    if check_first:
        errors = [f for f in check(scenario) if f.level == "error"]
        if errors:
            raise ScenarioNotReady(errors)

    selected, tech_inputs, input_data, solver = scenario.to_inputs()

    try:
        config = build_config(
            selected_techs=selected,
            tech_inputs=tech_inputs,
            input_data=input_data,
            solver_cfg=solver,
        )

        # ValueError: an input problem found by the backend
        # RuntimeError: the solver found no optimal solution
        _, results, meta_results, _ = run_scenario(
            config, input_data, selected_techs=selected, plot_graph=False
        )

        output = collect_results(results, meta_results, config, selected)

    except (ValueError, RuntimeError) as error:
        raise ScenarioError(str(error)) from error

    return ScenarioResult.from_output(output, meta_results, include_flows=include_flows)