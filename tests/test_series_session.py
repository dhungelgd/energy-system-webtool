"""What happens between a file that was chosen and a time series that is used (no page needed)."""

import io
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook

from backend.i18n import Translator
from backend.templates import new_component
from backend.timeseries_import import import_text
from frontend_nicegui.series_session import (
    PREVIEW_ROWS,
    START_FILE,
    START_SCENARIO,
    UploadSession,
)

DE = Translator("de")
EN = Translator("en")
START = date(2021, 1, 1)


def csv(values, minutes=60, start="2021-01-01 00:00", head="Zeit;Wert", decimal="."):
    rows = [head]
    first = datetime.fromisoformat(start)
    for i, value in enumerate(values):
        moment = first + timedelta(minutes=minutes) * i
        text = "" if value is None else str(value).replace(".", decimal)
        rows.append(f"{moment:%Y-%m-%d %H:%M};{text}")
    return ("\n".join(rows) + "\n").encode()


def excel(sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def session_of(values, name="x.csv", **options):
    return UploadSession(csv(values, **options), name)


# ---------------------------------------------------------------------------
# reading the file
# ---------------------------------------------------------------------------

def test_a_file_that_can_be_read_has_its_table_and_the_first_column_with_numbers_is_chosen():
    session = UploadSession(b"Zeit;Name;Last;PV\n2021-01-01 00:00;a;1;0.5\n2021-01-01 01:00;b;2;0.7\n", "x.csv")

    assert session.readable and session.error is None
    assert session.columns() == ["Last", "PV"] and session.column == "Last"
    assert session.has_dates() and session.is_hourly() and session.sheets() == []


def test_a_file_that_cannot_be_read_says_why_and_gives_nothing():
    session = UploadSession(b"   ", "x.csv")

    assert not session.readable and session.error.code == "empty"
    assert session.columns() == [] and session.column is None and session.notices(new_component("pv")) == []
    with pytest.raises(type(session.error)):
        session.build(new_component("pv"), START)
    assert session.problem(new_component("pv"), START).code == "empty"


def test_a_file_without_a_column_with_numbers_has_nothing_to_use():
    session = UploadSession(b"Name;Ort\na;b\nc;d\n", "x.csv")

    assert session.readable and session.columns() == [] and session.column is None
    assert session.problem(new_component("pv"), START).code == "no_numeric_column"
    assert import_text(session.problem(new_component("pv"), START), DE) == "Die Datei hat keine Spalte mit Zahlen."


def test_the_sheets_of_an_excel_file():
    session = UploadSession(excel({"Notes": [["hello"]], "Data": [["t", "v"], [1, 2], [2, 3], [3, 4]]}), "x.xlsx")

    assert session.sheets() == ["Notes", "Data"] and session.table.used.sheet == "Data"


# ---------------------------------------------------------------------------
# changing the settings of the import
# ---------------------------------------------------------------------------

def test_a_setting_of_the_import_reads_the_file_again():
    session = UploadSession(b"a;b\n1;1,234\n2;2,345\n3;3,456\n", "x.csv")
    assert session.table.used.decimal == "," and session.table.df["b"].tolist() == [1.234, 2.345, 3.456]

    session.change(decimal=".")                                              # 1,234 is a thousand and a bit

    assert session.options.decimal == "." and session.table.df["b"].tolist() == [1234.0, 2345.0, 3456.0]


def test_the_chosen_column_stays_if_it_is_still_there_and_goes_back_to_the_first_if_not():
    session = UploadSession(b"Zeit;Last;PV\n2021-01-01 00:00;1;0.5\n2021-01-01 01:00;2;0.7\n", "x.csv")
    session.column = "PV"

    session.change(decimal=".")
    assert session.column == "PV"

    session.column = "gone"
    session.change(decimal=",")
    assert session.column == "Last"


def test_a_change_of_the_layout_forgets_the_line_numbers_and_a_change_of_the_lines_keeps_the_layout():
    content = b"title\n\nZeit;Wert\n2021-01-01 00:00;1\n2021-01-01 01:00;2\n2021-01-01 02:00;3\n"
    session = UploadSession(content, "x.csv")
    session.change(header_line=3, first_data_line=4)
    session.change(delimiter=";")

    assert (session.options.header_line, session.options.first_data_line) == (None, None)
    assert session.options.delimiter == ";"

    session.change(first_data_line=5)

    assert session.options.delimiter == ";" and session.table.used.first_data_line == 5
    assert len(session.table.df) == 2                                         # the first row of data is skipped


def test_a_setting_that_makes_the_file_unreadable_gives_an_error_and_a_better_one_brings_the_file_back():
    session = UploadSession("Zeit;Wert\n2021-01-01 00:00;1\n2021-01-01 01:00;ä\n".encode("cp1252"), "x.csv")
    assert session.readable

    session.change(encoding="utf-8")
    assert not session.readable and session.error.code == "encoding"

    session.change(encoding="cp1252")
    assert session.readable and session.error is None


# ---------------------------------------------------------------------------
# the preview
# ---------------------------------------------------------------------------

def test_the_preview_shows_the_first_rows_in_the_way_of_the_language():
    session = session_of([1.5, 2.25, None, 4], head="Zeit;Last")

    columns, rows = session.preview(DE)

    assert [c["label"] for c in columns] == ["Zeit", "Last"]
    assert rows[0] == {"0": "01.01.2021 00:00", "1": "1,5"}
    assert rows[1]["1"] == "2,25" and rows[2]["1"] == ""                       # an empty value is an empty cell
    assert session.preview(EN)[1][1]["1"] == "2.25"


def test_the_preview_has_only_the_first_rows():
    session = session_of(range(100))

    assert len(session.preview(EN)[1]) == PREVIEW_ROWS == 8
    assert len(session.preview(EN, rows=3)[1]) == 3


def test_the_columns_of_the_preview_are_found_by_position_so_that_any_name_works():
    session = UploadSession(b"a.b;c d;a.b\n1;2;3\n4;5;6\n", "x.csv")

    columns, rows = session.preview(EN)

    assert [c["field"] for c in columns] == ["0", "1", "2"] and set(rows[0]) == {"0", "1", "2"}


# ---------------------------------------------------------------------------
# which part of the file is used
# ---------------------------------------------------------------------------

def test_the_start_of_the_scenario_is_the_default_when_the_file_includes_it():
    session = session_of(range(48), start="2021-03-01 00:00")

    assert session.start_choice_for(date(2021, 3, 2)) == START_SCENARIO
    assert session.build(new_component("demand"), date(2021, 3, 2)).values[0] == 24.0


def test_a_file_that_does_not_include_the_start_is_used_from_its_first_row():
    session = session_of(range(48), start="2021-03-01 00:00")

    assert session.start_choice_for(date(2022, 1, 1)) == START_FILE
    assert session.build(new_component("demand"), date(2022, 1, 1)).values[0] == 0.0


def test_the_visitor_can_choose_the_first_row_of_the_file():
    session = session_of(range(48), start="2021-03-01 00:00")
    session.start_choice = START_FILE

    assert session.build(new_component("demand"), date(2021, 3, 2)).values[0] == 0.0


def test_the_start_of_the_scenario_that_the_visitor_chose_is_an_error_when_the_scenario_moves_away_from_the_file():
    session = session_of(range(48), start="2021-03-01 00:00")
    session.start_choice = START_SCENARIO

    problem = session.problem(new_component("demand"), date(2022, 1, 1))

    assert problem.code == "start_outside"


def test_a_file_without_dates_has_no_start_to_choose():
    session = UploadSession(b"Wert\n1\n2\n3\n", "x.csv")

    assert not session.has_dates() and session.build(new_component("pv"), START).values == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# the unit of a price and the conversion to hourly values
# ---------------------------------------------------------------------------

def test_the_unit_of_a_price_counts_for_the_grid_only():
    session = session_of([25, 30])
    session.price_unit = "ct/kWh"

    assert session.build(new_component("grid"), START).values == pytest.approx([0.25, 0.30])
    assert session.build(new_component("pv"), START).values == [25.0, 30.0]


def test_a_file_that_is_not_hourly_is_converted_for_a_profile_without_asking():
    session = session_of([1, 2, 3, 4, 5, 6, 7, 8], minutes=15)

    assert not session.is_hourly() and not session.needs_aggregate(new_component("pv"))
    assert session.build(new_component("pv"), START).values == [2.5, 6.5]


def test_shares_of_the_annual_demand_are_added_up_without_asking():
    session = session_of([1, 2, 3, 4, 5, 6, 7, 8], minutes=15)
    demand = new_component("demand")

    assert not session.needs_aggregate(demand)
    assert session.build(demand, START).values == [10.0, 26.0]


def test_a_demand_in_kw_asks_and_cannot_be_built_before_the_answer():
    session = session_of([1, 2, 3, 4, 5, 6, 7, 8], minutes=15)
    demand = new_component("demand")
    demand.blocks["demand"]["profile_type"] = "absolute"

    assert session.needs_aggregate(demand)
    assert session.problem(demand, START).code == "convert_needed"

    session.aggregate = "mean"
    assert session.build(demand, START).values == [2.5, 6.5]
    session.aggregate = "sum"
    assert session.build(demand, START).values == [10.0, 26.0]


def test_an_hourly_file_asks_nothing():
    session = session_of([1, 2, 3])
    demand = new_component("demand")
    demand.blocks["demand"]["profile_type"] = "absolute"

    assert not session.needs_aggregate(demand) and session.problem(demand, START) is None


# ---------------------------------------------------------------------------
# what the visitor is told
# ---------------------------------------------------------------------------

def test_the_notices_are_what_the_import_found_and_how_the_file_was_converted():
    session = session_of([1, 2, 3, 4, 5, 6, 7, 8], minutes=15)

    codes = [notice.code for notice in session.notices(new_component("pv"))]

    assert codes[0] == "time_info" and "time_step_not_hourly" in codes and codes[-1] == "converted"


def test_the_notices_of_a_demand_in_kw_wait_for_the_answer_about_the_conversion():
    session = session_of([1, 2, 3, 4, 5, 6, 7, 8], minutes=15)
    demand = new_component("demand")
    demand.blocks["demand"]["profile_type"] = "absolute"

    assert "converted" not in [notice.code for notice in session.notices(demand)]
    session.aggregate = "sum"
    assert "converted" in [notice.code for notice in session.notices(demand)]


def test_a_file_that_cannot_be_read_has_no_notices():
    assert UploadSession(b"", "x.csv").notices(new_component("pv")) == []


def test_the_box_of_the_import_settings_starts_closed():
    assert UploadSession(csv([1, 2]), "x.csv").settings_open is False