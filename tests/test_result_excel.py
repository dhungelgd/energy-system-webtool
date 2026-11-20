"""The Excel file of a result: what is on its sheets, that the numbers are numbers, and that it works when something is missing."""

import io
import re
import time
import zipfile
from datetime import date, datetime, timedelta

import pytest
from openpyxl import load_workbook

from backend.i18n import Translator
from backend.results import BusSummary, FlowTable
from backend.results import Table as ResultTable
from backend.scenario_v2 import SeriesData
from frontend_nicegui import result_excel as excel
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.forms import FORMS
from frontend_nicegui.result_excel import build_workbook, excel_date_format, flatten, sheet_name, translated_table
from tests.report_samples import START, sample_result, sample_scenario
from tests.test_report_charts import FLOWS, TWO_MONTHS, summary

DE = Translator("de")
EN = Translator("en")
TODAY = date(2026, 11, 19)


def make(hours=24, language=EN, name="PV, battery and heat, test", **kwargs):
    return load_workbook(io.BytesIO(build_workbook(sample_scenario(hours, name), sample_result(hours, **kwargs), language, TODAY)))


def rows(sheet, first=1, last=None, width=None):
    return [list(row)[:width] if width else list(row) for row in sheet.iter_rows(min_row=first, max_row=last, values_only=True)]


def column(sheet, number):
    return [cell.value for cell in sheet[number]]


def two_months(language=EN):
    """A result of two months with flows that are the same all the time (so that the monthly energy can be counted)."""

    result = sample_result(24)
    result.buses = {"electricity": BusSummary(energy_sums={}, supply=result.buses["electricity"].supply, use=result.buses["electricity"].use,
                                              flows=summary(FLOWS, TWO_MONTHS).flows)}
    data = build_workbook(sample_scenario(TWO_MONTHS), result, language, TODAY)

    return data, load_workbook(io.BytesIO(data))


KEY = re.compile(r"^(excel|result|report|table|field|form|findings|status|run|scenario|header|row|common)\.[a-z_0-9.@]+$")


# ---------------------------------------------------------------------------
# the sheets
# ---------------------------------------------------------------------------

def test_the_sheets_are_the_summary_the_costs_the_capacities_each_carrier_the_scenario_and_the_time_series():
    assert make().sheetnames == ["Summary", "Costs", "Capacities", "Electricity", "Heat", "Gas", "Scenario", "Time series"]


def test_the_sheets_are_named_in_german_for_a_german_reader():
    assert make(language=DE).sheetnames == ["Übersicht", "Kosten", "Größen", "Strom", "Wärme", "Gas", "Szenario", "Zeitreihen"]


def test_a_result_without_carriers_and_a_scenario_without_series_has_only_the_sheets_that_it_needs():
    draft = ScenarioDraft(name="Small", steps=24)
    draft.set("battery")
    result = sample_result(24)
    result.buses = {}

    book = load_workbook(io.BytesIO(build_workbook(draft.scenario(), result, EN, TODAY)))

    assert book.sheetnames == ["Summary", "Costs", "Capacities", "Scenario"]


def test_the_file_has_the_name_of_the_scenario_as_its_title_and_the_project_as_its_author():
    book = make(name="My plant, 2026")

    assert book.properties.title == "My plant, 2026" and "DecarbCompany" in book.properties.creator


def test_every_sheet_is_printed_in_landscape_one_page_wide():
    for sheet in make().worksheets:
        assert sheet.page_setup.orientation == "landscape" and sheet.page_setup.fitToWidth == 1 and sheet.sheet_properties.pageSetUpPr.fitToPage


# ---------------------------------------------------------------------------
# the summary
# ---------------------------------------------------------------------------

def test_the_summary_has_the_name_the_date_the_period_and_the_solver():
    sheet = make(name="My plant, 2026")["Summary"]

    assert sheet["A1"].value == "My plant, 2026"
    assert sheet["A2"].value == "Optimisation of the energy system · Created 2026-11-19"
    assert (sheet["A4"].value, sheet["B4"].value) == ("Period", "24 hourly steps (1 day) from 01.01.2021 00:00")
    assert sheet["A5"].value == "Solver HiGHS: optimal in 1.5 s"


