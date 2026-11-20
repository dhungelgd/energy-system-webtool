"""The Excel file of a result: the numbers of a run for those who want to check them or work with them.

It holds what the PDF report cannot: every hourly value of each energy carrier and of each time series that was used.
The sheets are: the summary, the costs, the capacities, one sheet for each energy carrier, the scenario (its
period, its components with their settings, its time series), the values of the time series and the energy of each
month. There are no charts in it: they are in the report and on the page. The numbers are
numbers (Excel shows them with the separators of its own language and can calculate with them); the words are in
the language of the reader. No NiceGUI code in here, so it is easy to test; the look is that of the report.
"""

import io
import math
import re
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from backend.i18n import ENGLISH
from frontend_nicegui.forms import FORMS, form_fields
from frontend_nicegui.names import display_name
from frontend_nicegui.report_charts import monthly_data
from frontend_nicegui.report_data import date_text
from frontend_nicegui.result_charts import ZERO_FLOW, split_flows
from frontend_nicegui.result_terms import DECIMALS, TEXT_COLUMNS, bus_label, node_label, term
from frontend_nicegui.result_view import chosen_sizes, period_caption, solver_text
from frontend_nicegui.scenario_view import component_rows, describe_period, series_rows

SHEET_NAME_LENGTH = 31                 # Excel allows no more
BLUE, DARK, LIGHT = "005D9D", "004578", "EAF3FA"
HEAD_FILL = PatternFill("solid", fgColor=BLUE)
HEAD_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color=DARK)
SECTION_FONT = Font(bold=True, size=12, color=DARK)
GREY_FONT = Font(color="5B6B7B")
MAX_WIDTH = 60
NUMBER_FORMATS = {0: "#,##0", 1: "#,##0.0"}
OTHER_NUMBER_FORMAT = "#,##0.00"
FLOW_FORMAT = "0.00"                  # the hourly values show two decimals (the cell holds all of them)
NOTE_CHARACTERS = 110                 # about how many characters of a note fit in a line over the columns of the summary


def sheet_name(text, used):
    """A name for a sheet: at most 31 characters, none of []:*?/\\, and not a name that another sheet has."""

    name = re.sub(r"[\[\]:*?/\\]", " ", str(text)).strip()[:SHEET_NAME_LENGTH].strip() or "Sheet"
    candidate, number = name, 2
    while candidate.lower() in used:
        suffix = f" {number}"
        candidate, number = name[:SHEET_NAME_LENGTH - len(suffix)] + suffix, number + 1
    used.add(candidate.lower())

    return candidate


def excel_date_format(tr):
    """The format of a date and time in Excel, from the format of the date of the reader (2021-01-31 18:00, 31.01.2021 18:00)."""

    return tr("result.chart.date_format").replace("%Y", "yyyy").replace("%m", "mm").replace("%d", "dd") + " hh:mm"


def _write_head(sheet, row, columns):
    for column, text in enumerate(columns, start=1):
        cell = sheet.cell(row=row, column=column, value=text)
        cell.fill, cell.font = HEAD_FILL, HEAD_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def _write_rows(sheet, first_row, rows, formats=None):
    """Write rows below `first_row`; `formats` is a number format for each column (or None)."""

    for offset, row in enumerate(rows):
        for column, value in enumerate(row, start=1):
            cell = sheet.cell(row=first_row + offset, column=column, value=value)
            if formats and formats[column - 1] and isinstance(value, (int, float)) and not isinstance(value, bool):
                cell.number_format = formats[column - 1]

    return first_row + len(rows)


def _note(sheet, row, text, columns=4, font=GREY_FONT):
    """A long text over several columns, wrapped (a merged cell does not size its row by itself)."""

    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=columns)
    cell = sheet.cell(row=row, column=1, value=text)
    cell.font, cell.alignment = font, Alignment(wrap_text=True, vertical="top")
    sheet.row_dimensions[row].height = 15 * max(1, math.ceil(len(text) / NOTE_CHARACTERS))


def _page(sheet):
    """Print the sheet in landscape, one page wide."""

    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True


