"""Texts in English and German: the catalogs, the translator and the choice of the language."""

import ast
import json
import string
import tomllib
from pathlib import Path

import pytest

from backend.component_specs import INFO
from backend.i18n import (
    DEFAULT_LANGUAGE,
    ENGLISH,
    LANGUAGES,
    Msg,
    Translator,
    catalog,
    choose_language,
    detect_language,
)
from backend.i18n import translator as translator_module
from backend.system_templates import SYSTEM_TEMPLATES
from frontend_nicegui.draft import MAX_STEPS, MAX_YEAR, MIN_STEPS, MIN_YEAR, START_HINT, STEPS_HINT
from frontend_nicegui.markers import slug

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "backend" / "i18n"

EN, DE = catalog("en"), catalog("de")


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


# ---------------------------------------------------------------------------
# the catalogs
# ---------------------------------------------------------------------------

def test_the_languages():
    assert LANGUAGES == {"en": "English", "de": "Deutsch"}
    assert DEFAULT_LANGUAGE == "en"


def test_both_catalogs_have_exactly_the_same_keys():
    assert set(EN) == set(DE)
    assert len(EN) > 100


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_every_text_is_a_filled_in_string_without_stray_spaces(language):
    for key, text in catalog(language).items():
        assert isinstance(text, str) and text.strip(), f"{language}: {key}"
        assert text == text.strip(), f"{language}: {key}"
        assert "  " not in text, f"{language}: {key}"


def test_a_text_has_the_same_placeholders_in_both_languages():
    for key in EN:
        assert placeholders(EN[key]) == placeholders(DE[key]), key


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_the_braces_in_every_text_are_placeholders_that_can_be_filled_in(language):
    for key, text in catalog(language).items():
        text.format(**{name: "x" for name in placeholders(text)})


def test_every_plural_has_both_forms():
    for catalog_ in (EN, DE):
        ones = {key[: -len(".one")] for key in catalog_ if key.endswith(".one")}
        others = {key[: -len(".other")] for key in catalog_ if key.endswith(".other")}

        assert ones == others and ones


@pytest.mark.parametrize("language", list(LANGUAGES))
def test_the_keys_in_the_files_are_sorted_so_that_changes_are_easy_to_review(language):
    text = (FOLDER / f"{language}.json").read_text(encoding="utf-8")
    keys = list(json.loads(text))

    assert keys == sorted(keys)


def test_the_german_catalog_is_german_where_it_matters():
    assert DE["scenario.heading"] == "Ihr Szenario"
    assert DE["run.button"] == "Optimierung starten"
    assert "Sie" in DE["builder.intro"]                       # the formal "Sie" for business partners


def test_the_catalogs_are_part_of_the_installed_package():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    package_data = pyproject["tool"]["setuptools"]["package-data"]

    assert "*.json" in package_data["backend.i18n"]


# ---------------------------------------------------------------------------
# the names of components, groups and templates
# ---------------------------------------------------------------------------

def test_the_english_names_are_those_of_the_components():
    for key, info in INFO.items():
        assert EN[f"component.{key}.label"] == info.label, key
        assert EN[f"component.{key}.short"] == info.short_label, key


def test_every_component_has_a_german_name_and_a_short_name_that_fits_a_box():
    for key in INFO:
        assert DE[f"component.{key}.label"].strip()
        # German words are longer than English ones: a box of the diagram takes 14 characters
        assert 0 < len(DE[f"component.{key}.short"]) <= 14, key


def test_every_group_and_every_template_has_a_name_in_both_languages():
    for info in INFO.values():
        assert EN[f"group.{slug(info.group)}"] == info.group
        assert DE[f"group.{slug(info.group)}"]

    for name in SYSTEM_TEMPLATES:
        assert EN[f"template.{slug(name)}"] == name
        assert DE[f"template.{slug(name)}"]


# ---------------------------------------------------------------------------
# the translator
# ---------------------------------------------------------------------------

def test_a_text_is_looked_up_and_filled_in():
    assert Translator("en")("run.failed", reason="no solution") == (
        "The optimization could not be completed: no solution")
    assert Translator("de")("run.failed", reason="no solution") == (
        "Die Optimierung konnte nicht abgeschlossen werden: no solution")


def test_an_unknown_language_gets_english():
    assert Translator("fr")("scenario.heading") == "Your scenario"
    assert Translator("fr").language == "en"
    assert Translator(None).language == "en"


