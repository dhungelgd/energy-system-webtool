"""What the NiceGUI pages show about a result.

No NiceGUI code in here, only the decisions about what to show and how to word
it, so that it is easy to test. What is shown in words takes a translator `tr`
(English if none is given). The labels of the key figures come from the backend and
are English for now.
"""

from backend.i18n import ENGLISH


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


def solver_text(result, tr=ENGLISH):
    """For example: 'Solver: optimal in 2.7 s'."""

    if result.solver is None:
        return tr("result.solver_none")

    if result.solver.seconds is None:
        return tr("result.solver", termination=result.solver.termination)

    return tr(
        "result.solver_time",
        termination=result.solver.termination,
        seconds=tr.localize(f"{result.solver.seconds:.1f}"),
    )