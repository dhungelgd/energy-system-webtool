"""Tests for reading CSV and Excel time series files (no solver needed)."""

import datetime
import io
import time

import pandas as pd
import pytest
from openpyxl import Workbook

from backend.timeseries_import import (
    ImportOptions,
    TimeSeriesFileError,
    read_table,
    series_from_column,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def csv_file(text, encoding="utf-8", newline="\n"):
    return text.replace("\n", newline).encode(encoding)


def excel_file(sheets):
    """sheets: {sheet name: list of rows}"""

    workbook = Workbook()
    workbook.remove(workbook.active)

    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def messages(table, level):
    return [text for kind, text in table.messages if kind == level]


GERMAN = (
    "Zeitstempel;Last (kW);PV (kW)\n"
    "01.01.2021 00:00;12,5;0,0\n"
    "01.01.2021 01:00;13,25;0,0\n"
    "01.01.2021 02:00;14,0;0,125\n"
)


# ---------------------------------------------------------------------------
# CSV: the usual German and English layouts
# ---------------------------------------------------------------------------

def test_german_csv_semicolon_and_decimal_comma():
    table = read_table(csv_file(GERMAN), "last.csv")

    assert table.used.delimiter == ";"
    assert table.used.decimal == ","
    assert list(table.df.columns) == ["Zeitstempel", "Last (kW)", "PV (kW)"]
    assert table.df["Last (kW)"].tolist() == [12.5, 13.25, 14.0]
    assert table.df["PV (kW)"].tolist() == [0.0, 0.0, 0.125]


def test_german_dates_are_read_day_first():
    text = "Zeit;Last\n02.01.2021 00:00;1,5\n03.01.2021 00:00;2,5\n"
    table = read_table(csv_file(text), "x.csv")

    assert table.df["Zeit"].iloc[0] == pd.Timestamp("2021-01-02 00:00")


def test_english_csv_with_decimal_point():
    text = "time,load\n2021-01-01 00:00,12.5\n2021-01-01 01:00,13.25\n"
    table = read_table(csv_file(text), "x.csv")

    assert table.used.delimiter == ","
    assert table.used.decimal == "."
    assert table.df["load"].tolist() == [12.5, 13.25]


def test_quoted_thousands_separator_in_english_file():
    text = 'time,load\n2021-01-01 00:00,"1,234.5"\n2021-01-01 01:00,"2,000.25"\n'
    table = read_table(csv_file(text), "x.csv")

    assert table.df["load"].tolist() == [1234.5, 2000.25]


def test_german_thousands_dot_and_decimal_comma():
    text = "Zeit;Verbrauch\n01.01.2021 00:00;1.234,5\n01.01.2021 01:00;12.345,75\n"
    table = read_table(csv_file(text), "x.csv")

    assert table.df["Verbrauch"].tolist() == [1234.5, 12345.75]


def test_tab_separated_file():
    text = "Zeit\tLast\n01.01.2021 00:00\t0,125\n01.01.2021 01:00\t0,25\n"
    table = read_table(csv_file(text), "x.tsv")

    assert table.used.delimiter == "\t"
    # 0,125 must never become 125
    assert table.df["Last"].tolist() == [0.125, 0.25]


def test_pipe_separated_file():
    text = "a|b\n1|2\n3|4\n"
    table = read_table(csv_file(text), "x.csv")

    assert table.used.delimiter == "|"
    assert table.df["b"].tolist() == [2.0, 4.0]


def test_windows_line_endings():
    table = read_table(csv_file(GERMAN, newline="\r\n"), "x.csv")

    assert len(table.df) == 3


def test_integers_without_any_decimal_sign():
    table = read_table(csv_file("a;b\n1;2\n3;4\n"), "x.csv")

    assert table.df["a"].tolist() == [1.0, 3.0]
    assert not any("Decimal sign" in m for m in messages(table, "info"))


# ---------------------------------------------------------------------------
# CSV: encodings
# ---------------------------------------------------------------------------

def test_utf8_with_bom():
    table = read_table(csv_file(GERMAN, encoding="utf-8-sig"), "x.csv")

    assert table.df.columns[0] == "Zeitstempel"          # no BOM in the name


def test_windows_1252_with_umlauts():
    text = "Zeit;Wärme (kW);Größe\n01.01.2021 00:00;1,5;2,5\n01.01.2021 01:00;2,5;3,5\n"
    table = read_table(csv_file(text, encoding="cp1252"), "x.csv")

    assert list(table.df.columns) == ["Zeit", "Wärme (kW)", "Größe"]


def test_utf16_file_from_excel_unicode_export():
    table = read_table(GERMAN.encode("utf-16"), "x.txt")

    assert table.used.encoding == "utf-16"
    assert table.df["Last (kW)"].tolist() == [12.5, 13.25, 14.0]


def test_wrong_encoding_override_gives_a_clear_error():
    with pytest.raises(TimeSeriesFileError, match="encoding"):
        read_table(csv_file("Wärme;x\n1;2\n", encoding="cp1252"), "x.csv",
                   ImportOptions(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CSV: where the table starts
# ---------------------------------------------------------------------------

def test_title_and_metadata_lines_above_the_header():
    text = (
        "Lastgang Firma Mueller GmbH\n"
        "Zaehlpunkt;DE0001\n"
        "\n"
        "Zeit;Wirkleistung;Blindleistung\n"
        "01.01.2021 00:00;10,5;1,1\n"
        "01.01.2021 01:00;11,5;1,2\n"
    )
    table = read_table(csv_file(text), "x.csv")

    assert table.used.header_line == 4
    assert table.used.first_data_line == 5
    assert list(table.df.columns) == ["Zeit", "Wirkleistung", "Blindleistung"]
    assert table.row_lines == [5, 6]


def test_unit_line_below_the_header_is_skipped():
    text = (
        "Zeit;Last;PV\n"
        ";kW;kW\n"
        "01.01.2021 00:00;10,5;0\n"
        "01.01.2021 01:00;11,5;0\n"
    )
    table = read_table(csv_file(text), "x.csv")

    assert list(table.df.columns) == ["Zeit", "Last", "PV"]
    assert table.used.first_data_line == 3
    assert table.df["Last"].tolist() == [10.5, 11.5]


def test_file_without_header():
    table = read_table(csv_file("1,5;2,5\n3,5;4,5\n5;6\n"), "x.csv")

    assert table.used.header_line == 0
    assert list(table.df.columns) == ["Column 1", "Column 2"]
    assert len(table.df) == 3


def test_single_column_file():
    table = read_table(csv_file("1\n2\n3\n"), "x.csv")

    assert table.df["Column 1"].tolist() == [1.0, 2.0, 3.0]


def test_empty_lines_and_empty_trailing_columns_are_ignored():
    text = "Zeit;Last;;\n01.01.2021 00:00;1,5;;\n\n01.01.2021 01:00;2,5;;\n\n"
    table = read_table(csv_file(text), "x.csv")

    assert list(table.df.columns) == ["Zeit", "Last"]
    assert len(table.df) == 2


def test_quoted_field_with_the_delimiter_inside():
    text = 'Name;Wert\n"Halle A; Süd";1,5\n"Halle B";2,5\n'
    table = read_table(csv_file(text), "x.csv")

    assert table.df["Name"].tolist() == ["Halle A; Süd", "Halle B"]


def test_duplicate_column_names_are_made_unique():
    table = read_table(csv_file("Last;Last\n1;2\n3;4\n"), "x.csv")

    assert list(table.df.columns) == ["Last", "Last (2)"]


# ---------------------------------------------------------------------------
# CSV: bad values are reported, not hidden
# ---------------------------------------------------------------------------

def test_text_and_empty_values_are_reported_with_the_file_line():
    text = (
        "Zeit;Last\n"
        "01.01.2021 00:00;10,5\n"
        "01.01.2021 01:00;abc\n"
        "01.01.2021 02:00;\n"
        "01.01.2021 03:00;n/a\n"
        "01.01.2021 04:00;7\n"
    )
    table = read_table(csv_file(text), "x.csv")
    warnings = messages(table, "warning")

    assert pd.isna(table.df["Last"].iloc[1])
    assert any("not numbers" in w and "line 3" in w and "abc" in w for w in warnings)
    assert any("2 empty values" in w and "line 4" in w for w in warnings)


# ---------------------------------------------------------------------------
# decimal sign: the hard cases
# ---------------------------------------------------------------------------

def test_leading_zero_is_always_a_decimal_sign():
    text = "Zeit;Wert\n01.01.2021 00:00;0,125\n01.01.2021 01:00;0,375\n"
    table = read_table(csv_file(text), "x.csv")

    assert table.df["Wert"].tolist() == [0.125, 0.375]


def test_ambiguous_numbers_in_a_semicolon_file_are_read_as_decimal_comma():
    # 1,234 could be 1.234 or 1234. A German semicolon file means 1.234.
    text = "Zeit;Wert\n01.01.2021 00:00;1,234\n01.01.2021 01:00;2,345\n"
    table = read_table(csv_file(text), "x.csv")

    assert table.df["Wert"].tolist() == [1.234, 2.345]
    assert any("assumed" in w for w in messages(table, "warning"))


def test_decimal_sign_can_be_overridden():
    text = "Zeit;Wert\n01.01.2021 00:00;1,234\n01.01.2021 01:00;2,345\n"
    table = read_table(csv_file(text), "x.csv", ImportOptions(decimal="."))

    assert table.df["Wert"].tolist() == [1234.0, 2345.0]


def test_dates_are_never_mistaken_for_numbers():
    table = read_table(csv_file(GERMAN), "x.csv")

    assert pd.api.types.is_datetime64_any_dtype(table.df["Zeitstempel"])


# ---------------------------------------------------------------------------
# manual settings
# ---------------------------------------------------------------------------

def test_delimiter_override():
    text = "a;b,c\n1;2,3\n4;5,6\n"
    table = read_table(csv_file(text), "x.csv", ImportOptions(delimiter=","))

    assert list(table.df.columns) == ["a;b", "c"]


def test_header_and_data_line_override():
    text = "x;y\nZeit;Last\n01.01.2021 00:00;1,5\n01.01.2021 01:00;2,5\n"
    table = read_table(
        csv_file(text), "x.csv", ImportOptions(header_line=2, first_data_line=3)
    )

    assert list(table.df.columns) == ["Zeit", "Last"]
    assert len(table.df) == 2


def test_no_header_override():
    table = read_table(
        csv_file(GERMAN), "x.csv", ImportOptions(header_line=0, first_data_line=2)
    )

    assert list(table.df.columns) == ["Column 1", "Column 2", "Column 3"]
    assert len(table.df) == 3


def test_used_options_can_be_fed_back_and_give_the_same_table():
    first = read_table(csv_file(GERMAN), "x.csv")
    second = read_table(csv_file(GERMAN), "x.csv", first.used)

    pd.testing.assert_frame_equal(first.df, second.df)


# ---------------------------------------------------------------------------
# time axis checks
# ---------------------------------------------------------------------------

def test_hourly_data_is_described():
    table = read_table(csv_file(GERMAN), "x.csv")

    assert table.time.step_minutes == 60
    assert table.time.rows == 3
    assert table.time.gaps == 0 and table.time.duplicates == 0


def test_quarter_hourly_data_gets_a_warning():
    rows = "\n".join(f"2021-01-01 {h:02d}:{m:02d},{h}.5" for h in range(3) for m in (0, 15, 30, 45))
    table = read_table(csv_file("Zeit,Last\n" + rows + "\n"), "x.csv")

    assert table.time.step_minutes == 15
    assert any("15 minutes" in w and "hourly" in w for w in messages(table, "warning"))


def test_daylight_saving_duplicates_and_gaps_are_explained():
    autumn = (
        "Zeit;Last\n"
        "26.10.2025 01:00;1\n26.10.2025 02:00;1\n26.10.2025 02:00;1\n26.10.2025 03:00;1\n"
    )
    spring = (
        "Zeit;Last\n"
        "30.03.2025 01:00;1\n30.03.2025 03:00;1\n30.03.2025 04:00;1\n30.03.2025 05:00;1\n"
    )

    assert any("appear twice" in w for w in messages(read_table(csv_file(autumn), "x.csv"), "warning"))
    assert any("gaps" in w for w in messages(read_table(csv_file(spring), "x.csv"), "warning"))


def test_file_without_a_date_column_says_so():
    table = read_table(csv_file("a;b\n1;2\n3;4\n"), "x.csv")

    assert table.time is None
    assert any("No date column" in m for m in messages(table, "info"))


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def test_excel_with_numbers_and_dates():
    content = excel_file({"Daten": [
        ["Zeit", "Last", "PV"],
        [datetime.datetime(2021, 1, 1, 0), 12.5, 0.0],
        [datetime.datetime(2021, 1, 1, 1), 13.25, 0.125],
    ]})
    table = read_table(content, "last.xlsx")

    assert table.kind == "excel"
    assert table.used.sheet == "Daten"
    assert table.df["Last"].tolist() == [12.5, 13.25]
    assert table.time.step_minutes == 60


def test_excel_picks_the_first_sheet_with_data_and_lists_all_sheets():
    content = excel_file({
        "Leer": [],
        "Last": [["Zeit", "Wert"], [1, 2], [3, 4]],
        "Andere": [["a", "b"], [5, 6]],
    })
    table = read_table(content, "x.xlsx")

    assert table.used.sheet == "Last"
    assert table.sheets == ["Leer", "Last", "Andere"]


def test_excel_sheet_can_be_chosen():
    content = excel_file({
        "Erste": [["a", "b"], [1, 2], [3, 4]],
        "Zweite": [["c", "d"], [10, 20], [30, 40]],
    })
    table = read_table(content, "x.xlsx", ImportOptions(sheet="Zweite"))

    assert list(table.df.columns) == ["c", "d"]
    assert table.df["d"].tolist() == [20.0, 40.0]


def test_excel_unknown_sheet_gives_a_clear_error():
    content = excel_file({"Erste": [["a"], [1]]})

    with pytest.raises(TimeSeriesFileError, match="does not exist"):
        read_table(content, "x.xlsx", ImportOptions(sheet="Nope"))


def test_excel_numbers_stored_as_text_with_decimal_comma():
    content = excel_file({"S": [
        ["Zeit", "Last"],
        ["01.01.2021 00:00", "12,5"],
        ["01.01.2021 01:00", "13,25"],
    ]})
    table = read_table(content, "x.xlsx")

    assert table.df["Last"].tolist() == [12.5, 13.25]
    assert table.df["Zeit"].iloc[1] == pd.Timestamp("2021-01-01 01:00")


def test_excel_with_title_rows_and_a_table_starting_in_column_c():
    content = excel_file({"S": [
        ["Export Lastgang"],
        [],
        [None, None, "Zeit", "Last"],
        [None, None, datetime.datetime(2021, 1, 1, 0), 1.5],
        [None, None, datetime.datetime(2021, 1, 1, 1), 2.5],
    ]})
    table = read_table(content, "x.xlsx")

    assert list(table.df.columns) == ["Zeit", "Last"]
    assert table.used.header_line == 3
    assert table.df["Last"].tolist() == [1.5, 2.5]


def test_excel_empty_cells_are_reported():
    content = excel_file({"S": [
        ["Zeit", "Last"],
        [datetime.datetime(2021, 1, 1, 0), 1.5],
        [datetime.datetime(2021, 1, 1, 1), None],
        [datetime.datetime(2021, 1, 1, 2), 3.5],
    ]})
    table = read_table(content, "x.xlsx")

    assert any("1 empty values" in w and "line 3" in w for w in messages(table, "warning"))


def test_damaged_excel_file_gives_a_clear_error():
    with pytest.raises(TimeSeriesFileError, match="cannot be opened"):
        read_table(b"this is not an excel file", "x.xlsx")


# ---------------------------------------------------------------------------
# errors and unsupported files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content", [b"", b"   \n \n"])
def test_empty_file(content):
    with pytest.raises(TimeSeriesFileError, match="empty"):
        read_table(content, "x.csv")


def test_old_excel_format_is_explained():
    with pytest.raises(TimeSeriesFileError, match=r"\.xlsx"):
        read_table(b"whatever", "x.xls")


def test_unknown_file_type():
    with pytest.raises(TimeSeriesFileError, match="not supported"):
        read_table(b"whatever", "x.pdf")


def test_header_only_file():
    with pytest.raises(TimeSeriesFileError):
        read_table(csv_file("Zeit;Last\n"), "x.csv")


# ---------------------------------------------------------------------------
# picking a column
# ---------------------------------------------------------------------------

def test_series_from_column_returns_numbers():
    table = read_table(csv_file(GERMAN), "x.csv")

    assert series_from_column(table, "Last (kW)") == [12.5, 13.25, 14.0]


def test_text_column_cannot_be_used_as_a_series():
    text = "Name;Wert\nHalle A;1,5\nHalle B;2,5\n"
    table = read_table(csv_file(text), "x.csv")

    with pytest.raises(TimeSeriesFileError, match="does not contain numbers"):
        series_from_column(table, "Name")


def test_date_column_cannot_be_used_as_a_series():
    table = read_table(csv_file(GERMAN), "x.csv")

    with pytest.raises(TimeSeriesFileError, match="does not contain numbers"):
        series_from_column(table, "Zeitstempel")


# ---------------------------------------------------------------------------
# size and the way into the model
# ---------------------------------------------------------------------------

def full_year(step_minutes):
    stamps = pd.date_range("2021-01-01", periods=365 * 24 * 60 // step_minutes,
                           freq=f"{step_minutes}min")
    lines = ["Zeitstempel;Last (kW);PV (kW)"]
    for i, stamp in enumerate(stamps):
        lines.append(f"{stamp:%d.%m.%Y %H:%M};{(i % 97) / 7:.3f}".replace(".", ",", 1)
                     + f";{(i % 13) / 10:.2f}".replace(".", ","))
    return csv_file("\n".join(lines) + "\n")


def test_a_full_year_in_quarter_hours_is_read_fast():
    content = full_year(15)                      # 35040 rows

    started = time.perf_counter()
    table = read_table(content, "jahr.csv")
    seconds = time.perf_counter() - started

    assert len(table.df) == 35040
    assert seconds < 5


def test_a_full_year_read_from_a_german_file_passes_the_system_check():
    from backend.system_check import check_system

    table = read_table(full_year(60), "jahr.csv")
    assert len(table.df) == 8760

    data = {
        "timeindex": pd.date_range("2021-01-01", periods=8760, freq="1h"),
        "electricity_demand": series_from_column(table, "Last (kW)"),
    }
    findings = check_system(
        ["demand", "grid"],
        {"grid": {"price_mode": "constant", "variable_costs": 0.3}},
        data,
    )

    assert [f.message for f in findings] == []


def test_excel_prefers_the_sheet_with_numbers_over_a_notes_sheet():
    content = excel_file({
        "Hinweise": [["Bitte das Blatt Daten verwenden"], ["Stand 2021"]],
        "Daten": [["Zeit", "Last"], [1, 2.5], [2, 3.5], [3, 4.5]],
    })
    table = read_table(content, "x.xlsx")

    assert table.used.sheet == "Daten"
    assert table.df["Last"].tolist() == [2.5, 3.5, 4.5]
