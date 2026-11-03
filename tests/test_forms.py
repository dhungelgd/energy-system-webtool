"""The forms of the components: what they show and what an input does (no NiceGUI needed)."""

import itertools
import random

import pytest

from backend.blocks import BLOCKS
from backend.component_specs import FieldSpec
from backend.i18n import ENGLISH, Msg, Translator, catalog
from backend.scenario_convert import engine_gaps, scenario_to_v1
from backend.scenario_v2 import Component
from backend.templates import TEMPLATES, new_component
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

def test_these_components_have_a_form_and_these_settings_are_in_it():
    assert FORMS == {
        "pv": {"capacity": None},
        "wind": {"capacity": None},
        "demand": {"demand": None},
        "heat_demand": {"demand": None},
        "grid": {"costs": ("variable_costs",)},
        "grid_feedin": {"costs": ("revenue",)},
        "gas_import": {"costs": ("variable_costs",)},
        "gas_boiler": {"conversion": ("outputs.heat.efficiency",), "capacity": None},
        "heating_rod": {"conversion": ("outputs.heat.efficiency",), "capacity": None},
        "chp": {"conversion": ("outputs.electricity.efficiency", "outputs.heat.efficiency"), "capacity": None},
        "heat_pump": {"conversion": ("outputs.heat.ratio",), "capacity": None},
        "battery": {"storage": ("c_rate", "efficiency_charge", "efficiency_discharge", "loss_rate"), "capacity": None},
        "heat_storage": {"storage": ("c_rate", "efficiency_charge", "efficiency_discharge", "loss_rate"),
                         "capacity": None},
    }


def test_every_component_that_can_be_chosen_has_a_form():
    from backend.component_specs import INFO

    assert set(FORMS) == set(INFO)


def test_the_blocks_of_a_form():
    assert has_form(pv()) and form_blocks(pv()) == ("capacity",)
    assert form_blocks(new_component("grid")) == ("costs",)
    assert form_blocks(new_component("demand")) == ("demand",)
    assert form_blocks(new_component("battery")) == ("storage", "capacity")        # how it works first, then its size
    assert form_blocks(new_component("chp")) == ("conversion", "capacity")


def test_a_component_that_is_not_one_of_the_templates_has_no_form():
    custom = Component(id="x", name="Electrolyser", template=None, kind="converter",
                       connections=[{"carrier": "electricity", "direction": "in"},
                                    {"carrier": "hydrogen", "direction": "out"}], blocks={})

    assert not has_form(custom) and form_blocks(custom) == ()


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
    assert range_hint(spec_of("capacity", "capex")) == Msg("form.hint.min", min=0.0)


def test_a_percentage_is_shown_as_a_percentage_from_0_to_100():
    opex = field_of(invest(pv()), "opex")

    assert opex.unit == "% of the investment per year" and opex.value == 2.0
    assert (opex.minimum, opex.maximum) == (0.0, 100.0)
    assert range_hint(spec_of("capacity", "opex")) == Msg("form.hint.range", min=0.0, max=100.0)


def test_every_setting_with_a_percentage_has_the_range_0_to_100():
    percentages = [(name, f.key) for name, block in BLOCKS.items() for f in block.fields if f.unit.startswith("%")]

    assert len(percentages) == 9                  # a new one should be looked at: is its range 0 to 100?
    for name, key in percentages:
        spec = spec_of(name, key)
        assert (spec.minimum, spec.maximum) == (0, 100), f"{name}.{key}"


def test_a_choice_has_its_options_worded_for_the_reader():
    mode = field_of(pv(), "mode")

    assert mode.kind == "choice" and mode.value == "fixed"
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


# ---------------------------------------------------------------------------
# the forms of the other components, with their own words
# ---------------------------------------------------------------------------

def fields_of(template, tr=ENGLISH):
    component = new_component(template)
    return {f.key: f for block in form_blocks(component) for f in form_fields(component, block, tr)}


def test_the_demand_asks_for_the_profile_and_the_annual_demand():
    fields = fields_of("demand")

    assert list(fields) == ["profile_type", "annual_demand"]
    assert fields["profile_type"].kind == "choice" and fields["profile_type"].value == "annual_share"
    assert (fields["annual_demand"].label, fields["annual_demand"].unit) == ("Annual electricity demand", "kWh per year")
    assert fields["annual_demand"].value == 30000.0
    assert range_hint(spec_of("demand", "annual_demand")) == Msg("form.hint.min", min=0.0)