def test_the_summary_is_in_german():
    sheet = make(language=DE)["Übersicht"]

    assert sheet["A2"].value == "Optimierung des Energiesystems · Erstellt am 19.11.2026" and sheet["A4"].value == "Zeitraum"


def test_the_key_figures_are_numbers_with_their_unit_and_explanation():
    sheet = make()["Summary"]
    head = next(row for row in range(1, 20) if sheet.cell(row=row, column=1).value == "Figure")

    assert rows(sheet, head, head + 3, 3) == [["Figure", "Value", "Unit"], ["System cost (simulated period)", 55353, "€"],
                                              ["Grid import", 61200, "kWh"], ["Electricity consumption", 64000, "kWh"]]
    assert isinstance(sheet.cell(row=head + 1, column=2).value, (int, float))
    assert sheet.cell(row=head + 1, column=4).value.startswith("Objective of the optimization")


def test_the_optimised_system_has_what_was_built_and_what_was_left_out():
    sheet = make()["Summary"]
    texts = [cell.value for row in sheet.iter_rows(min_col=1, max_col=3) for cell in row if cell.value is not None]

    assert "The optimised system" in texts and "Heating rod" in texts and "2,471 kW (heat)" in texts and "19,080 € per year" in texts
    assert "PV" in texts and "41.7 kW" in texts and "Not built: Battery" in texts


def test_when_every_size_was_fixed_the_summary_says_so():
    result = sample_result(24)
    result.capacities = ResultTable(columns=result.capacities.columns, rows=[["PV", "fixed (input)", 5.0, "kW", 0.0]])

    sheet = load_workbook(io.BytesIO(build_workbook(sample_scenario(24), result, EN, TODAY)))["Summary"]

    assert any("All sizes were fixed" in str(cell.value) for row in sheet.iter_rows() for cell in row)


def test_a_period_shorter_than_a_year_has_the_note_and_a_year_has_none():
    short = [cell.value for row in make(24)["Summary"].iter_rows(min_col=1, max_col=1) for cell in row if cell.value]
    year = [cell.value for row in make(8760)["Summary"].iter_rows(min_col=1, max_col=1) for cell in row if cell.value]

    assert any(str(text).startswith("The simulated period is 1 day.") for text in short)
    assert not any(str(text).startswith("The simulated period") for text in year)


def test_the_note_that_a_result_is_an_aid_and_not_a_guarantee_is_the_last_line():
    sheet = make()["Summary"]
    last = [cell.value for row in sheet.iter_rows(min_col=1, max_col=1) for cell in row if cell.value][-1]

    assert "not a guarantee" in last


def test_long_notes_are_wrapped_over_the_columns_and_have_a_row_that_is_high_enough():
    sheet = make()["Summary"]
    merged = [r for r in sheet.merged_cells.ranges if "guarantee" in str(sheet.cell(row=r.min_row, column=1).value)][0]

    assert (merged.min_col, merged.max_col) == (1, 4)
    assert sheet.cell(row=merged.min_row, column=1).alignment.wrap_text and sheet.row_dimensions[merged.min_row].height >= 30


# ---------------------------------------------------------------------------
# costs and capacities
# ---------------------------------------------------------------------------

def test_the_costs_are_numbers_and_the_words_are_in_the_language_of_the_reader():
    english, german = make()["Costs"], make(language=DE)["Kosten"]

    assert rows(english) == [["Item", "Category", "Cost (€)"], ["Heating rod", "Investment and fixed O&M", 19080.3],
                             ["PV", "Investment and fixed O&M", 8400], ["Grid import", "Energy purchase", 36272.7],
                             ["Grid feed-in", "Revenue", -8400]]
    assert rows(german)[:2] == [["Posten", "Kategorie", "Kosten (€)"], ["Heizstab", "Investition und feste Betriebskosten", 19080.3]]
    assert all(isinstance(english.cell(row=r, column=3).value, (int, float)) for r in range(2, 6))


def test_a_cost_shows_whole_euros_and_the_cell_keeps_the_cents():
    cell = make()["Costs"]["C2"]

    assert cell.number_format == "#,##0" and cell.value == 19080.3


