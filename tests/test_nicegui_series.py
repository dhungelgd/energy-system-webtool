"""The time series of the components on the NiceGUI page (simulated user, no browser)."""

import asyncio
import io
from datetime import datetime, timedelta

import pytest

pytest.importorskip("nicegui")
from nicegui import ElementFilter, ui  # noqa: E402
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402
from openpyxl import Workbook  # noqa: E402

from backend.i18n import catalog  # noqa: E402
from frontend_nicegui.markers import slug  # noqa: E402


def field(user: User, marker: str):
    return user.find(marker=marker).elements.pop()


def exists(user: User, marker: str):
    with user.client:
        return bool(list(ElementFilter(marker=marker)))


def labels(user: User, marker: str):
    return [element.text for element in field(user, marker).descendants() if isinstance(element, ui.label)]


async def settle():
    await asyncio.sleep(0.3)


async def open_page(user: User, language=None):
    await user.open("/" if language is None else f"/?lang={language}")


async def choose_template(user: User, name: str):
    user.find(marker=f"template-{slug(name)}").click()
    await user.should_see(marker="selection-count")


async def switched_to(user: User, language: str):
    field(user, "language").value = language
    await user.should_see(marker="app-title", content=catalog(language)["app.title"])


def csv(values, name="Last (kW)", minutes=60, start="2021-01-01 00:00", decimal=".", extra=None):
    """A CSV file with a time column and one column of values (and maybe a second column)."""

    head = f"Zeit;{name}" + (f";{extra[0]}" if extra else "")
    rows = [head]
    first = datetime.fromisoformat(start)
    for i, value in enumerate(values):
        moment = first + timedelta(minutes=minutes) * i
        text = "" if value is None else str(value).replace(".", decimal)
        more = f";{str(extra[1][i]).replace('.', decimal)}" if extra else ""
        rows.append(f"{moment:%Y-%m-%d %H:%M};{text}{more}")
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


async def upload(user: User, key: str, content: bytes, name="daten.csv"):
    kind = "application/octet-stream"
    await field(user, f"series-upload-{key}").handle_uploads([SmallFileUpload(name, kind, content)])
    await user.should_see(marker=f"series-prepare-{key}")


async def use(user: User, key: str):
    user.find(marker=f"series-use-{key}").click()
    await user.should_see(marker=f"series-summary-{key}")


DAY = [1 + h / 10 for h in range(24)]                 # 1.0 to 3.3
SUM_OF_DAY = "51.6"


# ---------------------------------------------------------------------------
# who has a section
# ---------------------------------------------------------------------------

async def test_the_components_with_a_time_series_have_a_section_and_the_others_do_not(user: User):
    await open_page(user)

    await choose_template(user, "Full system")

    for key in ("demand", "heat_demand", "pv", "wind", "grid", "heat_pump"):
        assert exists(user, f"series-upload-{key}") or exists(user, f"series-mode-{key}"), key
    for key in ("battery", "gas_boiler", "chp", "heat_storage", "grid_feedin", "gas_import", "heating_rod"):
        assert not exists(user, f"series-upload-{key}") and not exists(user, f"series-mode-{key}"), key


async def test_the_section_says_what_the_series_is_for(user: User):
    await open_page(user)

    await choose_template(user, "PV system")

    await user.should_see("Time series")
    await user.should_see("The hourly availability of the PV system between 0 and 1")
    await user.should_see("One value for each hour. What the values mean")
    await user.should_see("No time series yet.")


# ---------------------------------------------------------------------------
# a file is prepared and used
# ---------------------------------------------------------------------------

