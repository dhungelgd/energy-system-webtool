"""The messages of the import of time series files: codes with parameters, in English and German."""

import copy
import io
import pickle

import pytest
from openpyxl import Workbook

from backend.i18n import ENGLISH, Translator, catalog
from backend.timeseries_import import (
    DecimalSign,
    ImportOptions,
    Notice,
    StepText,
    TimeSeriesFileError,
    import_text,
    read_table,
    series_from_column,
)

DE = Translator("de")
EN_CATALOG = catalog("en")


def excel_file(sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def hours(count, minute=0):
    return "".join(f"2021-01-01 {h:02d}:{minute:02d};{h}\n" for h in range(count))


# what makes each message: (the file, its name, the options)
ERRORS = {
    "empty": (b"   ", "x.csv", None),
    "encoding": (b"a;b\n\xe9;1\n", "x.csv", ImportOptions(encoding="utf-8")),
    "unreadable_table": (("a\n" + "x" * 200_000 + "\n").encode(), "x.csv", None),
    "excel_unreadable": (b"this is not an excel file", "x.xlsx", None),
    "sheet_missing": (excel_file({"A": [["t", "v"], [1, 2]]}), "x.xlsx", ImportOptions(sheet="Nope")),
    "excel_empty": (excel_file({"A": []}), "x.xlsx", None),
    "no_data": (b";;\n;;\n", "x.csv", None),
    "xls_old": (b"abc", "x.xls", None),
    "file_type": (b"abc", "x.pdf", None),
    "file_type_none": (b"abc", "datafile", None),
    "no_rows": (b"a;b\n1;2\n", "x.csv", ImportOptions(first_data_line=10)),
}
NOTICES = {
    "time_info": (("t;v\n" + hours(6)).encode(), "x.csv", None),
    "time_step_not_hourly": (("t;v\n" + "".join(f"2021-01-01 00:{m:02d};{m}\n" for m in (0, 15, 30, 45))).encode(), "x.csv", None),
    "unsorted": (b"t;v\n2021-01-01 02:00;1\n2021-01-01 00:00;2\n2021-01-01 01:00;3\n", "x.csv", None),
    "duplicates": (b"t;v\n2021-01-01 00:00;1\n2021-01-01 01:00;2\n2021-01-01 01:00;3\n2021-01-01 02:00;4\n", "x.csv", None),
    "gaps": (b"t;v\n2021-01-01 00:00;1\n2021-01-01 01:00;2\n2021-01-01 03:00;3\n2021-01-01 04:00;4\n", "x.csv", None),
    "no_date_column": (b"a;b\n1;2\n3;4\n5;6\n", "x.csv", None),
    "dates_unreadable": (("t;v\n" + hours(20) + "2021-13-45 00:00;99\n").encode(), "x.csv", None),
    "not_numbers": (("t;v\n" + "".join(f"{h};{h}\n" for h in range(10)) + "10;abc\n").encode(), "x.csv", None),
    "empty_values": (b"a;b\n1;2\n2;\n3;4\n4;5\n", "x.csv", None),
    "decimal_sign": (b"a;b\n1;1,5\n2;2,5\n3;3,5\n", "x.csv", None),
    "decimal_sign_assumed": (b"a;b\n1;1,234\n2;2,345\n3;3,456\n", "x.csv", None),
}


def the_error(content, name, options):
    with pytest.raises(TimeSeriesFileError) as raised:
        read_table(content, name, options)
    return raised.value


def the_notice(code, content, name, options):
    found = [n for n in read_table(content, name, options).messages if n.code == code]
    assert found, f"{code} was not produced"
    return found[0]


def test_the_tour_covers_every_message_of_the_import():
    codes = {key.split(".")[1] for key in EN_CATALOG if key.startswith("import.")}
    codes -= {"step", "sign", "aggregate"}  # parts of sentences, not sentences
    codes -= {"no_time_column", "start_outside", "infinite_values", "column_missing", "column_not_numbers"}
    codes -= {"step_too_long", "step_not_divisor", "convert_needed", "converted", "incomplete_hours"}

    assert codes == set(ERRORS) | set(NOTICES)  # the ten that are left out are tested with the series


@pytest.mark.parametrize("code", list(ERRORS))
def test_every_error_has_a_sentence_in_both_languages(code):
    error = the_error(*ERRORS[code])

    english, german = import_text(error, ENGLISH), import_text(error, DE)

    assert error.code == code
    assert str(error) == english                    # the English sentence is what str() says
    assert "{" not in english and "{" not in german and german != english


@pytest.mark.parametrize("code", list(NOTICES))
def test_every_notice_has_a_sentence_in_both_languages(code):
    notice = the_notice(code, *NOTICES[code])

    english, german = import_text(notice, ENGLISH), import_text(notice, DE)

    assert notice.text == english
    assert "{" not in english and "{" not in german and german != english


def test_the_columns_of_a_table_that_do_not_work_have_sentences_too():
    table = read_table(b"a;b\n1;x\n2;y\n", "x.csv")

    missing = pytest.raises(TimeSeriesFileError, series_from_column, table, "nope").value
    text = pytest.raises(TimeSeriesFileError, series_from_column, table, "b").value

    assert (missing.code, missing.params) == ("column_missing", {"column": "nope"})
    assert import_text(missing, DE) == "Die Spalte 'nope' gibt es nicht."
    assert (text.code, text.params) == ("column_not_numbers", {"column": "b"})
    assert import_text(text, DE) == "Die Spalte 'b' enthält keine Zahlen. Wählen Sie eine andere Spalte."


# ---------------------------------------------------------------------------
# the words
# ---------------------------------------------------------------------------

def test_a_german_sentence_for_a_file_with_a_quarter_hourly_step():
    content, name, options = NOTICES["time_step_not_hourly"]
    notice = the_notice("time_step_not_hourly", content, name, options)

    assert import_text(notice, DE) == (
        "Der Zeitschritt der Datei ist 15 Minuten, das Modell rechnet aber mit Stundenwerten. "
        "Rechnen Sie die Daten zuerst in Stundenwerte um.")
    assert import_text(notice, ENGLISH).startswith("The time step of the file is 15 minutes")


def test_the_time_information_in_both_languages():
    notice = the_notice("time_info", *NOTICES["time_info"])

    assert import_text(notice, ENGLISH) == "Time column 't': 01.01.2021 00:00 to 01.01.2021 05:00, 6 rows, time step 1 hour."
    assert import_text(notice, DE) == "Zeitspalte 't': 01.01.2021 00:00 bis 01.01.2021 05:00, 6 Zeilen, Zeitschritt 1 Stunde."


@pytest.mark.parametrize("minutes, english, german", [
    (15, "15 minutes", "15 Minuten"), (60, "1 hour", "1 Stunde"), (120, "2 hours", "2 Stunden"),
    (90, "1.5 hours", "1,5 Stunden"), (0.5, "0.5 minutes", "0,5 Minuten"),
])
def test_a_time_step_is_worded_in_minutes_or_hours(minutes, english, german):
    assert StepText(minutes).render(ENGLISH) == english
    assert StepText(minutes).render(DE) == german


def test_a_decimal_sign_is_worded_in_both_languages():
    assert DecimalSign(",").render(ENGLISH) == "comma (12,5)" and DecimalSign(",").render(DE) == "Komma (12,5)"
    assert DecimalSign(".").render(ENGLISH) == "point (12.5)" and DecimalSign(".").render(DE) == "Punkt (12.5)"


@pytest.mark.parametrize("count, german", [
    (1, "Spalte 'b': 1 leerer Wert (erster in Zeile 3)."),
    (2, "Spalte 'b': 2 leere Werte (erster in Zeile 3)."),
    (17, "Spalte 'b': 17 leere Werte (erster in Zeile 3)."),
])
def test_german_has_the_singular_and_the_plural(count, german):
    notice = Notice("warning", "empty_values", column="b", n=count, line=3)

    assert import_text(notice, DE) == german


def test_english_keeps_the_sentence_it_always_had_also_for_1():
    assert import_text(Notice("warning", "empty_values", column="b", n=1, line=3), ENGLISH) == (
        "Column 'b': 1 empty values (first in line 3).")
    assert import_text(Notice("warning", "empty_values", column="b", n=4, line=3), ENGLISH) == (
        "Column 'b': 4 empty values (first in line 3).")


@pytest.mark.parametrize("code, one, many", [
    ("duplicates", "1 Zeitstempel kommt doppelt vor.", "3 Zeitstempel kommen doppelt vor."),
    ("gaps", "1 Lücke in den Zeitstempeln.", "3 Lücken in den Zeitstempeln."),
])
def test_german_plurals_of_the_time_axis(code, one, many):
    assert import_text(Notice("warning", code, n=1), DE).startswith(one)
    assert import_text(Notice("warning", code, n=3), DE).startswith(many)


def test_the_value_that_is_not_a_number_is_named():
    notice = the_notice("not_numbers", *NOTICES["not_numbers"])

    assert notice.params == {"column": "v", "n": 1, "line": 12, "value": "abc"}
    assert import_text(notice, DE) == "Spalte 'v': 1 Wert ist keine Zahl (erster in Zeile 12: 'abc')."


# ---------------------------------------------------------------------------
# a notice is still a pair; an error is still an error with a message
# ---------------------------------------------------------------------------

def test_a_notice_unpacks_like_the_pair_that_the_old_code_expects():
    notice = Notice("info", "no_date_column")

    level, text = notice

    assert (level, text) == ("info", "No date column found. The rows are used in the order of the file.")
    assert notice == ("info", text) and notice.level == "info" and notice.text == text and len(notice) == 2


def test_the_messages_of_a_table_can_still_be_read_as_pairs():
    table = read_table(*NOTICES["time_step_not_hourly"][:2])

    assert any(level == "warning" and "15 minutes" in text and "hourly" in text for level, text in table.messages)


def test_an_error_says_its_english_sentence_when_it_is_printed():
    error = TimeSeriesFileError("sheet_missing", sheet="Daten")

    assert str(error) == "The sheet 'Daten' does not exist."
    assert isinstance(error, ValueError) and (error.code, error.params) == ("sheet_missing", {"sheet": "Daten"})


def test_errors_and_notices_can_be_copied_and_sent_between_processes():
    error = TimeSeriesFileError("encoding", encoding="utf-8")
    notice = Notice("warning", "time_step_not_hourly", step=StepText(15))
    decimal = Notice("info", "decimal_sign", sign=DecimalSign(","))

    for item in (error, notice, decimal):
        for again in (pickle.loads(pickle.dumps(item)), copy.deepcopy(item)):
            assert again.code == item.code and again.params == item.params
            assert import_text(again, DE) == import_text(item, DE)
            assert type(again) is type(item) and str(again) == str(item)


def test_a_file_with_a_huge_field_is_an_error_with_a_sentence_and_not_a_crash():
    # the detection of the separator used to read the file before the try: the csv module's own error got out
    error = the_error(*ERRORS["unreadable_table"])

    assert error.code == "unreadable_table" and "field larger than field limit" in error.params["error"]
    assert import_text(error, DE).startswith("Die Datei kann nicht als Tabelle gelesen werden:")