def test_the_heat_demand_says_heat():
    fields = fields_of("heat_demand")

    assert fields["annual_demand"].label == "Annual heat demand" and fields["annual_demand"].value == 90000.0
    assert "heat" in fields["annual_demand"].help


def test_a_demand_that_is_given_in_kw_has_no_annual_demand():
    component = new_component("demand")

    set_value(component, "demand", "profile_type", "absolute")

    assert [f.key for f in form_fields(component, "demand")] == ["profile_type"]
    assert component.blocks["demand"]["annual_demand"] == 30000.0                       # hidden, not lost


def test_the_grid_asks_for_the_price_of_electricity_and_not_for_variable_costs():
    fields = fields_of("grid")

    assert list(fields) == ["variable_costs"]
    price = fields["variable_costs"]
    assert (price.label, price.unit, price.value) == ("Electricity price", "€ per kWh", 0.3)
    assert price.help == "What one kWh from the grid costs."
    assert price.minimum == 0 and price.step == 0.01


def test_the_feed_in_asks_for_the_tariff_and_the_gas_import_for_the_gas_price():
    assert [(f.label, f.value) for f in fields_of("grid_feedin").values()] == [("Feed-in tariff", 0.078)]
    assert list(fields_of("grid_feedin")) == ["revenue"]
    assert [(f.label, f.value) for f in fields_of("gas_import").values()] == [("Gas price", 0.1)]
    assert list(fields_of("gas_import")) == ["variable_costs"]


def test_a_component_only_shows_the_settings_of_its_block_that_the_engine_reads():
    assert [f.key for f in BLOCKS["costs"].fields] == ["variable_costs", "revenue"]       # the block has both ...
    assert "revenue" not in fields_of("grid") and "variable_costs" not in fields_of("grid_feedin")   # ... a form one


def test_the_german_words_of_these_forms():
    assert fields_of("grid", DE)["variable_costs"].label == "Strompreis"
    assert fields_of("grid", DE)["variable_costs"].unit == "€ pro kWh"
    assert fields_of("grid_feedin", DE)["revenue"].label == "Einspeisevergütung"
    assert fields_of("gas_import", DE)["variable_costs"].label == "Gaspreis"
    assert fields_of("demand", DE)["annual_demand"].label == "Jahresstrombedarf"
    assert fields_of("heat_demand", DE)["annual_demand"].label == "Jahreswärmebedarf"
    assert fields_of("demand", DE)["annual_demand"].unit == "kWh pro Jahr"


def test_the_wind_turbine_has_the_form_of_the_pv_system_with_its_own_help():
    wind, solar = fields_of("wind"), fields_of("pv")

    assert list(wind) == list(solar)
    assert wind["capacity"].help == "The rated power of the wind turbine."
    assert solar["capacity"].help == "The installed peak power of the plant."
    assert wind["capacity"].label == solar["capacity"].label == "Installed size"        # no words of its own: the general ones


def test_a_text_of_its_own_belongs_to_a_setting_that_the_form_of_that_component_shows():
    own = [key for key in EN_CATALOG if "@" in key and key.startswith("field.")]

    assert len(own) == 35                 # a new one belongs to a setting that the form shows
    for key in own:
        generic, template = key.split("@")
        _, block, rest = generic.split(".", 2)
        setting = rest.split(".option.")[0] if ".option." in rest else rest.rsplit(".", 1)[0]     # a setting can be a path
        shown = FORMS[template][block]
        assert generic in EN_CATALOG and key in DE_CATALOG, key
        assert shown is None or setting in shown, key


def test_the_help_of_the_size_choice_says_what_a_fixed_size_means_for_the_costs():
    help_text = field_of(pv(), "mode").help

    assert "the cost of the plant is not part of the system cost" in help_text
    assert "nicht Teil der Systemkosten" in field_of(pv(), "mode", DE).help


# ---------------------------------------------------------------------------
# the forms and the engine agree
# ---------------------------------------------------------------------------

SPECIAL = {                                   # read by the adapter, not through a plain link
    "demand": {("demand", "profile_type"), ("demand", "annual_demand")},
    "heat_demand": {("demand", "profile_type"), ("demand", "annual_demand")},
    "heat_pump": {("conversion", "outputs.heat.ratio")},          # the COP series comes with the upload
}


def read_by_the_engine(template):
    """The settings of a component that the adapter to the engine reads (the ones with a name of their own)."""

    plain = {(link.block, link.field) for link in TEMPLATES[template].links}

    return plain | SPECIAL.get(template, set())