def test_the_capacities_are_numbers_with_one_decimal_and_the_words_in_german():
    sheet = make(language=DE)["Größen"]

    assert rows(sheet)[:3] == [["Bauteil", "Modus", "Größe", "Einheit", "Jahreskosten (€/a)"], ["PV-Anlage", "optimiert", 41.7, "kW", 8400],
                               ["Heizstab", "optimiert", 2471.04, "kW (Wärme)", 19080.3]]
    assert sheet["C2"].number_format == "#,##0.0"


def test_the_head_of_a_table_is_blue_with_white_bold_letters_and_stays_when_scrolling():
    sheet = make()["Costs"]

    assert sheet["A1"].fill.fgColor.rgb.endswith("005D9D") and sheet["A1"].font.bold and sheet["A1"].font.color.rgb.endswith("FFFFFF")
    assert sheet.freeze_panes == "A2"


def test_a_result_without_costs_or_capacities_says_so_on_the_sheet():
    book = make(costs=False, capacities=False)

    assert book["Costs"]["A1"].value == "No cost items in this run." and book["Costs"].max_row == 1
    assert book["Capacities"]["A1"].value == "No components with a capacity in this system."


# ---------------------------------------------------------------------------
# an energy carrier
# ---------------------------------------------------------------------------

def test_a_carrier_has_a_row_for_every_hour_with_the_time_and_a_column_for_every_flow_that_is_not_zero():
    sheet = make(48)["Electricity"]

    assert rows(sheet, 1, 1)[0] == ["Time", "Grid import [kW]", "PV [kW]", "Electricity demand [kW]", "Grid feed-in (use) [kW]",
                                    "Heating rod (use) [kW]"]
    assert sheet.max_row == 49 and sheet.max_column == 6


def test_the_time_is_a_date_and_time_that_follows_the_steps_and_has_the_format_of_the_reader():
    sheet = make(48)["Electricity"]

    assert [sheet.cell(row=r, column=1).value for r in (2, 3, 49)] == [START, START + timedelta(hours=1), START + timedelta(hours=47)]
    assert sheet["A2"].number_format == "yyyy-mm-dd hh:mm" and make(language=DE)["Strom"]["A2"].number_format == "dd.mm.yyyy hh:mm"


def test_the_values_are_the_hourly_flows_of_the_result():
    result = sample_result(24)
    sheet = load_workbook(io.BytesIO(build_workbook(sample_scenario(24), result, EN, TODAY)))["Electricity"]
    expected = result.buses["electricity"].flows.to_frame(with_end_row=False)

    assert column(sheet, "B")[1:] == pytest.approx([round(v, 6) for v in expected["grid_import-->electricity"]])
    assert column(sheet, "C")[1:] == pytest.approx([round(v, 6) for v in expected["pv-->electricity"]])
    assert all(isinstance(v, (int, float)) for v in column(sheet, "C")[1:])


def test_the_head_and_the_time_stay_in_view_on_the_sheets_with_hourly_values():
    book = make()

    assert book["Electricity"].freeze_panes == "B2" and book["Time series"].freeze_panes == "B2"


def test_an_hourly_value_shows_two_decimals():
    assert make()["Electricity"]["B2"].number_format == "0.00"


def test_the_names_are_in_german_for_a_german_reader():
    sheet = make(language=DE)["Strom"]

    assert rows(sheet, 1, 1)[0] == ["Zeit", "Netzbezug [kW]", "PV-Anlage [kW]", "Strombedarf [kW]", "Netzeinspeisung (Verwendung) [kW]",
                                    "Heizstab (Verwendung) [kW]"]


def test_a_carrier_through_which_nothing_flows_has_a_sheet_with_a_sentence_and_no_table():
    sheet = make()["Gas"]

    assert sheet["A1"].value == "Nothing flows through this energy carrier in this run." and sheet.max_row == 1 and sheet.max_column == 1


def test_a_result_without_hourly_flows_says_so_on_the_sheets_of_the_carriers():
    book = make(with_flows=False)

    assert book["Electricity"]["A1"].value == "This result has no hourly flows." and book["Heat"].max_row == 1


