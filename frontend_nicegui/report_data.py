"""What the PDF report says: its sections, cards, tables and charts, as plain data.

No NiceGUI, no PDF and no drawing code in here, so it is easy to test. The report is made from the scenario that was
run and the result of the run, in the language of the reader, and it uses the same numbers and words as the page
(result_view.py, result_terms.py, scenario_view.py): nothing is calculated twice. The look is in report_pdf.py,
the charts are in report_charts.py.
"""

from dataclasses import dataclass, field
from datetime import date

from backend.i18n import ENGLISH
from frontend_nicegui.result_charts import ZERO_FLOW
from frontend_nicegui.result_terms import bus_label, table_for_display
from frontend_nicegui.result_view import (
    chosen_sizes,
    headline_cards,
    period_caption,
    solver_label,
    solver_text,
)
from frontend_nicegui.scenario_view import component_rows, describe_period, series_rows


@dataclass(frozen=True)
class Card:
    """A card: a small title, a large value and a line of explanation (an item of the optimised system, a key figure)."""

    title: str
    value: str
    note: str = ""
    color: str = ""                    # the colour of the component, if the card is about one


@dataclass(frozen=True)
class TableData:
    """A table of text: its column titles and its rows."""

    columns: list
    rows: list


@dataclass(frozen=True)
class ChartRef:
    """A chart that is drawn later (report_charts.py): of which kind, for which energy carrier, with which title."""

    kind: str                          # 'costs', 'flows', 'monthly' or 'duration'
    title: str
    bus: str = ""
    note: str = ""


@dataclass(frozen=True)
class Paragraph:
    text: str
    style: str = "body"                # 'body', 'note' (with a bar at its side) or 'small' (grey)


@dataclass(frozen=True)
class Cards:
    cards: list


@dataclass(frozen=True)
class Table:
    title: str
    data: TableData


@dataclass(frozen=True)
class Section:
    heading: str
    blocks: list = field(default_factory=list)
    new_page: bool = False
    big: bool = False                  # starts on a new page unless there is much room left (an energy carrier with its charts)


@dataclass(frozen=True)
class Report:
    tag: str                           # the small band above the title
    title: str                         # the name of the scenario
    subtitle: str
    facts: list                        # [(label, value)] for the band under the title
    sections: list
    language: str
    footer: str                        # the text at the foot of every page (the page number is added)
    page_word: str


def date_text(day, tr=ENGLISH):
    """A date as the reader writes it (2026-11-19, in German 19.11.2026)."""

    return day.strftime(tr("result.chart.date_format"))


def display_table(table, tr):
    """A result table as a TableData (the words of the reader's language, the numbers as on the page)."""

    columns, rows = table_for_display(table, tr)

    return TableData(
        columns=[column["label"] for column in columns],
        rows=[[row.get(str(index), "") for index in range(len(columns))] for row in rows],
    )


def _chosen_section(result, tr):
    data = chosen_sizes(result, tr)
    blocks = []

    if not data["any"]:
        blocks.append(Paragraph(tr("result.chosen.none"), "small"))
    else:
        if data["built"]:
            blocks.append(Cards([
                Card(item["name"], item["size"], item["cost"], item["color"]) for item in data["built"]]))
        if data["not_built"]:
            blocks.append(Paragraph(tr("result.chosen.not_built", names=", ".join(data["not_built"])), "small"))

    return Section(tr("result.chosen.title"), [Paragraph(tr("result.chosen.hint"), "small"), *blocks])


def _figures_section(result, tr):
    cards = [Card(item["label"], item["value"], item["help"] or "") for item in headline_cards(result, tr)]

    return Section(tr("report.section.figures"), [Cards(cards)])


