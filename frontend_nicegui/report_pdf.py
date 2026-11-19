"""The PDF of the report: the look of the DecarbCompany flyer (the logos of the partners at the top, a blue tag, a large
title, a blue band, cards, blue headings, a foot line with the page number) laid out with reportlab.

What is on the pages is decided in report_data.py, the charts are drawn in report_charts.py; this file only makes
the pages. The logos are one image (assets/report_logos.png); a report without that file has no logos and is
otherwise the same.
"""

import io
import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from backend.i18n import ENGLISH
from frontend_nicegui import report_data as data
from frontend_nicegui.report_charts import chart_png

LOGOS = Path(__file__).resolve().parent / "assets" / "report_logos.png"

BLUE = colors.HexColor("#005D9D")          # the bands and the heads of the tables (the blue of the flyer)
DARK = colors.HexColor("#004578")          # the title and the headings
MID = colors.HexColor("#1073AE")           # the values of the cards
LIGHT = colors.HexColor("#EAF3FA")         # the rows and the boxes
LINE = colors.HexColor("#C9DCEB")
TEXT = colors.HexColor("#1F2D3A")
GREY = colors.HexColor("#5B6B7B")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
BODY = PAGE_WIDTH - 2 * MARGIN
TOP = 32 * mm                              # room for the logos
BOTTOM = 20 * mm

FONT, FONT_BOLD = "ReportSans", "ReportSans-Bold"


def _register_fonts():
    """DejaVu Sans (it comes with matplotlib) has every sign that a text of ours can hold: umlauts, the euro sign ..."""

    if FONT in pdfmetrics.getRegisteredFontNames():
        return

    folder = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont(FONT, str(folder / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(folder / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)


def _styles():
    def style(name, **kwargs):
        kwargs.setdefault("fontName", FONT)
        kwargs.setdefault("textColor", TEXT)
        return ParagraphStyle(name, **kwargs)

    return {
        "tag": style("tag", fontName=FONT_BOLD, fontSize=8.5, leading=11, textColor=colors.white),
        "title": style("title", fontName=FONT_BOLD, fontSize=27, leading=31, textColor=DARK),
        "subtitle": style("subtitle", fontSize=12.5, leading=16, textColor=GREY),
        "fact_label": style("fact_label", fontSize=7.5, leading=10, textColor=colors.HexColor("#CBE3F5")),
        "fact_value": style("fact_value", fontName=FONT_BOLD, fontSize=10.5, leading=13, textColor=colors.white),
        "heading": style("heading", fontName=FONT_BOLD, fontSize=16, leading=20, textColor=DARK),
        "subheading": style("subheading", fontName=FONT_BOLD, fontSize=10.5, leading=14, textColor=DARK),
        "body": style("body", fontSize=9, leading=13),
        "small": style("small", fontSize=8, leading=11, textColor=GREY),
        "card_title": style("card_title", fontName=FONT_BOLD, fontSize=7.5, leading=10, textColor=DARK),
        "card_value": style("card_value", fontName=FONT_BOLD, fontSize=15, leading=19, textColor=MID),
        "card_note": style("card_note", fontSize=7, leading=9.5, textColor=GREY),
        "cell": style("cell", fontSize=7.8, leading=10),
        "cell_head": style("cell_head", fontName=FONT_BOLD, fontSize=7.8, leading=10, textColor=colors.white),
    }


def _p(text, style):
    return Paragraph(escape(str(text)), style)


# ---------------------------------------------------------------------------
# the parts of a page
# ---------------------------------------------------------------------------

def _cover(report, styles):
    """The tag, the title, the subtitle and the band with the facts: the top of the first page."""

    tag = Table([[_p(report.tag, styles["tag"])]], colWidths=[BODY * 0.66])
    tag.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    tag.hAlign = "LEFT"

    cells = [[[_p(label, styles["fact_label"]), _p(value, styles["fact_value"])] for label, value in report.facts]]
    widths = [BODY * 0.40, BODY * 0.28, BODY * 0.32][: len(report.facts)]
    widths[-1] += BODY - sum(widths)
    band = Table(cells, colWidths=widths)
    band.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))

    return [tag, Spacer(1, 7 * mm), _p(report.title, styles["title"]), Spacer(1, 1.5 * mm),
            _p(report.subtitle, styles["subtitle"]), Spacer(1, 6 * mm), band, Spacer(1, 4 * mm)]