def test_a_time_step_of_half_an_hour_gives_rows_of_half_an_hour():
    flows = FlowTable(start=START, step_hours=0.5, columns=["pv-->electricity", "electricity-->demand"], values=[[1.0, 2.0, 3.0], [1.0, 1.0, 1.0]])
    result = sample_result(24)
    result.buses = {"electricity": BusSummary(energy_sums={}, supply=result.buses["electricity"].supply, use=result.buses["electricity"].use, flows=flows)}

    sheet = load_workbook(io.BytesIO(build_workbook(sample_scenario(24), result, EN, TODAY)))["Electricity"]

    assert [sheet.cell(row=r, column=1).value for r in (2, 3, 4)] == [START, START + timedelta(minutes=30), START + timedelta(minutes=60)]


# ---------------------------------------------------------------------------
# the scenario and the time series
# ---------------------------------------------------------------------------

def test_the_scenario_sheet_has_the_period_and_all_components():
    sheet = make()["Scenario"]
    texts = [row[0] for row in rows(sheet, 1, None, 1)]

    assert texts[0] == "PV, battery and heat, test" and texts[1] == "24 hourly steps (1 day) from 01.01.2021 00:00"
    assert ["Component", "Type", "Mode", "Size"] in rows(sheet, 1, None, 4)
    assert ["PV system", "PV system", "fixed", "not set"] in rows(sheet, 1, None, 4)


def test_the_settings_of_every_component_are_listed_with_the_names_and_units_of_the_forms():
    sheet = make()["Scenario"]
    settings = rows(sheet, 1, None, 4)

    assert ["Component", "Setting", "Value", "Unit"] in settings
    assert ["PV system", "How is the size decided?", "I enter a fixed size", None] in settings
    assert ["PV system", "Installed size", "not set", "kW"] in settings
    assert ["Battery storage", "Charging efficiency", 95, "%"] in settings
    assert ["Grid feed-in", "Feed-in tariff", 0.078, "€ per kWh"] in settings
    assert ["Battery storage", "Charge and discharge power", 0.5, "times the capacity per hour"] in settings


def test_the_settings_are_in_german_with_the_words_that_the_grid_has_for_its_price():
    settings = rows(make(language=DE)["Szenario"], 1, None, 4)

    assert ["PV-Anlage", "Wie wird die Größe festgelegt?", "Ich gebe eine feste Größe ein", None] in settings
    assert ["PV-Anlage", "Installierte Größe", "nicht festgelegt", "kW"] in settings
    assert ["Batteriespeicher", "Lade-Wirkungsgrad", 95, "%"] in settings


def test_a_setting_that_the_form_does_not_show_is_not_listed_and_one_that_a_series_replaces_is_left_out():
    settings = rows(make()["Scenario"], 1, None, 4)

    assert not any(row[1] == "Initial level" for row in settings)               # the engine ignores it, the form does not show it
    assert not any(row[0] == "Electricity grid" and row[1] == "Electricity price" for row in settings)   # a series replaces it


def test_no_setting_has_a_technical_name_with_dots_or_underscores():
    for language in (EN, DE):
        for row in rows(make(language=language)["Szenario" if language is DE else "Scenario"], 1, None, 4):
            if row[1] and row[0] not in (None, "Component", "Bauteil"):
                assert not re.search(r"[._]", str(row[1])) or " › " in str(row[1]), row


def test_a_component_without_a_form_has_its_settings_with_readable_names(monkeypatch):
    monkeypatch.delitem(FORMS, "pv")

    settings = excel.settings_rows(sample_scenario(24), EN)

    assert ["PV system", "Capacity › Mode", "fixed"] in [row[:3] for row in settings]
    assert not any("_" in str(row[1]) or "." in str(row[1]) for row in settings if row[0] == "PV system")


@pytest.mark.parametrize("path, expected", [("costs.variable_costs", "Costs › Variable costs"), ("mode", "Mode"), ("a.b.c_d", "A › B › C d")])
def test_a_name_without_a_text_is_made_readable(path, expected):
    assert excel.humanize(path) == expected