def shown_in_some_mode(template):
    """Every setting that the form of a component shows for some choice of the choices."""

    component = new_component(template)
    seen = set()

    for block in form_blocks(component):
        choices = [spec for spec in BLOCKS[block].fields if spec.kind == "choice"]
        for picks in itertools.product(*[spec.options for spec in choices]):
            for spec, pick in zip(choices, picks):
                set_value(component, block, spec.key, pick)
            seen |= {(block, f.key) for f in form_fields(component, block)}

    return seen


@pytest.mark.parametrize("template", list(FORMS))
def test_a_form_shows_exactly_the_settings_that_the_engine_reads(template):
    # nothing the engine needs is hidden, and nothing is offered that the engine would not read
    assert shown_in_some_mode(template) == read_by_the_engine(template)


def test_whatever_the_forms_offer_the_engine_can_run():
    draft = ScenarioDraft()
    draft.apply_template("Full system")

    for template in FORMS:
        component = draft.component(template)
        offered = sorted(shown_in_some_mode(template))

        for block, key in offered:
            spec = spec_of(block, key)
            if spec.kind == "number":
                assert set_value(component, block, key, max(spec.minimum or 0, 1)) is None

        assert engine_gaps(draft.scenario()) == [], template
        for block, key in offered:
            spec = spec_of(block, key)
            for pick in spec.options:                              # every choice that is offered
                set_value(component, block, key, pick)
                assert engine_gaps(draft.scenario()) == [], (template, key, pick)


def test_what_is_typed_in_the_forms_reaches_the_settings_of_the_engine():
    draft = ScenarioDraft()
    draft.apply_template("Full system")
    for template, block, key, raw in [
        ("grid", "costs", "variable_costs", 0.35), ("grid_feedin", "costs", "revenue", 0.05),
        ("gas_import", "costs", "variable_costs", 0.12), ("demand", "demand", "annual_demand", 45000),
        ("heat_demand", "demand", "annual_demand", 100000), ("wind", "capacity", "capacity", 20),
        ("pv", "capacity", "capacity", 50),
        ("gas_boiler", "conversion", "outputs.heat.efficiency", 85), ("heating_rod", "conversion", "outputs.heat.efficiency", 98),
        ("chp", "conversion", "outputs.electricity.efficiency", 30), ("chp", "conversion", "outputs.heat.efficiency", 55),
        ("heat_pump", "conversion", "outputs.heat.ratio", 4.2),
        ("battery", "storage", "c_rate", 0.8), ("battery", "storage", "efficiency_charge", 90),
        ("heat_storage", "storage", "loss_rate", 0.2), ("battery", "capacity", "capacity", 40),
    ]:
        assert set_value(draft.component(template), block, key, raw) is None

    settings = scenario_to_v1(draft.scenario()).settings

    assert settings["grid"]["variable_costs"] == 0.35 and settings["grid_feedin"]["feedin_tariff"] == 0.05
    assert settings["gas_import"]["variable_costs"] == 0.12
    assert settings["demand"]["scaling_factor"] == 45000 and settings["heat_demand"]["scaling_factor"] == 100000
    assert (settings["wind"]["mode"], settings["wind"]["capacity"]) == ("fixed", 20)
    assert settings["pv"]["capacity"] == 50
    assert settings["gas_boiler"]["efficiency"] == 0.85 and settings["heating_rod"]["efficiency"] == 0.98
    assert (settings["chp"]["efficiency_el"], settings["chp"]["efficiency_th"]) == (0.30, 0.55)
    assert (settings["heat_pump"]["cop_mode"], settings["heat_pump"]["cop_value"]) == ("constant", 4.2)
    assert (settings["battery"]["c_rate"], settings["battery"]["efficiency_charge"]) == (0.8, 0.90)
    assert settings["heat_storage"]["loss_rate"] == 0.002 and settings["battery"]["capacity"] == 40


def test_a_demand_in_kw_reaches_the_engine_with_a_factor_of_1():
    draft = ScenarioDraft()
    draft.apply_template("Electricity only")

    set_value(draft.component("demand"), "demand", "profile_type", "absolute")

    assert scenario_to_v1(draft.scenario()).settings["demand"]["scaling_factor"] == 1.0


