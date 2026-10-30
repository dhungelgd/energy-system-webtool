"""The forms of the components: what they show and what an input does (no NiceGUI needed)."""

import random

import pytest

from backend.blocks import BLOCKS
from backend.component_specs import FieldSpec
from backend.i18n import ENGLISH, Msg, Translator, catalog
from backend.scenario_v2 import Component
from backend.templates import new_component
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.forms import (
    FORMS,
    form_blocks,
    form_fields,
    has_form,
    problem,
    range_hint,
    sections,
    set_value,
    spec_of,
)

DE = Translator("de")
EN_CATALOG, DE_CATALOG = catalog("en"), catalog("de")

INVEST_KEYS = ["mode", "maximum", "capex", "opex", "lifetime", "interest_rate"]


def pv():
    return new_component("pv")


def shown(component, tr=ENGLISH):
    return [f.key for f in form_fields(component, "capacity", tr)]


def field_of(component, key, tr=ENGLISH):
    return next(f for f in form_fields(component, "capacity", tr) if f.key == key)


def invest(component):
    set_value(component, "capacity", "mode", "invest")
    return component


# ---------------------------------------------------------------------------
# which components have a form
# ---------------------------------------------------------------------------

def test_the_pv_system_has_a_form_for_its_size():
    assert FORMS == {"pv": ("capacity",)}
    assert has_form(pv()) and form_blocks(pv()) == ("capacity",)


def test_a_component_without_a_form_has_no_blocks_to_draw():
    assert not has_form(new_component("demand")) and form_blocks(new_component("demand")) == ()


# ---------------------------------------------------------------------------
# which settings are shown
# ---------------------------------------------------------------------------

def test_with_a_fixed_size_the_choice_and_the_size_are_shown():
    assert shown(pv()) == ["mode", "capacity"]


def test_when_the_optimizer_chooses_the_size_the_investment_settings_are_shown_instead():
    assert shown(invest(pv())) == INVEST_KEYS


def test_going_back_to_a_fixed_size_hides_the_investment_settings_again():
    component = invest(pv())

    set_value(component, "capacity", "mode", "fixed")

    assert shown(component) == ["mode", "capacity"]


def test_what_is_hidden_stays_stored():
    component = pv()
    set_value(component, "capacity", "capacity", 60)
    invest(component)
    set_value(component, "capacity", "capex", 999)

    set_value(component, "capacity", "mode", "fixed")

    assert component.blocks["capacity"]["capex"] == 999.0 and field_of(component, "capacity").value == 60.0


def test_a_component_without_a_choice_is_shown_with_the_default_choice():
    component = Component(id="x", name="X", template="pv", kind="source",
                          connections=[{"carrier": "electricity", "direction": "out"}], blocks={"capacity": {}})

    assert shown(component) == ["mode", "capacity"]
    assert field_of(component, "mode").value == "fixed"


def test_a_number_that_was_not_filled_in_is_shown_empty_and_not_as_the_default():
    component = Component(id="x", name="X", template="pv", kind="source",
                          connections=[{"carrier": "electricity", "direction": "out"}],
                          blocks={"capacity": {"mode": "invest"}})

    assert field_of(component, "capex").value is None


# ---------------------------------------------------------------------------
# what a setting looks like
# ---------------------------------------------------------------------------

def test_a_number_with_a_unit_and_a_range():
    capex = field_of(invest(pv()), "capex")

    assert (capex.label, capex.unit, capex.kind) == ("Investment cost", "€ per kW", "number")
    assert (capex.value, capex.minimum, capex.maximum, capex.step) == (1200.0, 0.0, None, 50.0)
    assert capex.section == "investment" and "quote" in capex.help
    assert capex.hint == Msg("form.hint.min", min=0.0)


def test_a_percentage_is_shown_as_a_percentage_from_0_to_100():
    opex = field_of(invest(pv()), "opex")

    assert opex.unit == "% of the investment per year" and opex.value == 2.0
    assert (opex.minimum, opex.maximum) == (0.0, 100.0)
    assert opex.hint == Msg("form.hint.range", min=0.0, max=100.0)


def test_every_setting_with_a_percentage_has_the_range_0_to_100():
    percentages = [(name, f.key) for name, block in BLOCKS.items() for f in block.fields if f.unit.startswith("%")]

    assert len(percentages) == 7                  # a new one should be looked at: is its range 0 to 100?
    for name, key in percentages:
        spec = spec_of(name, key)
        assert (spec.minimum, spec.maximum) == (0, 100), f"{name}.{key}"


def test_a_choice_has_its_options_worded_for_the_reader():
    mode = field_of(pv(), "mode")

    assert mode.kind == "choice" and mode.value == "fixed" and mode.hint is None
    assert mode.options == {"fixed": "I enter a fixed size", "invest": "The optimizer chooses the size"}


