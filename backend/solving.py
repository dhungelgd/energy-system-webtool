"""Solving the optimization model: with HiGHS (the standard) or with CBC.

Both give the same optimum: on a whole year of a system with 13 components every plant size was the same to
three decimals and the cost differed in the eighth digit. HiGHS needed a third of the time of CBC (45 s against
138 s on one machine).

HiGHS comes with the Python package `highspy`. CBC is a program that has to be installed on its own. If HiGHS is
asked for but not installed, CBC runs instead, and the result says which solver ran.

The time is measured here (the whole solve, as the visitor waits for it): HiGHS does not report one, and the
time that CBC reports leaves out the writing of the problem.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

import logging
import re
import time
from dataclasses import dataclass

from pyomo.environ import Var
from pyomo.opt import SolverFactory

logger = logging.getLogger(__name__)

SOLVERS = ("highs", "cbc")
DEFAULT_SOLVER = "highs"

# a value smaller than this is a zero that the solver wrote with a rounding error (or as -0.0)
ZERO = 1e-9

# oemof leaves None in these two attributes of the model, and the interface of HiGHS asks them
EMPTY_SUFFIXES = ("dual", "rc")


class NotOptimal(RuntimeError):
    """The solver did not find an optimal solution. `termination` says why: 'unbounded', 'infeasible', ..."""

    def __init__(self, status, termination):
        self.status = str(status)
        self.termination = str(termination)

        super().__init__(
            "The solver did not return an optimal solution. Instead the optimization ended with\n"
            f"       - status: {self.status}\n"
            f"       - termination condition: {self.termination}"
        )

    def __reduce__(self):
        return (type(self), (self.status, self.termination))


@dataclass(frozen=True)
class SolveInfo:
    """What happened: which solver ran, and how many seconds the solve took."""

    name: str
    seconds: float


def highs_available():
    """True if the package of HiGHS (highspy) is installed."""

    try:
        import highspy  # noqa: F401
    except ImportError:
        return False

    return True


def solve(model, name=DEFAULT_SOLVER, tee=False):
    """Solve an oemof model with the solver `name` and return a SolveInfo.

    NotOptimal (a RuntimeError) if the solver does not find an optimal solution: its `termination` and its
    message give the reason, for example 'unbounded' or 'infeasible', in the same words for both solvers.
    ValueError for a solver that does not exist.
    """

    if name not in SOLVERS:
        raise ValueError(f"unknown solver '{name}'; use one of {', '.join(SOLVERS)}")

    ran = name
    if name == "highs" and not highs_available():
        logger.warning("HiGHS (the package highspy) is not installed: the model is solved with CBC instead")
        ran = "cbc"

    started = time.perf_counter()
    (_solve_highs if ran == "highs" else _solve_cbc)(model, tee)
    seconds = time.perf_counter() - started

    _clean_zeros(model)

    return SolveInfo(name=ran, seconds=seconds)


def _solve_cbc(model, tee):
    try:
        model.solve(solver="cbc", solve_kwargs={"tee": tee})
    except RuntimeError as error:
        # oemof says why in its message; the same error as HiGHS gives, so that the reason can be asked for
        found = re.search(r"status:\s*(\S+).*?termination condition:\s*(\S+)", str(error), re.DOTALL)
        if found is None:
            raise
        raise NotOptimal(found.group(1), found.group(2)) from error


def _solve_highs(model, tee):
    opt = SolverFactory("appsi_highs")

    hidden = [name for name in EMPTY_SUFFIXES if hasattr(model, name) and getattr(model, name) is None]
    for name in hidden:
        delattr(model, name)
    try:
        results = opt.solve(model, tee=tee, load_solutions=False)
    finally:
        for name in hidden:
            setattr(model, name, None)

    # the post-processing of oemof reads these two
    model.solver_results = results
    model.es.results = results

    status = results.solver.status
    termination = results.solver.termination_condition
    if not (status == "ok" and termination == "optimal"):
        raise NotOptimal(status, termination)

    model.solutions.load_from(results)


def _clean_zeros(model):
    """Write a zero as 0.0: a solver can leave -0.0 or 1e-12 behind, and a visitor would read '-0.0 kW'."""

    for variable in model.component_data_objects(Var, active=True):
        if variable.value is not None and abs(variable.value) < ZERO:
            variable.set_value(0.0, skip_validation=True)