def _widths(sheet, minimum=10):
    for column in sheet.columns:
        longest = max((len(str(cell.value)) for cell in column if cell.value is not None and not isinstance(cell.value, (int, float))), default=0)
        longest = max(longest, 12 if any(isinstance(cell.value, (int, float)) for cell in column) else 0)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = min(max(longest + 2, minimum), MAX_WIDTH)


def translated_table(table, tr):
    """A result table as (column titles, rows, number formats): the words in the language of the reader, the numbers as
    numbers, an empty cell empty."""

    columns = [term(tr, name) for name in table.columns]
    rows = [[None if value is None else term(tr, value) if isinstance(value, str) and name in TEXT_COLUMNS else value
             for name, value in zip(table.columns, row)] for row in table.rows]
    formats = [None if name in TEXT_COLUMNS else NUMBER_FORMATS.get(DECIMALS.get(name), OTHER_NUMBER_FORMAT) for name in table.columns]

    return columns, rows, formats


# ---------------------------------------------------------------------------
# the sheets
# ---------------------------------------------------------------------------

def _summary(book, scenario, result, tr, today, used):
    sheet = book.active
    sheet.title = sheet_name(tr("excel.sheet.summary"), used)
    sheet["A1"], sheet["A1"].font = scenario.name, TITLE_FONT
    sheet["A2"], sheet["A2"].font = f"{tr('report.subtitle')} · {tr('excel.created')} {date_text(today, tr)}", GREY_FONT

    sheet.cell(row=4, column=1, value=tr("report.fact.period")).font = Font(bold=True)
    sheet.cell(row=4, column=2, value=describe_period(scenario, tr))
    sheet.cell(row=5, column=1, value=solver_text(result, tr)).font = GREY_FONT
    row = 6

    caption = period_caption(result, tr)
    if caption is not None:
        _note(sheet, row, caption)
        row += 1

    row += 1
    sheet.cell(row=row, column=1, value=tr("report.section.figures")).font = SECTION_FONT
    _write_head(sheet, row + 1, [tr("excel.col.figure"), tr("excel.col.value"), tr("table.unit"), tr("excel.col.help")])
    figures = [[term(tr, f.label), f.value, f.unit, term(tr, f.help)] for f in result.key_figures]
    first = row + 2
    row = _write_rows(sheet, first, figures, [None, OTHER_NUMBER_FORMAT, None, None]) + 1
    for number in range(first, row - 1):
        for column in (1, 2, 3):
            sheet.cell(row=number, column=column).alignment = Alignment(vertical="top")
        sheet.cell(row=number, column=4).alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[number].height = 15 * max(1, math.ceil(len(str(sheet.cell(row=number, column=4).value or "")) / 62))

    chosen = chosen_sizes(result, tr)
    sheet.cell(row=row, column=1, value=tr("result.chosen.title")).font = SECTION_FONT
    if chosen["built"]:
        _write_head(sheet, row + 1, [tr("table.component"), tr("table.size"), tr("excel.col.cost_year")])
        row = _write_rows(sheet, row + 2, [[item["name"], item["size"], item["cost"]] for item in chosen["built"]])
    else:
        row += 1
    if not chosen["any"]:
        sheet.cell(row=row, column=1, value=tr("result.chosen.none")).font = GREY_FONT
        row += 1
    if chosen["not_built"]:
        sheet.cell(row=row, column=1, value=tr("result.chosen.not_built", names=", ".join(chosen["not_built"]))).font = GREY_FONT
        row += 1

    _widths(sheet)
    sheet.column_dimensions["A"].width = 34
    sheet.column_dimensions["D"].width = MAX_WIDTH
    _note(sheet, row + 1, tr("report.note.model"))


def _table_sheet(book, title, table, tr, used, empty_text):
    sheet = book.create_sheet(sheet_name(title, used))
    if not table.rows:
        sheet["A1"], sheet["A1"].font = empty_text, GREY_FONT
        return

    columns, rows, formats = translated_table(table, tr)
    _write_head(sheet, 1, columns)
    _write_rows(sheet, 2, rows, formats)
    sheet.freeze_panes = "A2"
    _widths(sheet)


