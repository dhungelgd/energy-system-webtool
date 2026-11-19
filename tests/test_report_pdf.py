"""The PDF of the report: that it is made, what is on its pages, and that it still works when something is missing."""

import io
import time
from datetime import date

import pytest

pytest.importorskip("reportlab")
pypdf = pytest.importorskip("pypdf")

from backend.i18n import Translator  # noqa: E402
from backend.results import Table  # noqa: E402
from frontend_nicegui import report_pdf  # noqa: E402
from frontend_nicegui.report_data import build_report  # noqa: E402
from frontend_nicegui.report_pdf import build_pdf, render_pdf  # noqa: E402
from tests.report_samples import sample_result, sample_scenario  # noqa: E402

DE = Translator("de")
EN = Translator("en")
TODAY = date(2026, 11, 19)


def make(hours=24, language=EN, name="PV, battery and heat, test", **kwargs):
    return build_pdf(sample_scenario(hours, name), sample_result(hours, **kwargs), language, TODAY)


def pages(pdf):
    return pypdf.PdfReader(io.BytesIO(pdf)).pages


def text_of(pdf, number=None):
    found = pages(pdf)

    return found[number].extract_text() if number is not None else "\n".join(page.extract_text() for page in found)


def squash(text):
    """The text of a page without its line breaks (a long text is broken where the line ends)."""

    return " ".join(text.split())


# ---------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------

def test_the_report_is_a_pdf_of_a4_pages():
    pdf = make()

    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    first = pages(pdf)[0]
    assert (round(float(first.mediabox.width)), round(float(first.mediabox.height))) == (595, 842)


def test_the_document_has_the_name_of_the_scenario_as_its_title_and_the_project_as_its_author():
    info = pypdf.PdfReader(io.BytesIO(make(name="My plant, 2026"))).metadata

    assert info.title == "My plant, 2026" and "DecarbCompany" in info.author and info.subject == "Optimisation of the energy system"


def test_a_year_has_more_pages_than_a_day_because_of_the_charts():
    assert len(pages(make(24))) >= 2 and len(pages(make(8760))) >= len(pages(make(24)))


def test_the_first_page_has_the_tag_the_title_the_band_and_the_optimised_system():
    text = squash(text_of(make(), 0))

    for expected in ("RESULT REPORT · 2026-11-19", "PV, battery and heat, test", "Optimisation of the energy system",
                     "Period", "24 hourly steps (1 day) from 01.01.2021 00:00", "System cost (simulated period)", "55,353 €",
                     "Solver", "HiGHS", "The optimised system", "HEATING ROD", "2,471 kW (heat)", "PV", "41.7 kW", "Not built: Battery"):
        assert expected in text, expected


def test_the_document_has_the_fonts_of_the_text_with_every_sign_and_a_bold_one_for_the_headings():
    fonts = pages(make())[0]["/Resources"]["/Font"]
    names = [fonts[key].get_object()["/BaseFont"] for key in fonts]

    assert any(name.endswith("DejaVuSans") for name in names) and any(name.endswith("DejaVuSans-Bold") for name in names)


def test_the_key_figures_and_the_scenario_are_in_the_document():
    text = squash(text_of(make()))

    for expected in ("Key figures", "GRID IMPORT", "61.2 MWh", "Your scenario at a glance", "Components", "Electricity demand",
                     "Time series", "profiles.csv, DEMAND", "Where the system cost comes from", "Capacities", "Notes"):
        assert expected in text, expected


def test_every_energy_carrier_and_the_notes_are_in_the_document():
    text = squash(text_of(make(8760)))

    for expected in ("Electricity", "Energy flows", "Energy per month", "Duration curve", "Supply", "Use", "Heat", "Gas",
                     "Nothing flows through this energy carrier in this run.", "not a guarantee"):
        assert expected in text, expected


def test_every_page_has_the_foot_line_with_its_own_number():
    pdf = make(8760)

    for number, page in enumerate(pages(pdf), start=1):
        assert f"DecarbCompany | Hochschule Kempten | ILE & IEAT | Result report | Page {number}" in squash(page.extract_text())


def test_the_numbers_of_the_tables_are_those_of_the_page():
    text = squash(text_of(make()))

    assert "61,200" in text and "37,500" in text and "-8,400" in text and "Investment and fixed O&M" in text


# ---------------------------------------------------------------------------
# german
# ---------------------------------------------------------------------------

