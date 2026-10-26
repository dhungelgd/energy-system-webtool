"""What the NiceGUI pages show about a result.

No NiceGUI code in here, only the decisions about what to show and how to word
it, so that it is easy to test.
"""


def format_value(value, unit):
    """Readable text for one key figure (the same wording as the Streamlit page)."""

    if value is None:
        return "-"

    if unit == "%":
        return f"{value:.0f} %"
    if unit == "€":
        return f"{value:,.0f} €"
    if unit == "kW":
        return f"{value:,.1f} kW"
    if unit == "kWh":
        if abs(value) >= 10000:
            return f"{value / 1000:,.1f} MWh"
        return f"{value:,.0f} kWh"

    return f"{value:,.2f} {unit}"


def headline_cards(result):
    """The headline figures of a result: label, readable value, help text."""

    return [
        {
            "label": figure.label,
            "value": format_value(figure.value, figure.unit),
            "help": figure.help,
        }
        for figure in result.key_figures
    ]


def solver_text(result):
    """For example: 'Solver: optimal in 2.7 s'."""

    if result.solver is None:
        return "Solver: no information"

    text = f"Solver: {result.solver.termination}"
    if result.solver.seconds is not None:
        text += f" in {result.solver.seconds:.1f} s"

    return text