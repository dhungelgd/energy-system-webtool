"""What the NiceGUI pages show about a result.

No NiceGUI code in here, only the decisions about what to show and how to word
it, so that it is easy to test. What is shown in words takes a translator `tr`
(English if none is given). The labels of the key figures come from the backend and
are English for now.
"""

from backend.i18n import ENGLISH, Msg


def format_value(value, unit, tr=ENGLISH):
    """Readable text for one key figure (the same wording as the Streamlit page)."""

    if value is None:
        return "-"

    if unit == "%":
        return f"{tr.localize(f'{value:.0f}')} %"
    if unit == "€":
        return f"{tr.localize(f'{value:,.0f}')} €"
    if unit == "kW":
        return f"{tr.localize(f'{value:,.1f}')} kW"
    if unit == "kWh":
        if abs(value) >= 10000:
            return f"{tr.localize(f'{value / 1000:,.1f}')} MWh"
        return f"{tr.localize(f'{value:,.0f}')} kWh"

    return f"{tr.localize(f'{value:,.2f}')} {unit}"


def headline_cards(result, tr=ENGLISH):
    """The headline figures of a result: label, readable value, help text."""

    return [
        {
            "label": figure.label,
            "value": format_value(figure.value, figure.unit, tr),
            "help": figure.help,
        }
        for figure in result.key_figures
    ]


SOLVER_NAMES = {"highs": "HiGHS", "cbc": "CBC"}        # names of programs: the same in every language


def solver_label(name):
    """The name of a solver as it is written (HiGHS, CBC); an unknown one as it is."""

    return SOLVER_NAMES.get(name, name)


def solver_text(result, tr=ENGLISH):
    """For example: 'Solver HiGHS: optimal in 2.7 s' (without the name if the result does not have it)."""

    if result.solver is None:
        return tr("result.solver_none")

    named = result.solver.name is not None
    parts = {"termination": result.solver.termination}
    if named:
        parts["name"] = solver_label(result.solver.name)

    if result.solver.seconds is None:
        return tr("result.solver_named" if named else "result.solver", **parts)

    return tr(
        "result.solver_time_named" if named else "result.solver_time",
        seconds=tr.localize(f"{result.solver.seconds:.1f}"),
        **parts,
    )


def format_elapsed(seconds):
    """The time that a run has taken so far: 0:07, 1:12, 1:05:03."""

    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)

    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def run_failure(error):
    """Why a run gave no result, as a Msg: in plain words for the usual reasons, else the reason as it is.

    `error` is a ScenarioError. 'unbounded': the optimizer could earn money without end. 'infeasible': the
    demand cannot be met. 'unknown' and 'infeasibleOrUnbounded': HiGHS cannot tell the two apart.
    """

    termination = getattr(error, "termination", None)

    if termination == "unbounded":
        return Msg("run.unbounded")
    if termination == "infeasible":
        return Msg("run.infeasible")
    if termination in ("unknown", "infeasibleOrUnbounded"):
        return Msg("run.no_solution")

    return Msg("run.failed", reason=str(error))