def test_a_feed_in_tariff_above_the_price_is_found_by_the_check_while_typing():
    draft = ScenarioDraft()
    draft.apply_template("PV system")
    assert not any(f.code == "feedin_above_price" for f in draft.findings())

    set_value(draft.component("grid_feedin"), "costs", "revenue", 0.5)

    found = [f for f in draft.findings() if f.code == "feedin_above_price"]
    assert found and "(0.5 €/kWh) is higher than the electricity price (0.3 €/kWh)" in found[0].message

    set_value(draft.component("grid"), "costs", "variable_costs", 0.6)

    assert not any(f.code == "feedin_above_price" for f in draft.findings())


def test_whatever_is_typed_into_any_form_stays_a_valid_scenario():
    rng = random.Random(11)
    draft = ScenarioDraft()
    draft.apply_template("Full system")
    wild = [None, "", "abc", "-5", 0, 1, -1, 0.05, 0.3, 50, 100, 101, 30000, 1e12, -1e12, True, False,
            float("nan"), float("inf"), "12.5", [], {}]
    targets = [(template, block, spec) for template in FORMS for block in form_blocks(new_component(template))
               for spec in BLOCKS[block].fields if FORMS[template][block] is None or spec.key in FORMS[template][block]]

    for _ in range(4000):
        template, block, spec = rng.choice(targets)
        raw = rng.choice(list(spec.options) + ["dunno"]) if spec.kind == "choice" else rng.choice(wild)
        try:
            set_value(draft.component(template), block, spec.key, raw)
        except ValueError:
            assert spec.kind == "choice" and raw == "dunno"
        draft.scenario()                                          # must never raise


# ---------------------------------------------------------------------------
# the converters and the storages
# ---------------------------------------------------------------------------

def test_the_boiler_and_the_heating_rod_ask_for_the_efficiency_and_the_size():
    boiler, rod = fields_of("gas_boiler"), fields_of("heating_rod")

    assert list(boiler) == ["outputs.heat.efficiency", "mode", "capacity"] == list(rod)
    efficiency = boiler["outputs.heat.efficiency"]
    assert (efficiency.label, efficiency.unit, efficiency.value) == ("Efficiency", "%", 90.0)
    assert efficiency.help == "The share of the gas energy that becomes heat."
    assert rod["outputs.heat.efficiency"].value == 99.0
    assert rod["outputs.heat.efficiency"].help == "The share of the electricity that becomes heat."
    assert boiler["capacity"].help == "The heat output of the boiler."
    assert rod["capacity"].help == "The heat output of the heating rod."


def test_the_chp_plant_asks_for_both_efficiencies_and_says_which_output_its_size_is():
    fields = fields_of("chp")

    assert list(fields) == ["outputs.electricity.efficiency", "outputs.heat.efficiency", "mode", "capacity"]
    assert (fields["outputs.electricity.efficiency"].label, fields["outputs.electricity.efficiency"].value) == (
        "Electrical efficiency", 35.0)
    assert (fields["outputs.heat.efficiency"].label, fields["outputs.heat.efficiency"].value) == (
        "Thermal efficiency", 50.0)
    assert fields["capacity"].help == "The electrical output of the CHP plant. Its heat output follows from the efficiencies."


def test_the_heat_pump_asks_for_the_cop():
    fields = fields_of("heat_pump")

    assert list(fields) == ["outputs.heat.ratio", "mode", "capacity"]
    cop = fields["outputs.heat.ratio"]
    assert (cop.label, cop.unit, cop.value) == ("COP", "kWh heat per kWh electricity", 3.5)
    assert range_hint(spec_of("conversion", "outputs.heat.ratio")) == Msg("form.hint.above", min=0.0)
    assert fields["capacity"].help == "The heat output of the heat pump."


def test_a_storage_is_measured_in_kwh_and_has_no_initial_charge_level_in_its_form():
    fields = fields_of("battery")

    assert list(fields) == ["c_rate", "efficiency_charge", "efficiency_discharge", "loss_rate", "mode", "capacity"]
    assert (fields["capacity"].label, fields["capacity"].unit) == ("Installed capacity", "kWh")
    assert fields["capacity"].help == "The energy that the battery can store."
    assert fields["efficiency_charge"].value == 95.0 and fields["loss_rate"].unit == "% per hour"
    assert fields_of("heat_storage")["capacity"].help == "The heat that the heat storage can hold."
    assert "initial_level" not in fields and "initial_level" not in fields_of("heat_storage")     # the engine ignores it


def test_the_investment_settings_of_a_storage_are_per_kwh():
    component = invest(new_component("battery"))
    fields = {f.key: f for block in form_blocks(component) for f in form_fields(component, block)}

    assert (fields["maximum"].label, fields["maximum"].unit) == ("Maximum capacity", "kWh")
    assert fields["capex"].unit == "€ per kWh"
    assert "divided by the capacity" in fields["capex"].help