async def test_a_file_is_prepared_and_used_and_the_check_follows(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    await user.should_see("Electricity demand: no time series uploaded")

    await upload(user, "demand", csv(DAY))
    assert field(user, "series-column-demand").value == "Last (kW)"
    await use(user, "demand")

    assert labels(user, "series-summary-demand")[:2] == [
        f"24 values from 1 to 3.3, sum {SUM_OF_DAY}.", "From the file daten.csv, column Last (kW)."]
    await user.should_not_see("Electricity demand: no time series uploaded")
    assert not exists(user, "series-prepare-demand")                         # the panel is closed


async def test_the_preview_shows_the_first_rows_of_the_file(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    await upload(user, "pv", csv(DAY))

    rows = field(user, "series-preview-pv").rows
    assert len(rows) == 8 and rows[0] == {"0": "01.01.2021 00:00", "1": "1"} and rows[1]["1"] == "1.1"
    await user.should_see("Preview: 24 rows, 2 columns. The first rows are shown.")


async def test_another_column_can_be_chosen(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await upload(user, "pv", csv(DAY, extra=("PV", [h / 24 for h in range(24)])))
    assert field(user, "series-column-pv").options == ["Last (kW)", "PV"]

    field(user, "series-column-pv").value = "PV"
    await settle()
    await use(user, "pv")

    assert labels(user, "series-summary-pv")[0].startswith("24 values from 0 to 0.958333, sum 11.5")


async def test_a_sheet_of_an_excel_file_can_be_chosen(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    book = excel({"Notes": [["hello", "world"], [1, 2]], "Data": [["t", "v"]] + [[h, 0.5] for h in range(24)]})

    await upload(user, "pv", book, name="daten.xlsx")

    assert field(user, "series-sheet-pv").options == ["Notes", "Data"] and field(user, "series-sheet-pv").value == "Data"
    assert field(user, "series-column-pv").options == ["t", "v"]             # the sheet with the data was found by itself

    field(user, "series-sheet-pv").value = "Notes"
    await settle()

    assert field(user, "series-column-pv").options == ["hello", "world"] and field(user, "series-column-pv").value == "hello"


async def test_a_new_file_replaces_the_one_that_is_being_prepared(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await upload(user, "pv", csv(DAY))

    await field(user, "series-upload-pv").handle_uploads([SmallFileUpload("zweite.csv", "text/csv", csv(DAY))])
    await settle()

    await user.should_see("File: zweite.csv")
    await user.should_not_see("File: daten.csv")


async def test_cancel_closes_the_panel_and_changes_nothing(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    await upload(user, "demand", csv(DAY))

    user.find(marker="series-cancel-demand").click()
    await settle()

    assert not exists(user, "series-prepare-demand") and not exists(user, "series-summary-demand")
    await user.should_see("Electricity demand: no time series uploaded")


async def test_the_series_can_be_taken_away(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    await upload(user, "demand", csv(DAY))
    await use(user, "demand")

    user.find(marker="series-remove-demand").click()

    await user.should_see("No time series yet.")
    await user.should_see("Electricity demand: no time series uploaded")
    assert not exists(user, "series-summary-demand")


async def test_a_series_that_is_too_short_for_the_period_is_found_by_the_check(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")                           # a year is 8760 steps

    await upload(user, "demand", csv(DAY))
    await use(user, "demand")

    await user.should_see("Electricity demand: the time series has 24 values, but the selected time range needs 8760")


# ---------------------------------------------------------------------------
# a file that does not work
# ---------------------------------------------------------------------------

# (the ids are short on purpose: pytest puts the name of a running test in an environment variable, and a
# file with 200,000 characters as the name is more than Windows allows)
@pytest.mark.parametrize("content, name, sentence", [
    pytest.param(b"   ", "leer.csv", "The file is empty.", id="empty"),
    pytest.param(b"abc", "bild.pdf", "The file type '.pdf' is not supported. Use CSV, TXT, TSV or Excel (.xlsx).",
                 id="wrong-type"),
    pytest.param(b"abc", "alt.xls", "The old Excel format (.xls) is not supported.", id="old-excel"),
    pytest.param(("a\n" + "x" * 200_000 + "\n").encode(), "riesig.csv", "The file cannot be read as a table:",
                 id="huge-field"),
    pytest.param(b"Name;Ort\na;b\nc;d\n", "text.csv", "The file has no column with numbers.", id="no-numbers"),
])
async def test_a_file_that_does_not_work_is_explained_and_nothing_can_be_used(user: User, content, name, sentence):
    await open_page(user)
    await choose_template(user, "PV system")

    await upload(user, "pv", content, name=name)

    await user.should_see(sentence)
    assert not exists(user, "series-use-pv")


async def test_the_explanation_of_a_file_that_does_not_work_is_in_german(user: User):
    await open_page(user, "de")
    await choose_template(user, "PV system")

    await upload(user, "pv", b"   ", name="leer.csv")

    await user.should_see("Die Datei ist leer.")


# ---------------------------------------------------------------------------
# which part of the file, and in which unit
# ---------------------------------------------------------------------------

async def test_the_start_of_the_scenario_is_used_when_the_file_includes_it(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    user.find(marker="draft-start").clear().type("2021-03-02")
    user.find(marker="draft-steps").clear().type("24")
    await settle()

    await upload(user, "demand", csv(range(48), start="2021-03-01 00:00"))

    assert field(user, "series-start-demand").value == "scenario"
    await user.should_see("From the start of the scenario (2021-03-02)")
    await use(user, "demand")
    assert labels(user, "series-summary-demand")[0].startswith("24 values from 24 to 47")


async def test_the_first_row_of_the_file_can_be_chosen_instead(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    user.find(marker="draft-start").clear().type("2021-03-02")
    await settle()
    await upload(user, "demand", csv(range(48), start="2021-03-01 00:00"))

    field(user, "series-start-demand").value = "file"
    await settle()
    await use(user, "demand")

    assert labels(user, "series-summary-demand")[0].startswith("48 values from 0 to 47")


async def test_a_file_that_does_not_include_the_start_is_used_from_its_first_row_and_the_visitor_is_told(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")

    await upload(user, "demand", csv(range(24), start="2022-06-01 00:00"))

    await user.should_see("The start of the scenario (2021-01-01) is not in the file. The file is used from its first row.")
    assert not exists(user, "series-start-demand")
    await use(user, "demand")
    assert labels(user, "series-summary-demand")[0].startswith("24 values from 0 to 23")


async def test_the_decimal_sign_is_only_mentioned_when_the_program_was_not_sure(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    await upload(user, "pv", csv(DAY, decimal=","))                          # clearly a decimal comma
    await user.should_not_see("Decimal sign: ")                              # (the label of the setting says "Decimal sign")

    await upload(user, "pv", b"a;b\n1;1,234\n2;2,345\n3;3,456\n")
    await user.should_see("Decimal sign: comma (12,5) - assumed, please check the preview.")


async def test_a_file_without_dates_has_no_start_to_choose(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    await upload(user, "pv", b"Wert\n0.1\n0.2\n0.3\n")

    assert not exists(user, "series-start-pv") and not exists(user, "series-start-note-pv")
    await user.should_see("No date column found. The rows are used in the order of the file.")


# ---------------------------------------------------------------------------
# a time step shorter than an hour
# ---------------------------------------------------------------------------

async def test_a_quarter_hourly_file_is_converted_and_the_visitor_is_told(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    await upload(user, "pv", csv([0.5] * 96, minutes=15))

    await user.should_see("Converted 96 values with a time step of 15 minutes to 24 hourly values (average).")
    await use(user, "pv")
    assert labels(user, "series-summary-pv")[0].startswith("24 values from 0.5 to 0.5")


async def test_shares_of_the_annual_demand_are_added_up_without_a_question(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")

    await upload(user, "demand", csv([0.25] * 96, minutes=15))

    assert not exists(user, "series-aggregate-demand")
    await user.should_see("(sum).")
    await use(user, "demand")
    assert labels(user, "series-summary-demand")[0].startswith("24 values from 1 to 1")


async def test_a_demand_in_kw_has_to_say_how_the_values_are_converted(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    field(user, "field-demand-demand-profile_type").value = "absolute"
    await settle()

    await upload(user, "demand", csv([0.25] * 96, minutes=15))

    assert exists(user, "series-aggregate-demand") and not exists(user, "series-use-demand")
    await user.should_see("Choose how to convert the values to hourly values.")
    assert field(user, "series-aggregate-demand").options == {
        "mean": "Power in kW (the average of the hour is used)",
        "sum": "Energy per time step in kWh (the sum of the hour is used)"}

    field(user, "series-aggregate-demand").value = "sum"
    await settle()
    assert exists(user, "series-use-demand")
    await use(user, "demand")

    assert labels(user, "series-summary-demand")[0].startswith("24 values from 1 to 1")        # 4 x 0.25 kWh is 1 kW


async def test_the_same_demand_as_power_is_the_average(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    field(user, "field-demand-demand-profile_type").value = "absolute"
    await settle()
    await upload(user, "demand", csv([0.25] * 96, minutes=15))

    field(user, "series-aggregate-demand").value = "mean"
    await settle()
    await use(user, "demand")

    assert labels(user, "series-summary-demand")[0].startswith("24 values from 0.25 to 0.25")


async def test_a_file_with_a_time_step_that_cannot_be_converted_is_explained(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    await upload(user, "pv", csv([0.5] * 10, minutes=45))

    await user.should_see("does not divide an hour evenly")
    assert not exists(user, "series-use-pv")


# ---------------------------------------------------------------------------
# the grid price and the COP: a constant or a series
# ---------------------------------------------------------------------------

PRICE = "field-grid-costs-variable_costs"


async def test_the_grid_asks_first_whether_the_price_is_a_constant_or_a_series(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")

    assert field(user, "series-mode-grid").value == "constant"
    assert field(user, "series-mode-grid").options == {"constant": "A constant price", "series": "A time series"}
    assert not exists(user, "series-upload-grid") and exists(user, PRICE)


async def test_the_unit_of_the_prices_in_the_file_is_chosen_and_stored_in_euro_per_kwh(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    field(user, "series-mode-grid").value = "series"
    await user.should_see(marker="series-upload-grid")
    await user.should_see("No time series yet. Until you use one, the constant value is used.")

    await upload(user, "grid", csv([25.0 + h % 6 for h in range(24)], name="Preis"))
    assert field(user, "series-price-unit-grid").options == ["€/kWh", "ct/kWh", "€/MWh"]
    field(user, "series-price-unit-grid").value = "ct/kWh"
    await settle()
    await use(user, "grid")

    assert labels(user, "series-summary-grid")[0].startswith("24 values from 0.25 to 0.3")


async def test_a_series_replaces_the_price_and_the_price_comes_back_with_the_constant(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    user.find(marker=PRICE).clear().type("0.35")
    await settle()
    field(user, "series-mode-grid").value = "series"
    await user.should_see(marker="series-upload-grid")
    assert exists(user, PRICE)                                               # still the constant that is used

    await upload(user, "grid", csv([0.3] * 24, name="Preis"))
    await use(user, "grid")
    await settle()
    assert not exists(user, PRICE)                                           # the series replaces it

    field(user, "series-mode-grid").value = "constant"
    await user.should_see(marker=PRICE)

    assert field(user, PRICE).value == 0.35 and not exists(user, "series-summary-grid")


async def test_the_heat_pump_asks_first_too_and_keeps_its_cop(user: User):
    await open_page(user)
    await choose_template(user, "Heat pump + heating rod")
    cop = "field-heat_pump-conversion-outputs.heat.ratio"
    user.find(marker=cop).clear().type("4.2")
    await settle()
    assert field(user, "series-mode-heat_pump").options["constant"] == "A constant COP"

    field(user, "series-mode-heat_pump").value = "series"
    await user.should_see(marker="series-upload-heat_pump")
    await upload(user, "heat_pump", csv([3.0 + h / 24 for h in range(24)], name="COP"))
    await use(user, "heat_pump")
    await settle()
    assert not exists(user, cop)

    field(user, "series-mode-heat_pump").value = "constant"
    await user.should_see(marker=cop)

    assert field(user, cop).value == 4.2


async def test_taking_the_series_of_the_grid_away_goes_back_to_the_constant(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    field(user, "series-mode-grid").value = "series"
    await user.should_see(marker="series-upload-grid")
    await upload(user, "grid", csv([0.3] * 24, name="Preis"))
    await use(user, "grid")

    user.find(marker="series-remove-grid").click()
    await user.should_see(marker=PRICE)

    assert field(user, "series-mode-grid").value == "constant"


# ---------------------------------------------------------------------------
# the import settings
# ---------------------------------------------------------------------------

async def test_a_setting_of_the_import_changes_how_the_file_is_read(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await upload(user, "pv", b"a;b\n1;1,234\n2;2,345\n3;3,456\n")
    assert field(user, "series-preview-pv").rows[0]["1"] == "1.234"

    field(user, "series-decimal-pv").value = "."
    await settle()

    assert field(user, "series-preview-pv").rows[0]["1"] == "1234"


async def test_the_settings_of_a_csv_file_and_of_an_excel_file(user: User):
    await open_page(user)
    await choose_template(user, "PV system")

    await upload(user, "pv", csv(DAY))
    assert all(exists(user, f"series-{name}-pv") for name in ("delimiter", "decimal", "encoding", "header-line", "first-data-line"))
    assert field(user, "series-delimiter-pv").value == "auto"

    await upload(user, "pv", excel({"Data": [["t", "v"]] + [[h, 0.5] for h in range(24)]}), name="daten.xlsx")
    await user.should_see("File: daten.xlsx")                                 # the new file has replaced the first one
    assert exists(user, "series-decimal-pv") and not exists(user, "series-delimiter-pv") and not exists(user, "series-encoding-pv")


async def test_the_lines_of_the_file_can_be_set(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await upload(user, "pv", csv(DAY))
    assert field(user, "series-header-line-pv").value == 1 and field(user, "series-first-data-line-pv").value == 2

    field(user, "series-first-data-line-pv").value = 12
    await settle()

    assert len(field(user, "series-preview-pv").rows) == 8
    await user.should_see("Preview: 14 rows")                                  # the lines 12 to 25 of 25


async def test_the_box_with_the_settings_stays_open_when_the_page_is_drawn_again(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await upload(user, "pv", csv(DAY))
    expansion = next(e for e in field(user, "series-prepare-pv").descendants() if isinstance(e, ui.expansion))
    expansion.value = True
    await settle()

    field(user, "series-decimal-pv").value = "."
    await settle()

    again = next(e for e in field(user, "series-prepare-pv").descendants() if isinstance(e, ui.expansion))
    assert again.value is True


# ---------------------------------------------------------------------------
# what is kept and what is dropped
# ---------------------------------------------------------------------------

async def test_the_file_and_the_choices_stay_when_the_language_changes(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await upload(user, "pv", csv(DAY, extra=("PV", [h / 24 for h in range(24)])))
    field(user, "series-column-pv").value = "PV"
    await settle()

    await switched_to(user, "de")

    await user.should_see("Datei: daten.csv")
    assert field(user, "series-column-pv").value == "PV"
    await user.should_see("Diese Zeitreihe verwenden")


async def test_a_series_that_is_used_stays_when_the_language_changes(user: User):
    await open_page(user)
    await choose_template(user, "Electricity only")
    await upload(user, "demand", csv(DAY))
    await use(user, "demand")

    await switched_to(user, "de")

    assert labels(user, "series-summary-demand")[0] == f"24 Werte von 1 bis 3,3, Summe {SUM_OF_DAY.replace('.', ',')}."


async def test_a_file_that_is_being_prepared_is_dropped_with_its_component(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await upload(user, "pv", csv(DAY))

    user.find(marker="component-pv").click()
    await user.should_not_see(marker="series-upload-pv")
    user.find(marker="component-pv").click()
    await user.should_see(marker="series-upload-pv")

    assert not exists(user, "series-prepare-pv")


async def test_a_series_stays_when_the_template_changes_and_goes_with_its_component(user: User):
    await open_page(user)
    await choose_template(user, "PV system")
    await upload(user, "demand", csv(DAY))
    await use(user, "demand")
    await upload(user, "pv", csv([0.5] * 24, name="PV"))
    await use(user, "pv")

    await choose_template(user, "Electricity only")                           # the PV system goes, the demand stays

    await user.should_not_see(marker="series-summary-pv")
    assert exists(user, "series-summary-demand")


# ---------------------------------------------------------------------------
# in German
# ---------------------------------------------------------------------------

async def test_the_section_and_the_preparation_are_in_german(user: User):
    await open_page(user, "de")
    await choose_template(user, "Electricity only")

    await user.should_see("Zeitreihe")
    await user.should_see("Noch keine Zeitreihe.")
    await upload(user, "demand", csv(DAY, decimal=","))

    await user.should_see("Datei: daten.csv")
    await user.should_see("Spalte mit den Werten")
    await user.should_see("Welcher Teil der Datei wird verwendet?")
    await user.should_see("Ab dem Start des Szenarios (2021-01-01)")
    await user.should_see("Importeinstellungen")
    assert field(user, "series-preview-demand").rows[1]["1"] == "1,1"
    await use(user, "demand")
    assert labels(user, "series-summary-demand")[:2] == [
        "24 Werte von 1 bis 3,3, Summe 51,6.", "Aus der Datei daten.csv, Spalte Last (kW)."]


async def test_the_choices_of_the_grid_and_the_conversion_are_in_german(user: User):
    await open_page(user, "de")
    await choose_template(user, "Electricity only")
    assert field(user, "series-mode-grid").options == {"constant": "Ein fester Preis", "series": "Eine Zeitreihe"}

    field(user, "series-mode-grid").value = "series"
    await user.should_see("Noch keine Zeitreihe. Bis Sie eine verwenden, gilt der feste Wert.")
    await upload(user, "grid", csv([25.0] * 96, name="Preis", minutes=15))

    await user.should_see("96 Werte mit einem Zeitschritt von 15 Minuten wurden in 24 Stundenwerte umgerechnet (Mittelwert).")
    await user.should_see("Einheit der Preise in der Datei")