def flow_columns(bus, summary, tr):
    """The columns of the hourly flows of a carrier: (title, values) for each flow that is not zero all the time,
    supplies first, then the demand, then other uses (named as a use)."""

    frame = summary.flows.to_frame(with_end_row=False)
    supply, demand, other = split_flows(frame.columns, bus)
    columns = []

    for names, side, use in ((supply, 0, False), (demand, 1, False), (other, 1, True)):
        for name in names:
            if frame[name].abs().max() <= ZERO_FLOW:
                continue
            label = node_label(tr, name.split("-->")[side])
            columns.append((f"{tr('result.chart.as_use', name=label) if use else label} [kW]", [round(v, 6) for v in frame[name].tolist()]))

    return frame.index, columns


def _bus_sheet(book, bus, summary, tr, used):
    sheet = book.create_sheet(sheet_name(bus_label(tr, bus), used))
    flows = summary.flows

    if flows is None or not flows.columns:
        sheet["A1"], sheet["A1"].font = tr("result.no_flows"), GREY_FONT
        return

    index, columns = flow_columns(bus, summary, tr)
    if not columns:
        sheet["A1"], sheet["A1"].font = tr("result.nothing_flows"), GREY_FONT
        return

    _write_head(sheet, 1, [tr("excel.col.time"), *[title for title, _ in columns]])
    for number, stamp in enumerate(index.to_pydatetime(), start=2):
        sheet.cell(row=number, column=1, value=stamp).number_format = excel_date_format(tr)
    for column, (_, values) in enumerate(columns, start=2):
        for number, value in enumerate(values, start=2):
            sheet.cell(row=number, column=column, value=value).number_format = FLOW_FORMAT
    sheet.freeze_panes = "B2"
    _widths(sheet, 12)
    sheet.column_dimensions["A"].width = 18


def flatten(settings, prefix=""):
    """The settings of a component as (path, value): {'capacity': {'mode': 'fixed'}} gives ('capacity.mode', 'fixed')."""

    found = []
    for key, value in settings.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            found += flatten(value, path)
        elif isinstance(value, (list, tuple)):
            found.append((path, ", ".join(str(v) for v in value)))
        else:
            found.append((path, value))

    return found


def humanize(path):
    """A readable name for the path of a setting that has no text of its own: 'costs.variable_costs' gives 'Costs › Variable costs'."""

    return " › ".join(part.replace("_", " ").capitalize() for part in path.split("."))


def settings_rows(scenario, tr):
    """The settings of every component as [component, setting, value, unit], with the names and units that the form of
    the component shows (in the language of the reader), and a choice as the words of the choice."""

    rows = []
    for component in scenario.components:
        name = display_name(component, tr)
        blocks = FORMS.get(component.template)
        if blocks is None:                                  # a component without a form: its settings as they are
            for block_name, block in component.blocks.items():
                rows += [[name, humanize(f"{block_name}.{path}"), value, ""] for path, value in flatten(block)]
            continue
        for block_name in blocks:
            for entry in form_fields(component, block_name, tr):
                value = entry.options.get(entry.value, entry.value) if entry.kind == "choice" else entry.value
                rows.append([name, entry.label, tr("row.size.not_set") if value is None else value, entry.unit])

    return rows


def _statistics(values):
    """How many values a series has, how many of them are empty, the smallest and the largest (numbers, not text)."""

    present = [v for v in values if v is not None]

    return [len(values), len(values) - len(present), min(present) if present else None, max(present) if present else None]


def _source(origin):
    if origin is None or not origin.file:
        return ""

    return f"{origin.file}, {origin.column}" if origin.column else origin.file


