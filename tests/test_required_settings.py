"""Settings that are not filled in: found by the check, so that the run never stops with an error nobody can read."""

import copy

import pytest

from backend import service_v2
from backend.blocks import get_path, put_path
from backend.findings import ComponentRef, SettingRef, finding_text
from backend.i18n import ENGLISH, Translator
from backend.scenario_checks import REQUIRED, check_required, required_settings
from backend.scenario_v2 import ScenarioV2
from backend.service import ScenarioError, ScenarioNotReady
from backend.templates import new_component
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.forms import FORMS
from tests.helpers import needs_cbc

DE = Translator("de")


def full_system():
    draft = ScenarioDraft()
    draft.apply_template("Full system")
    return draft


def without(scenario, template, block, path):
    values = copy.deepcopy(scenario.model_dump())
    component = next(c for c in values["components"] if c["id"] == template)
    put_path(component["blocks"][block], path, None)
    return ScenarioV2(**values)


# (the component, the block, the setting, the sentence in English and in German)
MISSING = [
    ("gas_boiler", "conversion", "outputs.heat.efficiency",
     "Gas boiler: Efficiency is not filled in.", "Gaskessel: Wirkungsgrad ist nicht ausgefüllt."),
    ("battery", "storage", "efficiency_charge",
     "Battery storage: Charging efficiency is not filled in.", "Batteriespeicher: Lade-Wirkungsgrad ist nicht ausgefüllt."),
    ("battery", "storage", "efficiency_discharge",
     "Battery storage: Discharging efficiency is not filled in.", "Batteriespeicher: Entlade-Wirkungsgrad ist nicht ausgefüllt."),
    ("heat_storage", "storage", "loss_rate",
     "Heat storage: Self-discharge is not filled in.", "Wärmespeicher: Selbstentladung ist nicht ausgefüllt."),
    ("grid_feedin", "costs", "revenue",
     "Grid feed-in: Feed-in tariff is not filled in.", "Netzeinspeisung: Einspeisevergütung ist nicht ausgefüllt."),
    ("gas_import", "costs", "variable_costs",
     "Gas import: Gas price is not filled in.", "Gasbezug: Gaspreis ist nicht ausgefüllt."),
    ("grid", "costs", "variable_costs",
     "Electricity grid: Electricity price is not filled in.", "Stromnetz: Strompreis ist nicht ausgefüllt."),
    ("demand", "demand", "annual_demand",
     "Electricity demand: Annual electricity demand is not filled in.", "Strombedarf: Jahresstrombedarf ist nicht ausgefüllt."),
    ("heat_demand", "demand", "annual_demand",
     "Heat demand: Annual heat demand is not filled in.", "Wärmebedarf: Jahreswärmebedarf ist nicht ausgefüllt."),
]


def test_a_system_with_everything_filled_in_misses_nothing():
    assert check_required(full_system().scenario()) == []


@pytest.mark.parametrize("template, block, path, english, german", MISSING)
def test_a_setting_that_is_not_filled_in_is_an_error_with_a_sentence_in_both_languages(
        template, block, path, english, german):
    scenario = without(full_system().scenario(), template, block, path)

    found = check_required(scenario)

    assert len(found) == 1 and found[0].level == "error" and found[0].code == "value_missing"
    assert found[0].params == {"component": ComponentRef(template), "setting": SettingRef(block, path, template)}
    assert finding_text(found[0], ENGLISH) == english
    assert finding_text(found[0], DE) == german


def test_the_check_of_the_service_has_it_too_and_the_run_is_refused():
    scenario = without(full_system().scenario(), "gas_import", "costs", "variable_costs")

    errors = [f for f in service_v2.check(scenario) if f.level == "error" and f.code == "value_missing"]

    assert [f.message for f in errors] == ["Gas import: Gas price is not filled in."]
    with pytest.raises(ScenarioNotReady) as stopped:
        service_v2.run(scenario)
    assert any(f.code == "value_missing" for f in stopped.value.findings)


def test_a_price_of_0_is_filled_in():
    draft = full_system()
    draft.component("gas_import").blocks["costs"]["variable_costs"] = 0.0

    assert check_required(draft.scenario()) == []