def test_a_key_that_is_missing_in_german_shows_the_english_text(monkeypatch):
    def fake(language):
        return {"only.english": "English text"} if language == "en" else {}

    monkeypatch.setattr(translator_module, "catalog", fake)

    assert Translator("de")("only.english") == "English text"
    assert Translator("de").has("only.english")


def test_a_key_that_is_missing_everywhere_shows_the_key_so_that_the_gap_is_seen(monkeypatch):
    monkeypatch.setattr(translator_module, "catalog", lambda language: {})

    assert Translator("de")("no.such.key") == "no.such.key"
    assert not Translator("de").has("no.such.key")


def test_a_placeholder_that_is_not_given_is_an_error_and_not_silently_empty():
    with pytest.raises(KeyError):
        ENGLISH("run.failed")


@pytest.mark.parametrize("language, count, expected", [
    ("en", 1, "1 component"), ("en", 0, "0 components"), ("en", 5, "5 components"),
    ("de", 1, "1 Komponente"), ("de", 0, "0 Komponenten"), ("de", 13, "13 Komponenten"),
])
def test_the_form_depends_on_the_number(language, count, expected):
    assert Translator(language).plural("builder.count", count) == expected


def test_a_plural_can_have_more_parameters():
    assert ENGLISH.plural("period.days", 1.5, days="1.5") == "1.5 days"
    assert ENGLISH.plural("period.days", 1, days="1") == "1 day"


def test_a_message_is_worded_in_the_language_of_the_reader():
    msg = Msg("run.failed", reason="no solution")

    assert Translator("de").message(msg).startswith("Die Optimierung konnte nicht")
    assert ENGLISH.message(msg).startswith("The optimization could not")


def test_a_text_of_its_own_is_used_for_its_owner_and_the_general_text_for_everybody_else():
    english = ENGLISH

    assert english.own("field.costs.variable_costs.label", "grid") == "Electricity price"
    assert english.own("field.costs.variable_costs.label", "gas_import") == "Gas price"
    assert english.own("field.costs.variable_costs.label", "pv") == "Variable costs"
    assert english.own("field.costs.variable_costs.label", None) == "Variable costs"
    assert Translator("de").own("field.costs.variable_costs.label", "grid") == "Strompreis"


def test_a_decimal_number_in_a_message_is_written_the_way_of_the_language():
    msg = Msg("form.hint.range", min=0.5, max=100.0)

    assert ENGLISH.message(msg) == "Enter a number from 0.5 to 100."
    assert Translator("de").message(msg) == "Geben Sie eine Zahl von 0,5 bis 100 ein."


def test_texts_and_whole_numbers_in_a_message_stay_as_they_are():
    assert ENGLISH.message(Msg("run.failed", reason="took 1.5 s")) == (
        "The optimization could not be completed: took 1.5 s")
    assert Translator("de").message(Msg("hint.steps", min=1, max="8.784")) == (
        "Geben Sie eine ganze Zahl von 1 bis 8.784 ein.")


def test_messages_can_be_compared():
    assert Msg("a", x=1) == Msg("a", x=1)
    assert Msg("a", x=1) != Msg("a", x=2) and Msg("a") != Msg("b")
    assert "run.failed" in repr(Msg("run.failed", reason="x"))


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("language, value, expected", [
    ("en", 12.5, "12.5"), ("de", 12.5, "12,5"), ("en", 60.0, "60"), ("de", 60.0, "60"),
    ("de", 0.25, "0,25"), ("en", 1 / 3, "0.333333"),
])
def test_numbers_have_a_decimal_point_or_comma(language, value, expected):
    assert Translator(language).number(value) == expected


def test_a_number_can_be_shortened_to_a_few_significant_digits():
    assert ENGLISH.number(0.000011416, significant=4) == "1.142e-05"
    assert Translator("de").number(3.14159, significant=3) == "3,14"


@pytest.mark.parametrize("language, expected", [("en", "8,784"), ("de", "8.784")])
def test_whole_numbers_have_a_thousands_separator(language, expected):
    assert Translator(language).integer(8784) == expected


def test_a_number_written_the_english_way_can_be_swapped():
    assert Translator("de").localize("1,234.5 kW") == "1.234,5 kW"
    assert ENGLISH.localize("1,234.5 kW") == "1,234.5 kW"


