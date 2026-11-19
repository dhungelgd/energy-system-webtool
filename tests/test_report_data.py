"""What the PDF report says: the sections, cards, tables and charts that are made from a scenario and its result."""

from datetime import date

import pytest

from backend.i18n import Translator
from backend.results import Table as ResultTable
from backend.scenario_v2 import SeriesData
from frontend_nicegui import report_data as data
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.report_data import ChartRef, Paragraph, build_report, date_text, display_table
from frontend_nicegui.result_view import headline_cards
from tests.report_samples import sample_result, sample_scenario

DE = Translator("de")
EN = Translator("en")
TODAY = date(2026, 11, 19)


def report(hours=24, language=EN, **kwargs):
    return build_report(sample_scenario(hours), sample_result(hours, **kwargs), language, TODAY)


def section(report_, heading):
    return next(s for s in report_.sections if s.heading == heading)


def blocks_of(report_, heading, kind):
    return [b for b in section(report_, heading).blocks if isinstance(b, kind)]


# ---------------------------------------------------------------------------
# the first page
# ---------------------------------------------------------------------------

def test_the_report_is_about_the_scenario_with_its_name_and_the_date():
    made = build_report(sample_scenario(24, "My plant, 2026"), sample_result(24), EN, TODAY)

    assert made.title == "My plant, 2026" and made.tag == "RESULT REPORT · 2026-11-19"
    assert made.subtitle == "Optimisation of the energy system" and made.language == "en"


def test_the_date_and_the_words_are_in_german_for_a_german_reader():
    made = report(language=DE)

    assert made.tag == "ERGEBNISBERICHT · 19.11.2026" and made.subtitle == "Optimierung des Energiesystems"
    assert made.footer.endswith("Ergebnisbericht") and made.page_word == "Seite" and made.language == "de"


def test_the_band_has_the_period_the_system_cost_and_the_solver():
    made = report(24)

    assert made.facts == [
        ("Period", "24 hourly steps (1 day) from 01.01.2021 00:00"),
        ("System cost (simulated period)", "55,353 €"),
        ("Solver", "HiGHS"),
    ]


def test_the_date_is_written_as_the_reader_writes_it():
    assert date_text(date(2026, 3, 5), EN) == "2026-03-05" and date_text(date(2026, 3, 5), DE) == "05.03.2026"


def test_a_report_without_a_date_is_of_today():
    made = build_report(sample_scenario(24), sample_result(24), EN)

    assert str(date.today()) in made.tag


# ---------------------------------------------------------------------------
# the sections
# ---------------------------------------------------------------------------

def test_the_sections_are_in_the_order_that_a_reader_needs_them():
    made = report()

    assert [s.heading for s in made.sections] == [
        "The optimised system", "Key figures", "Your scenario at a glance", "Where the system cost comes from",
        "Capacities", "Electricity", "Heat", "Gas", "Notes"]


def test_the_headings_are_in_german():
    made = report(language=DE)

    assert [s.heading for s in made.sections] == [
        "Das optimierte System", "Kennzahlen", "Ihr Szenario auf einen Blick", "Woher die Systemkosten kommen",
        "Größen", "Strom", "Wärme", "Gas", "Hinweise"]


def test_the_optimised_system_has_a_card_for_each_component_that_was_built_and_says_what_was_left_out():
    made = report()
    cards = blocks_of(made, "The optimised system", data.Cards)[0].cards

    assert [(c.title, c.value, c.note) for c in cards] == [
        ("Heating rod", "2,471 kW (heat)", "19,080 € per year"), ("PV", "41.7 kW", "8,400 € per year")]
    assert all(c.color.startswith("#") for c in cards)
    assert [p.text for p in blocks_of(made, "The optimised system", Paragraph)][-1] == "Not built: Battery"


def test_when_every_size_was_fixed_the_report_says_that_the_model_chose_none():
    result = sample_result(24)
    result.capacities = ResultTable(columns=result.capacities.columns, rows=[["PV", "fixed (input)", 5.0, "kW", 0.0]])

    made = build_report(sample_scenario(24), result, EN, TODAY)

    assert not blocks_of(made, "The optimised system", data.Cards)
    assert any("All sizes were fixed" in p.text for p in blocks_of(made, "The optimised system", Paragraph))


