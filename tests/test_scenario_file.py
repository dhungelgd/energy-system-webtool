"""The file of a scenario that is saved from the page: what it holds and what it is called."""

import json

import pytest

from backend.scenario_v2 import ScenarioV2, SeriesData
from backend.series_input import slot_of
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.scenario_file import (
    DEFAULT_FILE_NAME,
    MAX_FILE_NAME_LENGTH,
    file_name_for,
    report_file_name,
    scenario_bytes,
)
from tests.test_draft_from_scenario import full_draft


@pytest.mark.parametrize("name, expected", [
    ("My PV system", "my_pv_system.json"),
    ("PV + Batterie, Größe 5", "pv_batterie_grosse_5.json"),
    ("Äpfel & Öl", "apfel_ol.json"),
    ("Straße", "strasse.json"),
    ("  spaced   out  ", "spaced_out.json"),
    ("pv-battery_2", "pv-battery_2.json"),
    ("UPPER Case", "upper_case.json"),
    ("Café Müller", "cafe_muller.json"),
])
def test_a_scenario_name_becomes_a_file_name_of_plain_letters_digits_and_signs(name, expected):
    assert file_name_for(name) == expected


@pytest.mark.parametrize("name", ["", None, "   ", "???", "+-+", "中文"])
def test_a_name_without_letters_or_digits_gives_the_default_file_name(name):
    assert file_name_for(name) == f"{DEFAULT_FILE_NAME}.json"


@pytest.mark.parametrize("name", ["../../etc/passwd", "..\\windows\\system32", "a/b\\c", "name.with.dots", "x:y*z?"])
def test_a_name_cannot_make_a_path_or_another_kind_of_file(name):
    result = file_name_for(name)

    assert result.endswith(".json") and result.count(".") == 1
    assert not any(sign in result for sign in "/\\:*?\"<>|") and not result.startswith((".", "-", "_"))


def test_a_long_name_is_cut_and_does_not_end_in_a_sign():
    result = file_name_for("a" * 59 + " very long name that goes on")

    assert len(result) <= MAX_FILE_NAME_LENGTH + len(".json") and result.endswith("a.json")
    assert not result.removesuffix(".json").endswith(("_", "-"))


def test_the_bytes_of_a_scenario_are_the_scenario_as_json_and_can_be_read_again():
    scenario = full_draft().scenario()

    content = scenario_bytes(scenario)

    assert isinstance(content, bytes)
    assert ScenarioV2.model_validate_json(content).model_dump() == scenario.model_dump()


def test_the_file_is_compact_and_keeps_umlauts_as_they_are():
    draft = ScenarioDraft(name="Größe äöü €", steps=24)
    draft.set("demand")

    content = scenario_bytes(draft.scenario())

    assert b"\n" not in content and "Größe äöü €".encode("utf-8") in content
    assert json.loads(content)["name"] == "Größe äöü €"


def test_a_year_of_series_is_light_enough_to_download():
    draft = ScenarioDraft(steps=8760)
    draft.apply_template("Full system")
    for component in draft.components():
        if slot_of(component) is not None:
            draft.set_series(component.id, SeriesData(values=[0.123456789 * (i % 97) for i in range(8760)]))

    assert len(scenario_bytes(draft.scenario())) < 1_500_000


@pytest.mark.parametrize("name, language, expected", [
    ("My PV system", "en", "my_pv_system_report.pdf"),
    ("Mein Betrieb, Größe 5", "de", "mein_betrieb_grosse_5_bericht.pdf"),
    ("", "en", "scenario_report.pdf"),
    ("???", "de", "scenario_bericht.pdf"),
    ("../../x", "en", "x_report.pdf"),
])
def test_the_report_is_named_after_the_scenario_with_a_word_in_the_language_of_the_reader(name, language, expected):
    assert report_file_name(name, language) == expected


def test_the_file_name_of_a_report_is_a_pdf_and_has_one_dot_only():
    result = report_file_name("name.with.dots " + "x" * 80, "en")

    assert result.endswith(".pdf") and result.count(".") == 1 and len(result) <= MAX_FILE_NAME_LENGTH + len("_report.pdf")