def _heading(text, styles):
    """The heading of a section and its short blue rule; both stay with what follows (never alone at a page end)."""

    heading = _p(text, styles["heading"])
    heading.keepWithNext = 1
    rule = HRFlowable(width=14 * mm, thickness=2, color=BLUE, hAlign="LEFT", spaceBefore=1, spaceAfter=6)
    rule.keepWithNext = 1

    return [heading, rule]


def _cards(cards, styles, per_row=3):
    """Cards in rows of three, as the cards 01 02 03 of the flyer: a white box with a thin blue edge."""

    gap = 4 * mm
    width = (BODY - gap * (per_row - 1)) / per_row
    rows, boxes = [], []

    for start in range(0, len(cards), per_row):
        row, boxed = [], []
        chunk = cards[start:start + per_row]
        for number in range(per_row):
            if number:
                row.append("")
            if number < len(chunk):
                card = chunk[number]
                content = [_p(card.title.upper(), styles["card_title"]), Spacer(1, 1.5 * mm), _p(card.value, styles["card_value"])]
                if card.note:
                    content += [Spacer(1, 1 * mm), _p(card.note, styles["card_note"])]
                row.append(content)
                boxed.append(number * 2)
            else:
                row.append("")
        rows.append(row)
        boxes.append(boxed)

    table = Table(rows, colWidths=[width if column % 2 == 0 else gap for column in range(per_row * 2 - 1)])
    commands = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
    for row_number, boxed in enumerate(boxes):
        for column in boxed:
            commands += [
                ("BOX", (column, row_number), (column, row_number), 0.8, LINE),
                ("LINEBEFORE", (column, row_number), (column, row_number), 3, MID),
                ("LEFTPADDING", (column, row_number), (column, row_number), 9), ("RIGHTPADDING", (column, row_number), (column, row_number), 7),
                ("TOPPADDING", (column, row_number), (column, row_number), 7), ("BOTTOMPADDING", (column, row_number), (column, row_number), 8)]
        if row_number:
            commands.append(("TOPPADDING", (0, row_number), (-1, row_number), 4 * mm))
    table.setStyle(TableStyle(commands))

    return table


NUMBER = re.compile(r"^[-−+]?[\d.,'\u00a0 ]+( ?(%|€|kW|kWh|h))?$")


def _table(table, styles):
    """A table with a blue head and light rows; columns that hold only numbers are right aligned."""

    columns = len(table.columns)
    numeric = [all(NUMBER.match(str(row[i]).strip()) or not str(row[i]).strip() for row in table.rows) and bool(table.rows)
               for i in range(columns)]

    def cell(text, head, right):
        style = ParagraphStyle("c", parent=styles["cell_head" if head else "cell"], alignment=2 if right else 0)
        return _p(text, style)

    rows = [[cell(text, True, numeric[i]) for i, text in enumerate(table.columns)]]
    rows += [[cell(text, False, numeric[i]) for i, text in enumerate(row)] for row in table.rows]

    # a column is as wide as its longest text (between a minimum and a maximum), so that nothing breaks in the middle of a word
    longest = [min(max(max([len(str(table.columns[i]))] + [len(str(row[i])) for row in table.rows]), 10), 36) for i in range(columns)]
    widths = [BODY * length / sum(longest) for length in longest]
    grid = Table(rows, colWidths=widths, repeatRows=1)
    grid.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))

    return grid


def _note(text, styles):
    """A text with a blue bar at its side (the boxes 'Das Projekt auf einen Blick' of the flyer)."""

    box = Table([["", _p(text, styles["body"])]], colWidths=[3 * mm, BODY - 3 * mm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), BLUE), ("BACKGROUND", (1, 0), (1, 0), LIGHT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (1, 0), (1, 0), 9), ("RIGHTPADDING", (1, 0), (1, 0), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0)]))

    return box


