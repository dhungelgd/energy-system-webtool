"""How the NiceGUI pages word a result (no NiceGUI needed)."""

import pytest

from backend.results import KeyFigure, ScenarioResult, SolverInfo, Table
from backend.i18n import Translator
from frontend_nicegui.result_view import format_value, headline_cards, solver_label, solver_text


def result(solver=None, figures=()):
    return ScenarioResult(
        objective=1.0, horizon_hours=24, solver=solver, key_figures=list(figures),
        cost_breakdown=Table(columns=[]), capacities=Table(columns=[]),
    )


@pytest.mark.parametrize("value, unit, expected", [
    (72.0, "€", "72 €"),
    (19710000.4, "€", "19,710,000 €"),
    (80.2, "%", "80 %"),
    (75.14, "kW", "75.1 kW"),
    (240.0, "kWh", "240 kWh"),
    (9999.0, "kWh", "9,999 kWh"),
    (65700000.0, "kWh", "65,700.0 MWh"),
    (3.5, "", "3.50 "),
    (3.5, "h", "3.50 h"),
    (None, "€", "-"),
])
def test_values_are_worded_readably(value, unit, expected):
    assert format_value(value, unit) == expected


def test_the_wording_is_the_same_as_on_the_streamlit_page():
    pytest.importorskip("streamlit")
    from frontend.ui_results import format_value as streamlit_format

    for value in (0.0, 72.0, -1500.5, 9999.0, 10000.0, 12345678.9):
        for unit in ("€", "%", "kW", "kWh", "h", ""):
            assert format_value(value, unit) == streamlit_format(value, unit)


def test_headline_cards_hold_label_value_and_help():
    cards = headline_cards(result(figures=[
        KeyFigure(label="System cost", value=72.0, unit="€", help="The objective."),
        KeyFigure(label="Grid import", value=240.0, unit="kWh"),
        KeyFigure(label="Empty", value=None, unit="kW"),
    ]))

    assert cards == [
        {"label": "System cost", "value": "72 €", "help": "The objective."},
        {"label": "Grid import", "value": "240 kWh", "help": ""},
        {"label": "Empty", "value": "-", "help": ""},
    ]


def test_a_result_without_figures_gives_no_cards():
    assert headline_cards(result()) == []


def test_the_solver_line():
    done = SolverInfo(status="ok", termination="optimal", seconds=2.66)

    assert solver_text(result(solver=done)) == "Solver: optimal in 2.7 s"
    assert solver_text(result(solver=SolverInfo(status="ok", termination="optimal"))) == "Solver: optimal"
    assert solver_text(result()) == "Solver: no information"

# ---------------------------------------------------------------------------
# in German
# ---------------------------------------------------------------------------

DE = Translator("de")


@pytest.mark.parametrize("value, unit, expected", [
    (72.0, "€", "72 €"),
    (19710000.4, "€", "19.710.000 €"),
    (80.2, "%", "80 %"),
    (75.14, "kW", "75,1 kW"),
    (9999.0, "kWh", "9.999 kWh"),
    (65700000.0, "kWh", "65.700,0 MWh"),
    (3.5, "h", "3,50 h"),
    (None, "€", "-"),
])
def test_values_in_german_have_a_decimal_comma_and_dots_between_the_thousands(value, unit, expected):
    assert format_value(value, unit, DE) == expected


def test_the_headline_cards_take_the_numbers_of_the_language_and_keep_the_backend_labels():
    figure = KeyFigure(label="System cost", value=1234.5, unit="€", help="The objective.")

    cards = headline_cards(result(figures=[figure]), DE)

    assert cards == [{"label": "System cost", "value": "1.234 €", "help": "The objective."}]


def test_the_solver_line_in_german():
    solved = result(SolverInfo(status="ok", termination="optimal", seconds=1.5))

    assert solver_text(solved, DE) == "Solver: optimal in 1,5 s"
    assert solver_text(result(SolverInfo(status="ok", termination="optimal")), DE) == "Solver: optimal"
    assert solver_text(result(), DE) == "Solver: keine Angabe"


def test_the_solver_line_in_english_is_the_default():
    solved = result(SolverInfo(status="ok", termination="optimal", seconds=1.5))

    assert solver_text(solved) == "Solver: optimal in 1.5 s"
    assert solver_text(result()) == "Solver: no information"


# ---------------------------------------------------------------------------
# the name of the solver that ran
# ---------------------------------------------------------------------------

def test_the_name_of_the_solver_is_written_when_the_result_knows_it():
    highs = result(SolverInfo(status="ok", termination="optimal", seconds=45.26, name="highs"))
    cbc = result(SolverInfo(status="ok", termination="optimal", name="cbc"))

    assert solver_text(highs) == "Solver HiGHS: optimal in 45.3 s"
    assert solver_text(cbc) == "Solver CBC: optimal"


def test_the_name_of_the_solver_is_the_same_in_german_and_the_time_follows_the_language():
    highs = result(SolverInfo(status="ok", termination="optimal", seconds=45.26, name="highs"))

    assert solver_text(highs, DE) == "Solver HiGHS: optimal in 45,3 s"
    assert solver_text(result(SolverInfo(status="ok", termination="optimal", name="cbc")), DE) == "Solver CBC: optimal"


def test_a_solver_that_is_not_known_is_written_as_it_is():
    assert solver_label("highs") == "HiGHS" and solver_label("cbc") == "CBC"
    assert solver_label("gurobi") == "gurobi"
    assert solver_text(result(SolverInfo(status="ok", termination="optimal", name="gurobi"))) == "Solver gurobi: optimal"


def test_a_result_without_the_name_reads_as_before():
    assert solver_text(result(SolverInfo(status="ok", termination="optimal", seconds=2.66))) == "Solver: optimal in 2.7 s"