def test_what_the_system_check_already_asks_for_is_not_asked_twice():
    scenario = without(full_system().scenario(), "heating_rod", "conversion", "outputs.heat.efficiency")

    assert check_required(scenario) == []
    codes = [f.code for f in service_v2.check(scenario) if f.level == "error"]
    assert codes.count("efficiency") == 1 and "value_missing" not in codes


def test_a_grid_with_a_price_series_does_not_need_the_price():
    grid = new_component("grid")
    assert ("costs", "variable_costs") in required_settings(grid)

    grid.blocks["costs"] = {"variable_costs_series": "price"}

    assert ("costs", "variable_costs") not in required_settings(grid)


def test_a_demand_in_kw_does_not_need_the_annual_demand():
    demand = new_component("demand")
    assert ("demand", "annual_demand") in required_settings(demand)

    demand.blocks["demand"]["profile_type"] = "absolute"

    assert required_settings(demand) == []


def test_a_component_that_is_not_one_of_the_templates_needs_nothing_of_this():
    from backend.scenario_v2 import Component

    custom = Component(id="x", name="Electrolyser", template=None, kind="converter",
                       connections=[{"carrier": "electricity", "direction": "in"},
                                    {"carrier": "hydrogen", "direction": "out"}], blocks={})

    assert required_settings(custom) == []


def test_the_name_of_a_setting_is_the_one_of_its_form_with_the_words_of_its_own():
    assert SettingRef("costs", "variable_costs", "grid").render(ENGLISH) == "Electricity price"
    assert SettingRef("costs", "variable_costs", "gas_import").render(DE) == "Gaspreis"
    assert SettingRef("costs", "variable_costs").render(ENGLISH) == "Variable costs"          # no component: the general words


def test_every_setting_that_is_required_is_in_the_form_of_its_component():
    # whatever the check asks for can be filled in
    for template, settings in REQUIRED.items():
        for block, key in settings:
            shown = FORMS[template][block]
            assert shown is None or key in shown, (template, key)


def test_the_paths_of_a_block():
    values = {"outputs": {"heat": {"efficiency": 90.0}}}

    assert get_path(values, "outputs.heat.efficiency") == 90.0
    assert get_path(values, "outputs.heat.ratio") is None and get_path(values, "outputs.gas.efficiency") is None
    assert get_path({}, "outputs.heat.efficiency") is None and get_path({"outputs": 5}, "outputs.heat") is None

    put_path(values, "outputs.heat.ratio", 3.5)
    assert values == {"outputs": {"heat": {"efficiency": 90.0, "ratio": 3.5}}}
    put_path(values, "outputs.electricity.efficiency", 35)
    assert get_path(values, "outputs.electricity.efficiency") == 35

    put_path(values, "outputs.electricity.efficiency", None)
    assert "electricity" not in values["outputs"]                            # the empty parent goes with it
    put_path(values, "outputs.heat.ratio", None)
    put_path(values, "outputs.heat.efficiency", None)
    assert values == {}
    put_path(values, "outputs.heat.efficiency", None)                         # nothing there: nothing happens
    assert values == {}


# ---------------------------------------------------------------------------
# with the solver: whatever is cleared in a form, the run is refused or it runs, and it never crashes
# ---------------------------------------------------------------------------

@needs_cbc
def test_clearing_any_setting_of_a_form_never_makes_the_run_crash():
    """Refused with a sentence, solved, or reported by the solver as unsolvable: never an error nobody can read."""

    from tests.test_scenario_convert_golden import chp_system, heat_system, pv_and_battery
    from tests.test_forms import shown_in_some_mode
    from tests.v1_support import scenario_from_v1

    runs = refused = unsolvable = 0
    for build in (pv_and_battery, heat_system, chp_system):
        base = scenario_from_v1(build())
        for component in base.components:
            if component.template not in FORMS:
                continue
            for block, path in sorted(shown_in_some_mode(component.template)):
                if get_path(component.blocks.get(block, {}), path) is None:
                    continue                                                     # nothing there to clear
                scenario = without(base, component.id, block, path)
                try:
                    service_v2.run(scenario)
                    runs += 1
                except ScenarioNotReady:
                    refused += 1                                                 # a sentence, as meant
                except ScenarioError:
                    unsolvable += 1                  # the solver says so, also in a sentence (no maximum: unbounded)

    # the three outcomes were all really tried; any other error would have failed the test
    assert refused >= 20 and runs >= 5 and unsolvable >= 1