def test_the_general_help_of_the_maximum_size_talks_about_space_and_the_pv_system_about_the_roof():
    assert "available space" in field_of(invest(new_component("wind")), "maximum").help
    assert "roof area" in field_of(invest(pv()), "maximum").help
    assert "Dachfläche" in field_of(invest(pv()), "maximum", DE).help


def test_the_german_words_of_the_converters_and_the_storages():
    chp = fields_of("chp", DE)
    battery = fields_of("battery", DE)

    assert chp["outputs.electricity.efficiency"].label == "Elektrischer Wirkungsgrad"
    assert chp["outputs.heat.efficiency"].label == "Thermischer Wirkungsgrad"
    assert fields_of("heat_pump", DE)["outputs.heat.ratio"].label == "Leistungszahl (COP)"
    assert fields_of("heat_pump", DE)["outputs.heat.ratio"].unit == "kWh Wärme pro kWh Strom"
    assert (battery["capacity"].label, battery["capacity"].unit) == ("Installierte Kapazität", "kWh")
    assert battery["efficiency_charge"].label == "Lade-Wirkungsgrad"
    assert fields_of("gas_boiler", DE)["capacity"].help == "Die Wärmeleistung des Kessels."


# ---------------------------------------------------------------------------
# a setting that is a path, and a minimum that is excluded
# ---------------------------------------------------------------------------

def boiler():
    return new_component("gas_boiler")


def test_a_setting_of_the_conversion_is_stored_where_the_conversion_keeps_it():
    component = boiler()

    assert set_value(component, "conversion", "outputs.heat.efficiency", 85) is None

    assert component.blocks["conversion"]["outputs"]["heat"]["efficiency"] == 85.0
    assert field_of_block(component, "conversion", "outputs.heat.efficiency").value == 85.0


def field_of_block(component, block, key, tr=ENGLISH):
    return next(f for f in form_fields(component, block, tr) if f.key == key)


def test_clearing_a_setting_of_the_conversion_removes_it_and_leaves_no_empty_dictionaries():
    component = boiler()

    set_value(component, "conversion", "outputs.heat.efficiency", None)

    assert component.blocks["conversion"] == {}


def test_clearing_one_of_two_efficiencies_keeps_the_other():
    component = new_component("chp")

    set_value(component, "conversion", "outputs.heat.efficiency", "")

    assert component.blocks["conversion"] == {"outputs": {"electricity": {"efficiency": 35.0}}}


def test_the_value_of_a_setting_that_is_not_there_is_empty():
    component = boiler()
    component.blocks["conversion"] = {}

    assert field_of_block(component, "conversion", "outputs.heat.efficiency").value is None


@pytest.mark.parametrize("raw", [0, 0.0, -1, 100.5])
def test_an_efficiency_of_0_or_above_100_is_refused(raw):
    component = boiler()

    found = set_value(component, "conversion", "outputs.heat.efficiency", raw)

    assert found == Msg("form.hint.above_range", min=0.0, max=100.0)
    assert component.blocks["conversion"]["outputs"]["heat"]["efficiency"] == 90.0


@pytest.mark.parametrize("raw", [0.1, 1, 100])
def test_an_efficiency_above_0_and_up_to_100_fits(raw):
    assert set_value(boiler(), "conversion", "outputs.heat.efficiency", raw) is None


def test_the_cop_must_be_above_0():
    component = new_component("heat_pump")

    assert set_value(component, "conversion", "outputs.heat.ratio", 0) == Msg("form.hint.above", min=0.0)
    assert set_value(component, "conversion", "outputs.heat.ratio", 0.1) is None
    assert set_value(component, "conversion", "outputs.heat.ratio", 7) is None


def test_the_messages_for_a_number_that_has_to_be_above_a_minimum():
    assert ENGLISH.message(Msg("form.hint.above_range", min=0.0, max=100.0)) == "Enter a number above 0 and at most 100."
    assert DE.message(Msg("form.hint.above_range", min=0.0, max=100.0)) == "Geben Sie eine Zahl über 0 und höchstens 100 ein."
    assert ENGLISH.message(Msg("form.hint.above", min=0.0)) == "Enter a number above 0."
    assert DE.message(Msg("form.hint.above", min=0.0)) == "Geben Sie eine Zahl über 0 ein."