def test_a_german_report_is_in_german_with_the_signs_and_the_numbers_of_the_reader():
    text = squash(text_of(make(language=DE, name="Gesamtsystem, ein Jahr"), None))

    for expected in ("ERGEBNISBERICHT · 19.11.2026", "Optimierung des Energiesystems", "Zeitraum", "Systemkosten (simulierter Zeitraum)",
                     "Das optimierte System", "2.471 kW (Wärme)", "Nicht gebaut: Batteriespeicher", "Kennzahlen",
                     "Ihr Szenario auf einen Blick", "Größen", "Hinweise", "keine Garantie", "61.200"):
        assert expected in text, expected
    assert "Seite 1" in text and "Ergebnisbericht | Seite" in text


# ---------------------------------------------------------------------------
# when something is missing
# ---------------------------------------------------------------------------

def test_a_report_without_the_logos_is_made_too_and_has_less_in_it(monkeypatch):
    with_logos = len(pages(make())[0].images)
    monkeypatch.setattr(report_pdf, "LOGOS", report_pdf.LOGOS.with_name("not_there.png"))

    without = make()

    assert len(pages(without)[0].images) == with_logos - 1 and "RESULT REPORT" in text_of(without, 0)


def test_the_logos_are_on_every_page():
    pdf = make(8760)

    assert all(len(page.images) >= 1 for page in pages(pdf)) and report_pdf.LOGOS.exists()


def test_a_result_without_hourly_flows_has_no_pictures_of_the_flows():
    pdf = make(8760, with_flows=False)

    pictures = sum(len(page.images) for page in pages(pdf))
    assert pictures == len(pages(pdf)) + 1                                  # the logos on each page and the chart of the costs
    assert "This result has no hourly flows." in squash(text_of(pdf))


def test_a_chart_that_cannot_be_drawn_is_left_out_and_the_rest_stays():
    result = sample_result(24)
    report = build_report(sample_scenario(24), result, EN, TODAY)

    pdf = render_pdf(report, result, EN, make_chart=lambda ref, result, tr: None)

    assert "Where the system cost comes from" in text_of(pdf) and len(pages(pdf)) >= 2
    assert sum(len(page.images) for page in pages(pdf)) == len(pages(pdf))   # only the logos


def test_a_very_long_name_and_many_components_are_laid_out_without_an_error():
    pdf = make(name="A very long name of a scenario that goes on and on " * 3)

    assert pdf.startswith(b"%PDF") and "very long name" in squash(text_of(pdf, 0))


def test_a_long_table_goes_on_the_next_page_with_its_head_repeated():
    result = sample_result(24)
    result.cost_breakdown = Table(columns=result.cost_breakdown.columns,
                                  rows=[[f"Item {i}", "Energy purchase", 100.0 + i] for i in range(120)])

    pdf = build_pdf(sample_scenario(24), result, EN, TODAY)
    text = text_of(pdf)

    assert text.count("Category") >= 2 and "Item 119" in text                        # all 120 rows are in the table


def test_a_picture_that_is_taller_than_a_page_is_made_smaller_and_not_cut():
    from PIL import Image

    tall = io.BytesIO()
    Image.new("RGB", (1000, 6000), "white").save(tall, format="PNG")

    image = report_pdf._image(tall.getvalue())

    assert image.drawHeight < 842 and image.drawWidth < report_pdf.BODY and image.drawHeight / image.drawWidth == pytest.approx(6.0)


def test_a_special_sign_in_a_name_does_not_break_the_page():
    pdf = make(name="Café Müller & Söhne <b>GmbH</b> – 50 % Ökostrom (≥ 2 MW) ₂")

    text = squash(text_of(pdf, 0))
    assert "Café Müller & Söhne <b>GmbH</b>" in text and "Ökostrom" in text         # shown as it was typed, not read as markup


def test_the_report_of_a_year_is_made_in_a_few_seconds():
    started = time.time()
    pdf = make(8760)

    assert time.time() - started < 20 and 100_000 < len(pdf) < 1_500_000


def test_making_a_report_does_not_change_the_scenario_or_the_result():
    scenario, result = sample_scenario(24), sample_result(24)
    before = (scenario.model_dump(), result.model_dump())

    build_pdf(scenario, result, EN, TODAY)

    assert (scenario.model_dump(), result.model_dump()) == before