def _image(png):
    width, height = ImageReader(io.BytesIO(png)).getSize()
    shown = BODY                                                      # all as wide as the text ...
    room = PAGE_HEIGHT - TOP - BOTTOM - 25 * mm                       # ... and never higher than a page (with its heading)
    if BODY * height / width > room:
        shown = room * width / height

    return Image(io.BytesIO(png), width=shown, height=shown * height / width, hAlign="LEFT")


def _units(section, styles, result, tr, make_chart):
    """The blocks of a section as units of flowables: (flowables, together). A unit that is 'together' (a chart with
    its title, a row of cards) is not split between two pages; a table may be, its head is repeated."""

    units = []
    for block in section.blocks:
        if isinstance(block, data.Paragraph):
            flowables = [_note(block.text, styles), Spacer(1, 2.5 * mm)] if block.style == "note" else [
                _p(block.text, styles[block.style]), Spacer(1, 2 * mm)]
            units.append((flowables, True))
        elif isinstance(block, data.Cards):
            units.append(([_cards(block.cards, styles), Spacer(1, 4 * mm)], True))
        elif isinstance(block, data.Table):
            title = []
            if block.title:
                subheading = _p(block.title, styles["subheading"])
                subheading.keepWithNext = 1
                title = [subheading, Spacer(1, 1.5 * mm)]
            units.append(([*title, _table(block.data, styles), Spacer(1, 4 * mm)], False))
        elif isinstance(block, data.ChartRef):
            png = make_chart(block, result, tr)
            if png is not None:
                title = [_p(block.title, styles["subheading"])] if block.title else []
                caption = [_p(block.note, styles["small"])] if block.note else []
                units.append(([*title, *caption, Spacer(1, 1.5 * mm), _image(png), Spacer(1, 4 * mm)], True))

    return units


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------

def _page_decor(report):
    logos = None
    if LOGOS.exists():
        width, height = ImageReader(str(LOGOS)).getSize()
        logos = (str(LOGOS), BODY, BODY * height / width)

    def decorate(canvas, document):
        canvas.saveState()
        if logos is not None:
            path, width, height = logos
            canvas.drawImage(path, MARGIN, PAGE_HEIGHT - 9 * mm - height, width=width, height=height, mask="auto")
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.8)
        canvas.line(MARGIN, 14 * mm, PAGE_WIDTH - MARGIN, 14 * mm)
        canvas.setFont(FONT, 7.2)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(PAGE_WIDTH / 2, 10 * mm, f"{report.footer} | {report.page_word} {canvas.getPageNumber()}")
        canvas.restoreState()

    return decorate


def render_pdf(report, result=None, tr=ENGLISH, make_chart=chart_png):
    """The bytes of the PDF of a report_data.Report. `make_chart(ref, result, tr)` gives the PNG of a chart (or None)."""

    _register_fonts()
    styles = _styles()
    buffer = io.BytesIO()

    document = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=TOP, bottomMargin=BOTTOM,
        title=report.title, author="DecarbCompany, Hochschule Kempten", subject=report.subtitle, creator="Energy System Web Tool",
    )
    document.addPageTemplates([PageTemplate(
        id="page", frames=[Frame(MARGIN, BOTTOM, BODY, PAGE_HEIGHT - TOP - BOTTOM, id="body", leftPadding=0, rightPadding=0,
                                 topPadding=0, bottomPadding=0)],
        onPage=_page_decor(report))])

    story = _cover(report, styles)
    for section in report.sections:
        story.append(PageBreak() if section.new_page else CondPageBreak(80 * mm if section.big else 45 * mm))
        story += _heading(section.heading, styles)
        for flowables, together in _units(section, styles, result, tr, make_chart):
            story += [KeepTogether(flowables)] if together else flowables
        story.append(Spacer(1, 4 * mm))

    document.build(story)

    return buffer.getvalue()


def build_pdf(scenario, result, tr=ENGLISH, today=None):
    """The PDF report of a scenario that was run (bytes): the page shows the same, in the same words."""

    return render_pdf(data.build_report(scenario, result, tr, today or date.today()), result, tr)