def test_what_the_form_refuses_is_what_the_conversion_would_refuse():
    # the form never lets a value in that makes the component invalid for the scenario
    from backend.blocks import conversion_problems

    for raw in (0, 0.5, 50, 100, 100.5):
        component = boiler()
        refused = set_value(component, "conversion", "outputs.heat.efficiency", raw) is not None
        invalid = bool(conversion_problems(component.blocks["conversion"], {"heat"}, "x"))

        assert not invalid, raw                      # whatever is stored is valid
        assert refused == (raw in (0, 100.5)), raw


# ---------------------------------------------------------------------------
# what only a few settings together can get wrong
# ---------------------------------------------------------------------------

def test_the_two_efficiencies_of_the_chp_plant_cannot_add_up_to_more_than_100():
    component = new_component("chp")                                 # 35 and 50

    found = set_value(component, "conversion", "outputs.electricity.efficiency", 60)

    assert found == Msg("form.hint.efficiency_sum")
    assert component.blocks["conversion"]["outputs"]["electricity"]["efficiency"] == 35.0          # not stored
    assert set_value(component, "conversion", "outputs.electricity.efficiency", 50) is None       # 50 + 50 = 100 fits
    assert set_value(component, "conversion", "outputs.heat.efficiency", 51) == Msg("form.hint.efficiency_sum")


def test_the_sum_is_only_checked_when_the_component_is_known():
    assert problem("conversion", "outputs.electricity.efficiency", 60) is None
    assert problem("conversion", "outputs.electricity.efficiency", 60, new_component("chp")) == Msg(
        "form.hint.efficiency_sum")


def test_the_message_about_the_sum_in_both_languages():
    assert ENGLISH.message(Msg("form.hint.efficiency_sum")) == "The efficiencies together cannot be more than 100 %."
    assert DE.message(Msg("form.hint.efficiency_sum")) == "Die Wirkungsgrade zusammen dürfen nicht mehr als 100 % betragen."
    assert DE.message(Msg("form.hint.invalid")) == "Dieser Wert ist hier nicht möglich."


def test_clearing_an_efficiency_is_always_possible_and_found_by_the_check():
    draft = ScenarioDraft()
    draft.apply_template("Gas heating")

    set_value(draft.component("gas_boiler"), "conversion", "outputs.heat.efficiency", None)

    found = [f for f in draft.findings() if f.code == "value_missing"]
    assert [f.message for f in found] == ["Gas boiler: Efficiency is not filled in."]


def test_a_storage_efficiency_has_the_usual_range():
    component = new_component("battery")

    assert set_value(component, "storage", "efficiency_charge", 101) == Msg("form.hint.range", min=0.0, max=100.0)
    assert set_value(component, "storage", "efficiency_charge", 0) is None        # a storage that cannot be charged is not an error here


# ---------------------------------------------------------------------------
# a setting that a time series replaces
# ---------------------------------------------------------------------------

def test_the_price_of_the_grid_is_not_shown_while_the_grid_uses_a_series():
    from backend.scenario_v2 import SeriesData

    draft = ScenarioDraft()
    draft.apply_template("Electricity only")
    grid = draft.component("grid")
    assert [f.key for f in form_fields(grid, "costs")] == ["variable_costs"]

    draft.set_series("grid", SeriesData(values=[0.3, 0.2]))

    assert form_fields(grid, "costs") == []
    draft.clear_series("grid")
    assert [f.key for f in form_fields(grid, "costs")] == ["variable_costs"]


def test_the_cop_of_the_heat_pump_is_not_shown_while_the_heat_pump_uses_a_series_and_comes_back_with_its_value():
    from backend.scenario_v2 import SeriesData

    draft = ScenarioDraft()
    draft.apply_template("Heat pump + heating rod")
    pump = draft.component("heat_pump")
    set_value(pump, "conversion", "outputs.heat.ratio", 4.2)

    draft.set_series("heat_pump", SeriesData(values=[3.0, 3.5]))
    assert form_fields(pump, "conversion") == []

    draft.clear_series("heat_pump")
    assert [(f.key, f.value) for f in form_fields(pump, "conversion")] == [("outputs.heat.ratio", 4.2)]


def test_a_setting_that_no_series_replaces_is_always_shown():
    from backend.scenario_v2 import SeriesData

    draft = ScenarioDraft()
    draft.apply_template("PV system")
    draft.set_series("demand", SeriesData(values=[1.0]))

    assert [f.key for f in form_fields(draft.component("demand"), "demand")] == ["profile_type", "annual_demand"]