def test_the_time_series_are_listed_with_their_source_and_the_values_are_on_their_own_sheet():
    book = make()
    listed = rows(book["Scenario"], 1, None, 7)

    row = next(r for r in listed if r[:2] == ["Electricity demand", "kW"])
    assert row[2:4] == [24, 0] and row[4:6] == pytest.approx([0.1, 0.9]) and row[6] == "profiles.csv, DEMAND"
    assert all(isinstance(v, (int, float)) for v in row[2:6])
    sheet = book["Time series"]
    assert rows(sheet, 1, 1)[0][:3] == ["Time", "Electricity demand [kW]", "Heat demand [kW]"]
    assert sheet.max_row == 25 and sheet.max_column == 7 and sheet["B2"].value == pytest.approx(0.5)


def test_a_series_that_is_longer_than_the_period_is_written_to_its_end_and_a_gap_stays_empty():
    draft = ScenarioDraft(name="Longer", steps=24)
    draft.set("demand")
    draft.set_series("demand", SeriesData(unit="kW", values=[1.0, None, 3.0] + [2.0] * 47))

    sheet = load_workbook(io.BytesIO(build_workbook(draft.scenario(), sample_result(24), EN, TODAY)))["Time series"]

    assert sheet.max_row == 51 and sheet["B2"].value == 1.0 and sheet["B3"].value is None and sheet["B4"].value == 3.0
    assert sheet["A51"].value == START + timedelta(hours=49)


def test_the_statistics_of_a_series_are_numbers_and_an_empty_series_has_no_smallest_and_largest():
    assert excel._statistics([2.0, None, 0.5, 3.0]) == [4, 1, 0.5, 3.0]
    assert excel._statistics([None, None]) == [2, 2, None, None]
    assert excel._statistics([]) == [0, 0, None, None]


def test_flatten_gives_the_path_of_every_setting():
    assert flatten({"capacity": {"mode": "fixed", "capacity": 5.0}, "list": [1, 2], "flag": True, "none": None}) == [
        ("capacity.mode", "fixed"), ("capacity.capacity", 5.0), ("list", "1, 2"), ("flag", True), ("none", None)]


# ---------------------------------------------------------------------------
# the energy of each month (there are no charts in the file)
# ---------------------------------------------------------------------------

def test_a_period_within_one_month_has_no_sheet_of_monthly_values():
    assert "Monthly values" not in make(24).sheetnames


def test_two_months_have_a_table_of_the_energy_of_each_month_in_kwh():
    _, book = two_months()
    sheet = book["Monthly values"]

    assert rows(sheet, 1, 5) == [["Electricity", None, None, None, None], ["Month", "Grid import [kWh]", "PV [kWh]", "Demand [kWh]", "Heating rod [kWh]"],
                                 ["2021-01", 744, 1488, 2232, 372], ["2021-02", 672, 1344, 2016, 336], [None] * 5]
    assert sheet["B3"].number_format == "#,##0" and sheet.freeze_panes == "B1"


def test_each_carrier_has_its_own_table_with_two_empty_rows_between_them():
    sheet = make(TWO_MONTHS)["Monthly values"]

    assert [sheet.cell(row=r, column=1).value for r in (1, 2, 3, 4)] == ["Electricity", "Month", "2021-01", "2021-02"]
    assert [sheet.cell(row=r, column=1).value for r in (5, 6)] == [None, None]
    assert [sheet.cell(row=r, column=1).value for r in (7, 8, 9, 10)] == ["Heat", "Month", "2021-01", "2021-02"]
    assert rows(sheet, 8, 8)[0][:3] == ["Month", "Heating rod [kWh]", "Demand [kWh]"]


def test_the_months_are_written_as_the_reader_writes_them():
    _, book = two_months(DE)

    assert book["Monatswerte"]["A2"].value == "Monat" and book["Monatswerte"]["A3"].value == datetime(2021, 1, 1).strftime(DE("result.chart.month_format"))


