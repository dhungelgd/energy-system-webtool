"""How the NiceGUI pages word a result (no NiceGUI needed)."""

import pytest

from backend.results import KeyFigure, ScenarioResult, SolverInfo, Table
from backend.i18n import Msg, Translator
from backend.service import ScenarioError
from frontend_nicegui.result_view import (
    chosen_sizes,
    format_elapsed,
    format_value,
    headline_cards,
    period_caption,
    run_failure,
    solver_label,
    solver_text,
)


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


# ---------------------------------------------------------------------------
# the time that a run has taken
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seconds, text", [
    (0, "0:00"), (0.9, "0:00"), (1, "0:01"), (7.4, "0:07"), (59.9, "0:59"), (60, "1:00"), (72, "1:12"),
    (331.1, "5:31"), (3599, "59:59"), (3600, "1:00:00"), (3725, "1:02:05"), (-5, "0:00"),
])
def test_the_time_of_a_run_is_written_as_minutes_and_seconds(seconds, text):
    assert format_elapsed(seconds) == text


# ---------------------------------------------------------------------------
# why a run gave no result
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("termination, code", [
    ("unbounded", "run.unbounded"),
    ("infeasible", "run.infeasible"),
    ("unknown", "run.no_solution"),                      # HiGHS cannot tell the two apart
    ("infeasibleOrUnbounded", "run.no_solution"),
])
def test_the_usual_reasons_of_a_failed_run_are_explained_in_plain_words(termination, code):
    assert run_failure(ScenarioError("technical text", termination=termination)) == Msg(code)


@pytest.mark.parametrize("error", [
    ScenarioError("[pv] fixed mode requires capacity > 0."),                       # no reason of a solver
    ScenarioError("time limit", termination="maxTimeLimit"),                       # a reason that has no words of its own
])
def test_any_other_reason_is_given_as_it_is(error):
    assert run_failure(error) == Msg("run.failed", reason=str(error))


def test_each_reason_has_a_sentence_in_both_languages_and_says_what_to_do():
    en, de = Translator("en"), Translator("de")

    for code in ("run.unbounded", "run.infeasible", "run.no_solution"):
        english, german = en.message(Msg(code)), de.message(Msg(code))
        assert "{" not in english and "{" not in german and english != german
    assert "upper limit" in en.message(Msg("run.unbounded")) and "feed-in revenue" in en.message(Msg("run.unbounded"))
    assert "Obergrenze" in de.message(Msg("run.unbounded")) and "Einspeisevergütung" in de.message(Msg("run.unbounded"))
    assert "demand cannot be met" in en.message(Msg("run.infeasible"))
    assert "Bedarf" in de.message(Msg("run.infeasible"))


def test_a_reason_that_is_unknown_to_the_page_does_not_break_it():
    assert run_failure(Exception("not a ScenarioError")) == Msg("run.failed", reason="not a ScenarioError")


# ---------------------------------------------------------------------------
# the words of the headline figures, and the note for a period shorter than a year
# ---------------------------------------------------------------------------

def figure_result(label, helptext, horizon=8760.0):
    return ScenarioResult(
        objective=1.0, horizon_hours=horizon,
        key_figures=[KeyFigure(label=label, value=1234.5, unit="€", help=helptext)],
        cost_breakdown=Table(columns=[]), capacities=Table(columns=[]),
    )


def test_the_label_and_the_help_of_a_headline_figure_are_translated():
    shown = figure_result("Grid import", "Electricity bought from the grid.")

    assert headline_cards(shown) == [{"label": "Grid import", "value": "1,234 €", "help": "Electricity bought from the grid."}]
    assert headline_cards(shown, DE) == [
        {"label": "Netzbezug", "value": "1.234 €", "help": "Strom, der aus dem Netz bezogen wird."}]


def test_a_label_that_is_not_in_the_table_is_shown_as_it_is():
    assert headline_cards(figure_result("Something new", "Some help."), DE)[0]["label"] == "Something new"


def test_the_label_of_the_system_cost_depends_on_the_length_of_the_period_in_both_languages():
    assert headline_cards(figure_result("Annual system cost", ""), DE)[0]["label"] == "Jährliche Systemkosten"
    assert headline_cards(figure_result("System cost (simulated period)", ""), DE)[0]["label"] == "Systemkosten (simulierter Zeitraum)"


@pytest.mark.parametrize("hours, english, german", [
    (24, "The simulated period is 1 day.", "Der simulierte Zeitraum beträgt 1 Tag."),
    (168, "The simulated period is 7 days.", "Der simulierte Zeitraum beträgt 7 Tage."),
    (8699, "The simulated period is 362 days.", "Der simulierte Zeitraum beträgt 362 Tage."),
    (6, "The simulated period is 1 day.", "Der simulierte Zeitraum beträgt 1 Tag."),            # never "0 days"
])
def test_a_period_shorter_than_a_year_gets_a_note_with_the_days(hours, english, german):
    shown = figure_result("Grid import", "", horizon=float(hours))

    assert period_caption(shown).startswith(english)
    assert period_caption(shown, DE).startswith(german)
    assert "so the system cost is not an annual figure." in period_caption(shown)
    assert "die Systemkosten sind also keine Jahreszahl." in period_caption(shown, DE)


@pytest.mark.parametrize("hours", [8700.0, 8760.0, 8784.0])
def test_a_whole_year_has_no_note(hours):
    assert period_caption(figure_result("Grid import", "", horizon=hours)) is None