def test_the_key_figures_are_the_cards_of_the_page_with_their_explanation():
    made = report()
    cards = blocks_of(made, "Key figures", data.Cards)[0].cards

    assert [(c.title, c.value) for c in cards] == [("System cost (simulated period)", "55,353 €"), ("Grid import", "61.2 MWh"),
                                                   ("Electricity consumption", "64.0 MWh")]
    assert [c.note for c in cards] == [item["help"] for item in headline_cards(sample_result(24), EN)]


# ---------------------------------------------------------------------------
# the scenario
# ---------------------------------------------------------------------------

def test_the_scenario_says_its_period_and_lists_all_components_with_their_mode_and_size():
    made = report(24)
    glance = "Your scenario at a glance"

    assert blocks_of(made, glance, Paragraph)[0].text == "24 hourly steps (1 day) from 01.01.2021 00:00"
    table = next(b for b in blocks_of(made, glance, data.Table) if b.title == "Components")
    assert table.data.columns == ["Component", "Type", "Mode", "Size"]
    assert len(table.data.rows) == 13 and ["PV system", "PV system", "fixed", "not set"] in table.data.rows


def test_a_period_shorter_than_a_year_has_the_note_and_a_year_has_none():
    short = blocks_of(report(24), "Your scenario at a glance", Paragraph)
    year = blocks_of(report(8760), "Your scenario at a glance", Paragraph)

    assert [p.style for p in short] == ["body", "note"] and short[1].text.startswith("The simulated period is 1 day.")
    assert [p.style for p in year] == ["body"]


def test_the_time_series_are_listed_with_the_file_and_the_column_they_came_from():
    table = next(b for b in blocks_of(report(), "Your scenario at a glance", data.Table) if b.title == "Time series")

    assert table.data.columns == ["Used by", "Unit", "Values", "Empty", "Smallest", "Largest", "Source"]
    assert len(table.data.rows) == 6
    assert ["Electricity demand", "kW", "24", "0", "0.1", "0.9", "profiles.csv, DEMAND"] in table.data.rows


def test_a_series_that_has_no_source_has_an_empty_source():
    draft = ScenarioDraft(name="No source", steps=24)
    draft.set("demand")
    draft.set_series("demand", SeriesData(unit="kW", values=[1.0] * 24))

    made = build_report(draft.scenario(), sample_result(24), EN, TODAY)
    table = next(b for b in blocks_of(made, "Your scenario at a glance", data.Table) if b.title == "Time series")

    assert table.data.rows[0][-1] == ""


def test_a_scenario_without_time_series_has_no_table_of_them():
    draft = ScenarioDraft(name="Nothing", steps=24)
    draft.set("battery")

    made = build_report(draft.scenario(), sample_result(24), EN, TODAY)

    assert [b.title for b in blocks_of(made, "Your scenario at a glance", data.Table)] == ["Components"]


# ---------------------------------------------------------------------------
# costs and capacities
# ---------------------------------------------------------------------------

def test_the_costs_have_a_chart_without_a_title_of_its_own_and_a_table():
    blocks = section(report(), "Where the system cost comes from").blocks

    assert blocks[0] == ChartRef("costs", "") and isinstance(blocks[1], data.Table)
    assert blocks[1].data.columns == ["Item", "Category", "Cost (€)"]
    assert blocks[1].data.rows[0] == ["Heating rod", "Investment and fixed O&M", "19,080"] and blocks[1].data.rows[-1][2] == "-8,400"


def test_a_result_without_costs_says_so():
    made = report(costs=False)

    assert [p.text for p in blocks_of(made, "Where the system cost comes from", Paragraph)] == ["No cost items in this run."]
    assert not blocks_of(made, "Where the system cost comes from", ChartRef)


def test_the_capacities_have_a_table_and_the_note_for_fixed_sizes_only_if_one_is_fixed():
    free = section(report(), "Capacities").blocks
    fixed = section(report(built=False), "Capacities").blocks

    assert len(free) == 1 and free[0].data.columns[:3] == ["Component", "Mode", "Capacity"]
    assert len(fixed) == 2 and fixed[1].text.startswith("Components in fixed mode have no capital cost")


def test_a_result_without_capacities_says_so():
    made = report(capacities=False)

    assert [p.text for p in section(made, "Capacities").blocks] == ["No components with a capacity in this system."]