def _scenario_sheet(book, scenario, tr, used):
    sheet = book.create_sheet(sheet_name(tr("excel.sheet.scenario"), used))
    sheet["A1"], sheet["A1"].font = scenario.name, TITLE_FONT
    sheet["A2"] = describe_period(scenario, tr)
    row = 4

    sheet.cell(row=row, column=1, value=tr("report.scenario.components")).font = SECTION_FONT
    _write_head(sheet, row + 1, [tr("table.component"), tr("table.type"), tr("table.mode"), tr("table.size")])
    row = _write_rows(sheet, row + 2, [[r["component"], r["type"], r["mode"], r["size"]] for r in component_rows(scenario, tr)]) + 1

    sheet.cell(row=row, column=1, value=tr("excel.settings")).font = SECTION_FONT
    _write_head(sheet, row + 1, [tr("table.component"), tr("excel.col.setting"), tr("excel.col.value"), tr("table.unit")])
    row = _write_rows(sheet, row + 2, settings_rows(scenario, tr)) + 1

    series = series_rows(scenario, tr)
    if series:
        sheet.cell(row=row, column=1, value=tr("report.scenario.series")).font = SECTION_FONT
        _write_head(sheet, row + 1, [tr("table.used_by"), tr("table.unit"), tr("table.values"), tr("table.empty"), tr("table.min"), tr("table.max"), tr("report.col.source")])
        _write_rows(sheet, row + 2, [[r["used_by"], r["unit"], *_statistics(scenario.series[r["series"]].values), _source(scenario.series[r["series"]].source)]
                                     for r in series])

    _widths(sheet)
    sheet.column_dimensions["A"].width = 30


def _series_sheet(book, scenario, tr, used):
    series = series_rows(scenario, tr)
    if not series:
        return

    sheet = book.create_sheet(sheet_name(tr("report.scenario.series"), used))
    data = [scenario.series[r["series"]].values for r in series]
    _write_head(sheet, 1, [tr("excel.col.time"), *[f"{r['used_by']} [{r['unit']}]" for r in series]])

    start = scenario.time.start
    for number in range(max(len(values) for values in data)):
        sheet.cell(row=number + 2, column=1, value=start + timedelta(hours=number)).number_format = excel_date_format(tr)
        for column, values in enumerate(data, start=2):
            if number < len(values) and values[number] is not None:
                sheet.cell(row=number + 2, column=column, value=values[number])
    sheet.freeze_panes = "B2"
    _widths(sheet, 14)
    sheet.column_dimensions["A"].width = 18


def _months_sheet(book, result, tr, used):
    """The energy of each month (kWh) of each carrier, one table below the other. No sheet if no carrier has two months
    or more."""

    data = {bus: monthly_data(bus, summary, tr) for bus, summary in result.buses.items()}
    data = {bus: found for bus, found in data.items() if found is not None and (found.supplies or found.demand is not None or found.uses)}
    if not data:
        return

    sheet = book.create_sheet(sheet_name(tr("excel.sheet.months"), used))
    row = 1
    for bus, months in data.items():
        lines = [*months.supplies, *([months.demand] if months.demand is not None else []), *months.uses]
        sheet.cell(row=row, column=1, value=bus_label(tr, bus)).font = SECTION_FONT
        _write_head(sheet, row + 1, [tr("excel.col.month"), *[f"{line.name} [kWh]" for line in lines]])
        for offset, month in enumerate(months.months):
            sheet.cell(row=row + 2 + offset, column=1, value=month.strftime(tr("result.chart.month_format")))
            for column, line in enumerate(lines, start=2):
                sheet.cell(row=row + 2 + offset, column=column, value=round(float(line.values[offset]), 3)).number_format = NUMBER_FORMATS[0]
        row += len(months.months) + 4

    sheet.freeze_panes = "B1"
    _widths(sheet, 14)
    sheet.column_dimensions["A"].width = 16


def build_workbook(scenario, result, tr=ENGLISH, today=None):
    """The Excel file of a scenario that was run (bytes)."""

    book, used = Workbook(), set()
    _summary(book, scenario, result, tr, today or date.today(), used)
    _table_sheet(book, tr("result.tab.costs"), result.cost_breakdown, tr, used, tr("result.no_costs"))
    _table_sheet(book, tr("result.tab.capacities"), result.capacities, tr, used, tr("result.no_capacities"))
    for bus, summary in result.buses.items():
        _bus_sheet(book, bus, summary, tr, used)
    _months_sheet(book, result, tr, used)
    _scenario_sheet(book, scenario, tr, used)
    _series_sheet(book, scenario, tr, used)

    for sheet in book.worksheets:
        _page(sheet)
    book.properties.title, book.properties.creator = scenario.name, "DecarbCompany, Hochschule Kempten"
    buffer = io.BytesIO()
    book.save(buffer)

    return buffer.getvalue()