# ---------------------------------------------------------------------------
# the optimised system: what the model chose to build
# ---------------------------------------------------------------------------

CAPACITY_COLUMNS = ["Component", "Mode", "Capacity", "Unit", "Annualised cost (€/a)"]


def sized(rows, columns=CAPACITY_COLUMNS):
    return ScenarioResult(
        objective=1.0, horizon_hours=8760.0,
        key_figures=[KeyFigure(label="Annual system cost", value=12556.4, unit="€", help="")],
        solver=SolverInfo(status="ok", termination="optimal", seconds=79.2, name="highs"),
        cost_breakdown=Table(columns=[]), capacities=Table(columns=list(columns), rows=rows),
    )


ROWS = [
    ["PV", "optimized", 38.0, "kW", 3531.0],
    ["Heat pump", "optimized", 18.04, "kW (heat)", 1394.4],
    ["Battery", "optimized", 0.0, "kWh", 0.0],
    ["Heat storage", "optimized", 8.0, "kWh", 25.0],
    ["Wind turbine", "optimized", 0.0, "kW", 0.0],
    ["Gas boiler", "fixed (input)", 9.0, "kW (heat)", 0.0],
]


def test_what_the_model_built_is_listed_with_size_and_cost_and_the_most_expensive_first():
    chosen = chosen_sizes(sized(ROWS))

    assert chosen["any"] is True
    assert [(c["name"], c["size"], c["cost"]) for c in chosen["built"]] == [
        ("PV", "38 kW", "3,531 € per year"),
        ("Heat pump", "18 kW (heat)", "1,394 € per year"),
        ("Heat storage", "8 kWh", "25 € per year"),
    ]


def test_the_most_expensive_comes_first_whatever_the_order_of_the_table():
    chosen = chosen_sizes(sized([
        ["Heat storage", "optimized", 8.0, "kWh", 25.0], ["PV", "optimized", 38.0, "kW", 3531.0],
        ["Heat pump", "optimized", 18.0, "kW (heat)", 1394.4],
    ]))

    assert [c["name"] for c in chosen["built"]] == ["PV", "Heat pump", "Heat storage"]


def test_what_the_model_left_out_is_listed_by_name_and_a_fixed_size_is_not_a_choice():
    chosen = chosen_sizes(sized(ROWS))

    assert chosen["not_built"] == ["Battery", "Wind turbine"]
    assert "Gas boiler" not in [c["name"] for c in chosen["built"]] + chosen["not_built"]


def test_a_size_with_decimals_keeps_one_and_a_whole_size_has_none():
    chosen = chosen_sizes(sized([["PV", "optimized", 38.46, "kW", 100.0], ["Wind turbine", "optimized", 12.0, "kW", 50.0]]))

    assert [c["size"] for c in chosen["built"]] == ["38.5 kW", "12 kW"]


def test_the_words_and_numbers_are_in_the_language_of_the_reader():
    chosen = chosen_sizes(sized(ROWS), DE)

    assert [(c["name"], c["size"], c["cost"]) for c in chosen["built"]] == [
        ("PV-Anlage", "38 kW", "3.531 € pro Jahr"),
        ("Wärmepumpe", "18 kW (Wärme)", "1.394 € pro Jahr"),
        ("Wärmespeicher", "8 kWh", "25 € pro Jahr"),
    ]
    assert chosen["not_built"] == ["Batteriespeicher", "Windkraftanlage"]


def test_a_size_of_a_thousand_or_more_has_the_separator_of_the_language():
    chosen = chosen_sizes(sized([["Heating rod", "optimized", 2471.04, "kW (heat)", 19080.3]]))

    assert chosen["built"][0]["size"] == "2,471 kW (heat)"
    assert chosen_sizes(sized([["Heating rod", "optimized", 2471.04, "kW (heat)", 19080.3]]), DE)["built"][0]["size"] == "2.471 kW (Wärme)"


def test_each_built_component_has_its_colour_of_the_charts_and_an_unknown_one_is_grey():
    from frontend_nicegui.palette import COLORS, GREY

    chosen = chosen_sizes(sized([["PV", "optimized", 1.0, "kW", 1.0], ["Something new", "optimized", 1.0, "kW", 0.5]]))

    assert chosen["built"][0]["color"] == COLORS["pv"] and chosen["built"][1]["color"] == GREY


def test_when_every_size_is_fixed_there_is_nothing_that_the_model_chose():
    chosen = chosen_sizes(sized([["PV", "fixed (input)", 5.0, "kW", 0.0]]))

    assert chosen == {"any": False, "built": [], "not_built": []}


def test_when_the_model_built_nothing_it_still_says_what_it_could_have_built():
    chosen = chosen_sizes(sized([["PV", "optimized", 0.0, "kW", 0.0], ["Battery", "optimized", 0.0, "kWh", 0.0]]))

    assert chosen["any"] is True and chosen["built"] == [] and chosen["not_built"] == ["PV", "Battery"]


@pytest.mark.parametrize("table", [
    Table(columns=[]), Table(columns=["Component", "Mode"]), Table(columns=["Something", "Else"]),
])
def test_a_table_of_capacities_that_is_not_the_usual_one_gives_nothing(table):
    result = sized([])
    result.capacities = table

    assert chosen_sizes(result) == {"any": False, "built": [], "not_built": []}


def test_an_empty_cost_counts_as_zero():
    chosen = chosen_sizes(sized([["PV", "optimized", 5.0, "kW", None]]))

    assert chosen["built"][0]["cost"] == "0 € per year"