def test_the_texts_are_in_the_language_of_the_reader():
    capex = field_of(invest(pv()), "capex", DE)
    mode = field_of(pv(), "mode", DE)

    assert (capex.label, capex.unit) == ("Investitionskosten", "€ pro kW")
    assert "Angebot" in capex.help
    assert mode.options == {"fixed": "Ich gebe eine feste Größe ein", "invest": "Der Optimierer wählt die Größe"}
    assert field_of(invest(pv()), "lifetime", DE).unit == "Jahre"


def test_a_setting_without_a_unit_has_an_empty_unit():
    assert field_of(pv(), "mode").unit == ""


def test_the_sections_group_the_settings_and_only_the_basic_one_has_no_title():
    grouped = sections(form_fields(invest(pv()), "capacity"))

    assert [(name, title, [f.key for f in group]) for name, title, group in grouped] == [
        ("basic", None, ["mode"]),
        ("investment", "Investment", ["maximum", "capex", "opex", "lifetime", "interest_rate"]),
    ]
    assert sections(form_fields(invest(pv()), "capacity", DE), DE)[1][1] == "Investition"


def test_a_section_without_settings_is_left_out():
    assert [name for name, _, _ in sections(form_fields(pv(), "capacity"))] == ["basic"]


# ---------------------------------------------------------------------------
# what an input does
# ---------------------------------------------------------------------------

def test_a_number_is_stored_as_a_float():
    component = pv()

    assert set_value(component, "capacity", "capacity", 50) is None

    assert component.blocks["capacity"]["capacity"] == 50.0
    assert isinstance(component.blocks["capacity"]["capacity"], float)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_an_empty_input_means_not_filled_in_and_removes_the_value(raw):
    component = invest(pv())

    assert set_value(component, "capacity", "capex", raw) is None

    assert "capex" not in component.blocks["capacity"]


def test_a_number_written_as_text_is_accepted():
    component = pv()

    assert set_value(component, "capacity", "capacity", " 12.5 ") is None

    assert component.blocks["capacity"]["capacity"] == 12.5


@pytest.mark.parametrize("raw", [0, 0.0, 100, 100.0])
def test_the_limits_of_a_range_themselves_fit(raw):
    assert set_value(invest(pv()), "capacity", "interest_rate", raw) is None


@pytest.mark.parametrize("key, raw", [
    ("interest_rate", -0.1), ("interest_rate", 100.1), ("opex", 101), ("lifetime", 0.5), ("lifetime", 101),
    ("capex", -1), ("maximum", -5),
])
def test_a_number_outside_the_range_is_refused_with_a_message_and_not_stored(key, raw):
    component = invest(pv())
    before = dict(component.blocks["capacity"])

    found = set_value(component, "capacity", key, raw)

    assert isinstance(found, Msg) and found.key.startswith("form.hint.")
    assert component.blocks["capacity"] == before


@pytest.mark.parametrize("raw", ["abc", "1,5,5", True, False, float("nan"), float("inf"), float("-inf"), [1], {}])
def test_something_that_is_not_a_number_is_refused_and_not_stored(raw):
    component = pv()
    before = dict(component.blocks["capacity"])

    found = set_value(component, "capacity", "capacity", raw)

    assert found == Msg("form.hint.number")
    assert component.blocks["capacity"] == before


def test_the_message_names_the_range_in_the_language_of_the_reader():
    found = problem("capacity", "interest_rate", 150)

    assert ENGLISH.message(found) == "Enter a number from 0 to 100."
    assert DE.message(found) == "Geben Sie eine Zahl von 0 bis 100 ein."
    assert ENGLISH.message(problem("capacity", "capex", -1)) == "Enter a number of at least 0."
    assert DE.message(problem("capacity", "capacity", "x")) == "Geben Sie eine Zahl ein."


def test_the_bounds_are_written_with_a_decimal_comma_in_german():
    spec = FieldSpec(key="x", label="X", kind="number", minimum=0.5, maximum=2.5)

    assert ENGLISH.message(range_hint(spec)) == "Enter a number from 0.5 to 2.5."
    assert DE.message(range_hint(spec)) == "Geben Sie eine Zahl von 0,5 bis 2,5 ein."


def test_the_hint_depends_on_which_bounds_there_are():
    only_max = FieldSpec(key="x", label="X", kind="number", maximum=5)
    none = FieldSpec(key="y", label="Y", kind="number")

    assert range_hint(only_max) == Msg("form.hint.max", max=5.0)
    assert range_hint(none) == Msg("form.hint.number")


def test_checking_an_input_does_not_store_it():
    component = pv()

    assert problem("capacity", "capacity", 50) is None

    assert "capacity" not in component.blocks["capacity"]


def test_a_choice_is_stored_and_changes_what_is_shown():
    component = pv()

    assert set_value(component, "capacity", "mode", "invest") is None

    assert component.blocks["capacity"]["mode"] == "invest" and shown(component) == INVEST_KEYS