def test_the_file_has_no_charts_and_no_drawings_a_partner_takes_them_from_the_report_or_the_page():
    for data in (build_workbook(sample_scenario(24), sample_result(24), EN, TODAY), two_months()[0], build_workbook(sample_scenario(8760), sample_result(8760), DE, TODAY)):
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert not [name for name in names if name.startswith(("xl/charts", "xl/drawings"))], names


def test_no_text_of_the_file_is_the_key_of_a_text_that_is_missing_from_the_catalogs():
    for language in (EN, DE):
        for hours in (24, TWO_MONTHS):
            book = make(hours, language)
            for sheet in book.worksheets:
                if sheet.max_row > 500:
                    continue
                for row in sheet.iter_rows(values_only=True):
                    for value in row:
                        assert not (isinstance(value, str) and KEY.match(value)), (sheet.title, value)


# ---------------------------------------------------------------------------
# the parts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Costs", "Costs"), ("a/b\\c:d*e?f[g]h", "a b c d e f g h"), ("x" * 50, "x" * 31), ("", "Sheet"), ("   ", "Sheet"),
])
def test_the_name_of_a_sheet_has_at_most_31_characters_and_none_of_the_signs_that_excel_does_not_allow(text, expected):
    assert sheet_name(text, set()) == expected


def test_two_sheets_never_have_the_same_name_not_even_in_another_case():
    used = set()

    names = [sheet_name("Gas", used), sheet_name("GAS", used), sheet_name("gas", used), sheet_name("x" * 40, used), sheet_name("x" * 40, used)]

    assert names == ["Gas", "GAS 2", "gas 3", "x" * 31, "x" * 29 + " 2"]


def test_the_format_of_the_date_follows_the_reader():
    assert excel_date_format(EN) == "yyyy-mm-dd hh:mm" and excel_date_format(DE) == "dd.mm.yyyy hh:mm"


def test_a_table_gives_numbers_as_numbers_words_translated_and_an_empty_cell_empty():
    table = ResultTable(columns=["Component", "Mode", "Capacity", "Share (%)", "Other"], rows=[["Heating rod", "optimized", 2.5, None, "text"]])

    columns, data, formats = translated_table(table, DE)

    assert columns == ["Bauteil", "Modus", "Größe", "Anteil (%)", "Other"] and data == [["Heizstab", "optimiert", 2.5, None, "text"]]
    assert formats == [None, None, "#,##0.0", "#,##0.0", "#,##0.00"]


# ---------------------------------------------------------------------------
# size, speed, and what is not touched
# ---------------------------------------------------------------------------

def test_a_year_is_made_in_a_few_seconds_and_the_file_is_not_heavy():
    started = time.time()
    data = build_workbook(sample_scenario(8760), sample_result(8760), EN, TODAY)

    assert time.time() - started < 20 and 200_000 < len(data) < 3_000_000
    book = load_workbook(io.BytesIO(data), read_only=True)
    assert sum(1 for _ in book["Electricity"].iter_rows()) == 8761


def test_a_very_long_name_is_a_title_and_does_not_break_the_file():
    book = make(name="A very long name of a scenario that goes on and on " * 3)

    assert book["Summary"]["A1"].value.startswith("A very long name") and len(book.sheetnames) == 8


def test_making_the_file_does_not_change_the_scenario_or_the_result():
    scenario, result = sample_scenario(24), sample_result(24)
    before = (scenario.model_dump(), result.model_dump())

    build_workbook(scenario, result, EN, TODAY)

    assert (scenario.model_dump(), result.model_dump()) == before


def test_a_file_made_without_a_date_is_of_today():
    book = load_workbook(io.BytesIO(build_workbook(sample_scenario(24), sample_result(24), EN)))

    assert str(date.today()) in book["Summary"]["A2"].value


def test_the_time_of_the_series_starts_where_the_scenario_starts():
    draft = ScenarioDraft(name="Later", start="2022-06-15", steps=24)
    draft.set("demand")
    draft.set_series("demand", SeriesData(unit="kW", values=[1.0] * 24))

    sheet = load_workbook(io.BytesIO(build_workbook(draft.scenario(), sample_result(24), EN, TODAY)))["Time series"]

    assert sheet["A2"].value == datetime(2022, 6, 15) and excel.FLOW_FORMAT == "0.00"