# ---------------------------------------------------------------------------
# the energy carriers
# ---------------------------------------------------------------------------

def test_a_carrier_has_three_charts_and_the_two_tables_of_who_supplies_and_who_uses_it():
    blocks = section(report(), "Electricity").blocks

    assert [(b.kind, b.title, b.bus) for b in blocks if isinstance(b, ChartRef)] == [
        ("flows", "Energy flows", "electricity"), ("monthly", "Energy per month", "electricity"),
        ("duration", "Duration curve", "electricity")]
    assert [b.title for b in blocks if isinstance(b, data.Table)] == ["Supply", "Use"]
    assert blocks[1].note.startswith("What supplies the carrier") and blocks[2].note.startswith("Every value of the period")


def test_the_tables_of_a_carrier_have_the_numbers_as_on_the_page_in_both_languages():
    english = [b for b in section(report(), "Electricity").blocks if isinstance(b, data.Table)]
    german = [b for b in section(report(language=DE), "Strom").blocks if isinstance(b, data.Table)]

    assert english[0].data.rows == [["Grid import", "61,200", "62.0"], ["PV", "37,500", "38.0"]]
    assert german[0].data.columns == ["Bauteil", "Energie (kWh)", "Anteil (%)"]
    assert german[0].data.rows == [["Netzbezug", "61.200", "62,0"], ["PV-Anlage", "37.500", "38,0"]]


def test_a_carrier_through_which_nothing_flows_says_so_and_has_no_charts():
    blocks = section(report(), "Gas").blocks

    assert [b.text for b in blocks if isinstance(b, Paragraph)] == ["Nothing flows through this energy carrier in this run."]
    assert not [b for b in blocks if isinstance(b, ChartRef)] and len([b for b in blocks if isinstance(b, data.Table)]) == 2


def test_a_result_without_hourly_flows_says_so_and_still_has_the_tables():
    made = report(with_flows=False)
    blocks = section(made, "Electricity").blocks

    assert [b.text for b in blocks if isinstance(b, Paragraph)] == ["This result has no hourly flows."]
    assert not [b for b in blocks if isinstance(b, ChartRef)] and [b.title for b in blocks if isinstance(b, data.Table)] == ["Supply", "Use"]


def test_a_carrier_that_starts_on_a_new_page_unless_there_is_room_is_marked():
    made = report()

    assert [s.big for s in made.sections] == [False] * 5 + [True] * 3 + [False]


def test_a_result_without_carriers_has_none_of_those_sections():
    result = sample_result(24)
    result.buses = {}

    made = build_report(sample_scenario(24), result, EN, TODAY)

    assert [s.heading for s in made.sections][-2:] == ["Capacities", "Notes"]


# ---------------------------------------------------------------------------
# the notes
# ---------------------------------------------------------------------------

def test_the_notes_say_what_the_solver_did_and_that_a_result_is_an_aid_and_depends_on_the_data():
    blocks = section(report(), "Notes").blocks

    assert blocks[0].text == "Solver HiGHS: optimal in 1.5 s" and blocks[0].style == "small"
    assert [b.style for b in blocks[1:]] == ["note", "note"]
    assert "not a guarantee" in blocks[1].text and "depends on how good the data are" in blocks[2].text


def test_the_notes_are_in_german():
    blocks = section(report(language=DE), "Hinweise").blocks

    assert "keine Garantie" in blocks[1].text and "Zeitreihen und die Preise" in blocks[2].text


# ---------------------------------------------------------------------------
# a table as the page shows it
# ---------------------------------------------------------------------------

def test_a_result_table_is_given_as_titles_and_rows_of_text():
    table = display_table(sample_result(24).cost_breakdown, EN)

    assert table.columns == ["Item", "Category", "Cost (€)"] and table.rows[2] == ["Grid import", "Energy purchase", "36,273"]


@pytest.mark.parametrize("language", [EN, DE])
def test_a_table_row_has_as_many_cells_as_the_table_has_columns(language):
    made = report(8760, language)

    for s in made.sections:
        for block in s.blocks:
            if isinstance(block, data.Table):
                assert all(len(row) == len(block.data.columns) for row in block.data.rows), (s.heading, block.title)