def test_a_choice_that_is_not_an_option_cannot_happen_and_is_not_stored():
    component = pv()

    with pytest.raises(ValueError, match="not one of the options"):
        set_value(component, "capacity", "mode", "dunno")

    assert component.blocks["capacity"]["mode"] == "fixed"


def test_a_setting_that_does_not_exist_is_an_error_of_the_program():
    with pytest.raises(KeyError, match="no setting 'colour'"):
        set_value(pv(), "capacity", "colour", 1)


def test_the_block_is_created_if_the_component_does_not_have_it_yet():
    component = Component(id="x", name="X", template="pv", kind="source",
                          connections=[{"carrier": "electricity", "direction": "out"}], blocks={})

    set_value(component, "capacity", "capacity", 5)

    assert component.blocks == {"capacity": {"capacity": 5.0}}


# ---------------------------------------------------------------------------
# with the draft: the check answers what was typed, and the scenario stays valid
# ---------------------------------------------------------------------------

def draft_with_pv():
    draft = ScenarioDraft()
    draft.apply_template("PV system")
    return draft


def messages(draft):
    return [finding.message for finding in draft.findings()]


def test_a_size_that_is_typed_in_answers_the_check():
    draft = draft_with_pv()
    assert any("fixed mode needs a capacity" in m for m in messages(draft))

    set_value(draft.component("pv"), "capacity", "capacity", 50)

    assert not any("fixed mode needs a capacity" in m for m in messages(draft))


def test_an_investment_setting_that_is_cleared_is_asked_for_by_the_check():
    draft = draft_with_pv()
    component = draft.component("pv")
    invest(component)
    assert not any("invest mode needs" in m for m in messages(draft))

    set_value(component, "capacity", "capex", None)

    assert any("invest mode needs values for capex" in m for m in messages(draft))


def test_no_maximum_is_fine_it_means_no_limit():
    draft = draft_with_pv()
    invest(draft.component("pv"))

    assert not any("maximum" in m for m in messages(draft))


def test_whatever_is_typed_in_the_draft_stays_a_valid_scenario():
    rng = random.Random(7)
    draft = draft_with_pv()
    component = draft.component("pv")
    wild = [None, "", " ", "abc", "1e3", "-5", 0, 1, -1, 50, 100, 101, 1e12, -1e12, 0.5, True, False,
            float("nan"), float("inf"), "12.5", [], {}, 25.0]
    keys = ["mode", "capacity", "maximum", "capex", "opex", "lifetime", "interest_rate"]

    for _ in range(3000):
        key = rng.choice(keys)
        raw = rng.choice(["fixed", "invest", "dunno"]) if key == "mode" else rng.choice(wild)
        try:
            set_value(component, "capacity", key, raw)
        except ValueError:
            assert key == "mode" and raw == "dunno"
        draft.scenario()                      # must never raise
        draft.findings()


# ---------------------------------------------------------------------------
# the texts of every block, in both languages
# ---------------------------------------------------------------------------

def test_the_english_texts_of_the_catalog_are_those_of_the_block_catalog():
    for name, block in BLOCKS.items():
        assert EN_CATALOG[f"block.{name}.label"] == block.label
        assert EN_CATALOG[f"block.{name}.help"] == block.help
        for spec in block.fields:
            base = f"field.{name}.{spec.key}"
            assert EN_CATALOG[f"{base}.label"] == spec.label
            assert EN_CATALOG[f"{base}.help"] == spec.help
            assert (f"{base}.unit" in EN_CATALOG) == bool(spec.unit)
            if spec.unit:
                assert EN_CATALOG[f"{base}.unit"] == spec.unit
            for option in spec.options:
                assert EN_CATALOG[f"{base}.option.{option}"] == spec.option_labels[option]


def test_every_text_of_the_block_catalog_has_a_german_text():
    for name, block in BLOCKS.items():
        keys = [f"block.{name}.label", f"block.{name}.help"]
        for spec in block.fields:
            base = f"field.{name}.{spec.key}"
            keys += [f"{base}.label", f"{base}.help"]
            keys += [f"{base}.unit"] if spec.unit else []
            keys += [f"{base}.option.{option}" for option in spec.options]

        for key in keys:
            assert DE_CATALOG[key].strip(), key


@pytest.mark.parametrize("block_name", [name for name, block in BLOCKS.items() if block.fields])
def test_the_form_of_every_block_can_be_made_in_both_languages(block_name):
    kind = "sink" if block_name == "demand" else "source"
    component = Component(id="x", name="X", template=None, kind=kind,
                          connections=[{"carrier": "electricity", "direction": "in" if kind == "sink" else "out"}],
                          blocks={block_name: {}})

    english = form_fields(component, block_name, ENGLISH)
    german = form_fields(component, block_name, DE)

    assert english and len(english) == len(german)
    for en, de in zip(english, german):
        assert en.key == de.key and en.label and de.label and en.label != de.label
        assert not de.label.startswith("field.")          # a text that is missing would show its key