def _scenario_section(scenario, result, tr):
    blocks = [Paragraph(describe_period(scenario, tr), "body")]

    caption = period_caption(result, tr)
    if caption is not None:
        blocks.append(Paragraph(caption, "note"))

    components = component_rows(scenario, tr)
    blocks.append(Table(tr("report.scenario.components"), TableData(
        [tr("table.component"), tr("table.type"), tr("table.mode"), tr("table.size")],
        [[row["component"], row["type"], row["mode"], row["size"]] for row in components])))

    series = series_rows(scenario, tr)
    if series:
        def source(identifier):
            origin = scenario.series[identifier].source
            if origin is None or not origin.file:
                return ""
            return f"{origin.file}, {origin.column}" if origin.column else origin.file

        blocks.append(Table(tr("report.scenario.series"), TableData(
            [tr("table.used_by"), tr("table.unit"), tr("table.values"), tr("table.empty"), tr("table.min"),
             tr("table.max"), tr("report.col.source")],
            [[row["used_by"], row["unit"], str(row["values"]), str(row["empty"]), str(row["min"]), str(row["max"]),
              source(row["series"])] for row in series])))

    return Section(tr("report.section.scenario"), blocks)


def _costs_section(result, tr):
    if not result.cost_breakdown.rows:
        return Section(tr("result.section.costs"), [Paragraph(tr("result.no_costs"), "small")])

    return Section(tr("result.section.costs"), [
        ChartRef("costs", ""),                      # the heading of the section is its title
        Table("", display_table(result.cost_breakdown, tr)),
    ])


def _capacities_section(result, tr):
    table = result.capacities
    if not table.rows:
        return Section(tr("result.tab.capacities"), [Paragraph(tr("result.no_capacities"), "small")])

    blocks = [Table("", display_table(table, tr))]
    if "Mode" in table.columns and any(row[table.columns.index("Mode")] == "fixed (input)" for row in table.rows):
        blocks.append(Paragraph(tr("result.fixed_note"), "small"))

    return Section(tr("result.tab.capacities"), blocks)


def _bus_section(bus, summary, tr):
    flows = summary.flows
    blocks = []

    if flows is None or not flows.columns:
        blocks.append(Paragraph(tr("result.no_flows"), "small"))
    elif not (flows.to_frame(with_end_row=False).abs().max() > ZERO_FLOW).any():
        blocks.append(Paragraph(tr("result.nothing_flows"), "small"))
    else:
        blocks += [
            ChartRef("flows", tr("result.section.flows"), bus),
            ChartRef("monthly", tr("result.section.monthly"), bus, tr("result.monthly.hint")),
            ChartRef("duration", tr("result.section.duration"), bus, tr("result.duration.hint")),
        ]

    blocks += [Table(tr("result.supply"), display_table(summary.supply, tr)),
               Table(tr("result.use"), display_table(summary.use, tr))]

    return Section(bus_label(tr, bus), blocks, big=True)


def _notes_section(result, tr):
    return Section(tr("report.section.notes"), [
        Paragraph(solver_text(result, tr), "small"),
        Paragraph(tr("report.note.model"), "note"),
        Paragraph(tr("report.note.data"), "note"),
    ])


def build_report(scenario, result, tr=ENGLISH, today=None):
    """The report of a scenario that was run: what the page shows of its result, in the order a reader needs it."""

    today = today or date.today()
    cards = headline_cards(result, tr)

    facts = [(tr("report.fact.period"), describe_period(scenario, tr))]
    if cards:
        facts.append((cards[0]["label"], cards[0]["value"]))
    facts.append((tr("report.fact.solver"), solver_label(result.solver.name)))

    sections = [
        _chosen_section(result, tr),
        _figures_section(result, tr),
        _scenario_section(scenario, result, tr),
        _costs_section(result, tr),
        _capacities_section(result, tr),
        *[_bus_section(bus, summary, tr) for bus, summary in result.buses.items()],
        _notes_section(result, tr),
    ]

    return Report(
        tag=tr("report.tag", date=date_text(today, tr)),
        title=scenario.name,
        subtitle=tr("report.subtitle"),
        facts=facts,
        sections=sections,
        language=tr.language,
        footer=tr("report.footer"),
        page_word=tr("report.page"),
    )