# ---------------------------------------------------------------------------
# the language of a visitor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("header, expected", [
    ("de-DE,de;q=0.9,en;q=0.8", "de"),
    ("de", "de"),
    ("en-US,en;q=0.9", "en"),
    ("fr-FR,fr;q=0.9", "en"),                       # not offered: the default
    ("fr-FR,fr;q=0.9,de;q=0.5", "de"),              # the best one that is offered
    ("en;q=0.5, de;q=0.9", "de"),
    ("en;q=0.9, de;q=0.9", "en"),                   # same quality: the one named first
    ("de;q=0, en", "en"),                           # q=0 means 'not acceptable'
    ("*", "en"),
    ("", "en"),
    (None, "en"),
    ("de;q=abc", "en"),                             # a broken quality is not trusted
    ("DE-at", "de"),
])
def test_the_language_of_the_browser(header, expected):
    assert detect_language(header) == expected


@pytest.mark.parametrize("requested, header, expected", [
    ("de", "en-US", "de"),                          # the link wins
    ("en", "de-DE", "en"),
    ("xx", "de-DE", "de"),                          # an unknown request is ignored
    (None, "de-DE", "de"),
    (None, None, "en"),
    ("", "", "en"),
])
def test_the_link_wins_over_the_browser(requested, header, expected):
    assert choose_language(requested, header) == expected


# ---------------------------------------------------------------------------
# the code and the catalogs fit together
# ---------------------------------------------------------------------------

SOURCES = sorted((ROOT / "backend").rglob("*.py")) + sorted((ROOT / "frontend_nicegui").rglob("*.py"))

# keys that are built from a name in the code (component.<key>.label, group.<slug>, ...)
DYNAMIC_FAMILIES = ("component.", "group.", "template.", "row.mode.", "block.", "field.", "series.help.", "series.mode.constant@")


def literal_keys_in_calls():
    """The keys that are written out in calls such as tr("key"), tr.plural("key"), Msg("key")."""

    keys, plural_keys = [], []

    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            function = node.func

            def literal(position):
                if len(node.args) > position:
                    argument = node.args[position]
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        return argument.value

            if isinstance(function, ast.Name) and function.id in ("tr", "Msg", "ScenarioFileError") and literal(0):
                keys.append((path.name, literal(0)))
            elif isinstance(function, ast.Attribute) and function.attr == "plural" and literal(0):
                plural_keys.append((path.name, literal(0)))
            # the code of a finding: coded("error", "code", ...) or, in the system check, error("code", ...)
            elif isinstance(function, ast.Name) and function.id == "coded" and literal(1):
                keys.append((path.name, f"check.{literal(1)}"))
            elif (isinstance(function, ast.Name) and function.id in ("error", "warning")
                  and path.name == "system_check.py" and literal(0)):
                keys.append((path.name, f"check.{literal(0)}"))
            # the code of a message about a file: TimeSeriesFileError("code", ...) or Notice("level", "code", ...)
            elif isinstance(function, ast.Name) and function.id == "TimeSeriesFileError" and literal(0):
                keys.append((path.name, f"import.{literal(0)}"))
            elif isinstance(function, ast.Name) and function.id == "Notice" and literal(1):
                keys.append((path.name, f"import.{literal(1)}"))

    return keys, plural_keys


def every_string_in_the_sources():
    found = set()

    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)

    return found


def test_the_code_asks_for_texts_that_exist():
    keys, plural_keys = literal_keys_in_calls()

    assert keys and plural_keys                    # the scan finds the calls at all
    for place, key in keys:
        assert key in EN or f"{key}.one" in EN, f"{place}: no text '{key}'"
    for place, key in plural_keys:
        assert f"{key}.one" in EN and f"{key}.other" in EN, f"{place}: no plural '{key}'"


def test_every_text_in_the_catalog_is_used_by_the_code():
    strings = every_string_in_the_sources() | {key for _, key in literal_keys_in_calls()[0]}
    unused = []

    for key in EN:
        base = key.rsplit(".", 1)[0] if key.endswith((".one", ".other")) else key
        if key.startswith(DYNAMIC_FAMILIES):
            continue
        if key in strings or base in strings:
            continue
        if key.startswith(("check.", "import.")) and key.split(".")[1] in strings:
            continue                  # the code of a message is also written in tables and conditions, not only in the call
        unused.append(key)

    assert unused == [], f"texts nobody asks for: {unused}"

def test_the_hints_of_the_draft_are_the_english_texts_of_the_catalog():
    assert STEPS_HINT == ENGLISH("hint.steps", min=MIN_STEPS, max=ENGLISH.integer(MAX_STEPS))
    assert START_HINT == ENGLISH("hint.start", first=MIN_YEAR, last=MAX_YEAR)