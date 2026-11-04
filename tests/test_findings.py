"""Findings: a code plus parameters, worded in the language of the reader."""

import pickle

import pytest

from backend.findings import ComponentRef, Finding, Fixed, coded, finding_text, reference
from backend.i18n import ENGLISH, Translator, catalog
from backend.system_check import check_system
from backend.templates import new_component
from tests.helpers import timeindex

DE = Translator("de")
EN = catalog("en")


# ---------------------------------------------------------------------------
# a finding
# ---------------------------------------------------------------------------

def test_a_finding_without_a_code_is_just_its_message():
    finding = Finding("error", "Something is wrong.")

    assert (finding.code, finding.params, finding.fixes) == (None, {}, ())
    assert finding_text(finding, DE) == "Something is wrong."          # nothing to translate


def test_two_findings_with_the_same_content_are_equal():
    assert Finding("error", "x") == Finding("error", "x")
    assert coded("error", "no_demand") == coded("error", "no_demand")
    assert coded("error", "no_demand") != coded("warning", "no_demand")


def test_each_finding_has_its_own_parameters():
    first, second = Finding("error", "x"), Finding("error", "y")

    first.params["a"] = 1

    assert second.params == {}


def test_a_coded_finding_has_its_code_its_parameters_and_the_english_wording():
    found = coded("error", "demand_no_supply", None, (("grid",),), component=ComponentRef("demand"))

    assert found.level == "error" and found.code == "demand_no_supply"
    assert found.params == {"component": ComponentRef("demand")}
    assert found.fixes == (("grid",),)
    assert found.message == "Electricity demand has no supply. Add a grid connection (or PV or wind)."


def test_a_finding_can_be_sent_between_processes():
    found = coded("warning", "renewables_alone", None, (("grid",),),
                  components=[ComponentRef("pv"), ComponentRef("wind")], n=2)

    again = pickle.loads(pickle.dumps(found))

    assert again == found and finding_text(again, DE) == finding_text(found, DE)


# ---------------------------------------------------------------------------
# the names of the components
# ---------------------------------------------------------------------------

def test_the_names_of_the_caller_are_used_for_the_english_wording_and_a_missing_one_shows_the_key():
    with_names = coded("error", "needs_electricity", {"heat_pump": "Heat Pump (mine)"},
                       component=ComponentRef("heat_pump"))
    without_names = coded("error", "needs_electricity", {}, component=ComponentRef("heat_pump"))

    assert with_names.message == "Heat Pump (mine) needs electricity and cannot run."
    assert without_names.message == "heat_pump needs electricity and cannot run."


def test_without_names_a_component_is_named_by_the_catalog_in_the_language_of_the_reader():
    found = coded("error", "needs_electricity", {}, component=ComponentRef("heat_pump"))

    assert finding_text(found, ENGLISH) == "Heat pump needs electricity and cannot run."
    assert finding_text(found, DE) == "Wärmepumpe braucht Strom und kann nicht laufen."


def test_names_that_are_given_win_over_the_catalog():
    found = coded("error", "needs_electricity", {}, component=ComponentRef("heat_pump"))

    assert finding_text(found, DE, {"heat_pump": "WP 1"}) == "WP 1 braucht Strom und kann nicht laufen."


def test_a_component_with_a_name_of_its_own_is_not_translated():
    found = coded("warning", "profile_shares", None, component="Office demand", total=Fixed(0.9, 3))

    assert finding_text(found, DE).startswith("Office demand: Das Bedarfsprofil")


# ---------------------------------------------------------------------------
# the other parameters
# ---------------------------------------------------------------------------

def test_a_number_with_decimals_is_written_the_way_of_the_language():
    found = coded("warning", "profile_shares", None, component="X", total=Fixed(0.9, 3))

    assert "adds up to 0.900," in finding_text(found, ENGLISH)
    assert "summiert sich auf 0,900," in finding_text(found, DE)
    assert "30000.000" in finding_text(coded("warning", "profile_shares", None, component="X",
                                             total=Fixed(30000.0, 3)), ENGLISH)


def test_a_float_is_written_without_trailing_zeros_and_with_a_decimal_comma_in_german():
    found = coded("error", "chp_efficiency_sum", None, component=ComponentRef("chp"), total=1.2)

    assert "(1.2)" in finding_text(found, ENGLISH)
    assert "(1,2)" in finding_text(found, DE)


def test_a_count_is_written_as_it_is():
    found = coded("error", "series_short", None, component=ComponentRef("demand"), count=8760, needed=8784)

    assert "has 8760 values" in finding_text(found, ENGLISH)
    assert "hat 8760 Werte" in finding_text(found, DE)


def test_a_list_is_joined_with_and_in_the_language_of_the_reader():
    found = coded("warning", "surplus_not_exported", None,
                  components=[ComponentRef("pv"), ComponentRef("wind")])

    assert "from PV system and Wind turbine cannot" in finding_text(found, ENGLISH)
    assert "aus PV-Anlage und Windkraftanlage kann" in finding_text(found, DE)


def test_a_list_with_one_component_has_no_joining_word():
    found = coded("warning", "surplus_not_exported", None, components=[ComponentRef("pv")])

    assert "from PV system cannot" in finding_text(found, ENGLISH)


def test_the_singular_or_plural_text_follows_n():
    one = coded("warning", "renewables_alone", None, components=[ComponentRef("pv")], n=1)
    two = coded("warning", "renewables_alone", None, components=[ComponentRef("pv"), ComponentRef("wind")], n=2)

    assert finding_text(one, DE).startswith("PV-Anlage allein kann den Bedarf")
    assert finding_text(two, DE).startswith("PV-Anlage und Windkraftanlage allein können den Bedarf")


# ---------------------------------------------------------------------------
# which component a message names
# ---------------------------------------------------------------------------

def test_a_component_with_its_standard_name_follows_the_language():
    assert reference(new_component("pv")) == ComponentRef("pv")


def test_a_component_with_a_name_of_its_own_keeps_it():
    assert reference(new_component("pv", name="PV south roof")) == "PV south roof"


def test_a_name_that_is_the_standard_name_of_another_template_is_a_name_of_its_own():
    assert reference(new_component("pv", name="Heat pump")) == "Heat pump"


def test_a_component_without_a_template_keeps_its_name():
    from backend.scenario_v2 import Component

    custom = Component(id="x", name="Electrolyser", template=None, kind="converter",
                       connections=[{"carrier": "electricity", "direction": "in"},
                                    {"carrier": "hydrogen", "direction": "out"}], blocks={})

    assert reference(custom) == "Electrolyser"


def test_a_reference_to_a_component_the_catalog_does_not_know_shows_the_key():
    assert ComponentRef("ufo").render(DE) == "component.ufo.label"
    assert ComponentRef("ufo").render(DE, {}) == "ufo"


# ---------------------------------------------------------------------------
# a tour through every message of the system check, in both languages
# ---------------------------------------------------------------------------

OK = [0.5] * 24
GRID = {"grid": {"price_mode": "constant", "variable_costs": 0.3}}
DEMAND = {"electricity_demand": OK}
HEAT = {"heat_demand": OK}
FIXED = {"mode": "fixed", "capacity": 5.0}

CASES = {
    "no_demand": ([], {}, {}),
    "demand_no_supply": (["demand"], {}, DEMAND),
    "heat_not_supplied": (["heat_demand"], {}, HEAT),
    "grid_price_missing": (["demand", "grid"], {"grid": {"price_mode": "timeseries"}}, DEMAND),
    "grid_price_unit": (["demand", "grid"], {"grid": {"price_mode": "timeseries", "price_unit": "ct/MWh"}},
                        {**DEMAND, "grid_price": OK}),
    "grid_price_empty": (["demand", "grid"], {"grid": {"price_mode": "timeseries"}},
                         {**DEMAND, "grid_price": [float("nan")] * 24}),
    "grid_price_short": (["demand", "grid"], {"grid": {"price_mode": "timeseries"}},
                         {**DEMAND, "grid_price": [0.3] * 10}),
    "feedin_above_price": (["demand", "grid", "grid_feedin"],
                           {"grid": {"price_mode": "constant", "variable_costs": 0.1},
                            "grid_feedin": {"feedin_tariff": 0.2}}, DEMAND),
    "feedin_above_lowest_price": (["demand", "grid", "grid_feedin"],
                                  {"grid": {"price_mode": "timeseries"}, "grid_feedin": {"feedin_tariff": 0.2}},
                                  {**DEMAND, "grid_price": [0.1] * 24}),
    "profile_missing": (["demand", "grid"], GRID, {}),
    "cop_missing": (["demand", "heat_demand", "grid", "heat_pump"],
                    {**GRID, "heat_pump": {**FIXED, "cop_mode": "timeseries"}}, {**DEMAND, **HEAT}),
    "cop_not_positive": (["demand", "heat_demand", "grid", "heat_pump"],
                         {**GRID, "heat_pump": {**FIXED, "cop_mode": "constant", "cop_value": 0}}, {**DEMAND, **HEAT}),
    "series_invalid": (["demand", "grid"], GRID, {"electricity_demand": [float("nan")] + OK[1:]}),
    "series_short": (["demand", "grid"], GRID, {"electricity_demand": [0.5] * 10}),
    "series_long": (["demand", "grid"], GRID, {"electricity_demand": [0.5] * 30}),
    "efficiency": (["demand", "heat_demand", "grid", "heating_rod"],
                   {**GRID, "heating_rod": {**FIXED, "efficiency": 0}}, {**DEMAND, **HEAT}),
    "efficiency_electrical": (["demand", "heat_demand", "grid", "gas_import", "chp"],
                              {**GRID, "chp": {**FIXED, "efficiency_el": 0, "efficiency_th": 0.5}}, {**DEMAND, **HEAT}),
    "efficiency_thermal": (["demand", "heat_demand", "grid", "gas_import", "chp"],
                           {**GRID, "chp": {**FIXED, "efficiency_el": 0.35, "efficiency_th": 0}}, {**DEMAND, **HEAT}),
    "c_rate": (["demand", "grid", "battery"], {**GRID, "battery": {**FIXED, "c_rate": 0}}, DEMAND),
    "chp_efficiency_sum": (["demand", "heat_demand", "grid", "gas_import", "chp"],
                           {**GRID, "chp": {**FIXED, "efficiency_el": 0.6, "efficiency_th": 0.6}}, {**DEMAND, **HEAT}),
    "fixed_needs_capacity": (["demand", "grid", "pv"], {**GRID, "pv": {"mode": "fixed"}}, {**DEMAND, "pv": OK}),
    "invest_needs_values": (["demand", "grid", "pv"], {**GRID, "pv": {"mode": "invest"}}, {**DEMAND, "pv": OK}),
    "renewables_alone": (["demand", "pv"], {"pv": FIXED}, {**DEMAND, "pv": OK}),
    "surplus_not_exported": (["demand", "grid", "pv"], {**GRID, "pv": FIXED}, {**DEMAND, "pv": OK}),
    "feedin_unused": (["demand", "grid", "grid_feedin"], {**GRID, "grid_feedin": {"feedin_tariff": 0.05}}, DEMAND),
    "no_fuel": (["demand", "heat_demand", "grid", "heat_pump", "gas_boiler"],
                {**GRID, "heat_pump": {**FIXED, "cop_mode": "constant", "cop_value": 3.0}, "gas_boiler": FIXED},
                {**DEMAND, **HEAT}),
    "chp_no_heat_demand": (["demand", "grid", "gas_import", "chp"],
                           {**GRID, "chp": {**FIXED, "efficiency_el": 0.35, "efficiency_th": 0.5}}, DEMAND),
    "chp_only_heat_source": (["demand", "heat_demand", "gas_import", "chp"],
                             {"chp": {**FIXED, "efficiency_el": 0.35, "efficiency_th": 0.5}}, {**DEMAND, **HEAT}),
    "needs_electricity": (["heat_demand", "gas_import", "gas_boiler", "heat_pump"],
                          {"gas_boiler": FIXED, "heat_pump": {**FIXED, "cop_mode": "constant", "cop_value": 3.0}}, HEAT),
    "gas_unused": (["demand", "grid", "gas_import"], GRID, DEMAND),
    "battery_no_source": (["heat_demand", "gas_import", "gas_boiler", "battery"],
                          {"gas_boiler": FIXED, "battery": {**FIXED, "c_rate": 0.5}}, HEAT),
    "no_heat_demand": (["demand", "grid", "heat_pump"],
                       {**GRID, "heat_pump": {**FIXED, "cop_mode": "constant", "cop_value": 3.0}}, DEMAND),
}


def run_case(name):
    selected, tech, series = CASES[name]
    return check_system(selected, tech, {"timeindex": timeindex(24), **series})


def test_the_tour_covers_every_message_of_the_system_check():
    codes = {key.split(".")[1] for key in EN if key.startswith("check.")}
    codes -= {"profile_shares", "capacity_factor", "value_missing"}  # the data checks have their own tests

    assert codes == set(CASES)


@pytest.mark.parametrize("name", list(CASES))
def test_every_message_is_produced_and_worded_in_both_languages(name):
    found = [f for f in run_case(name) if f.code == name]

    assert found, f"{name} was not produced"
    for finding in found:
        english, german = finding_text(finding, ENGLISH), finding_text(finding, DE)
        assert "{" not in english and "{" not in german
        assert german != english
        assert finding.message and "{" not in finding.message


@pytest.mark.parametrize("name", list(CASES))
def test_a_message_has_the_level_that_it_always_had(name):
    expected = "warning" if name in {
        "series_long", "renewables_alone", "surplus_not_exported", "feedin_unused", "no_fuel",
        "chp_no_heat_demand", "chp_only_heat_source", "needs_electricity", "gas_unused",
        "battery_no_source", "no_heat_demand",
    } else "error"

    assert {f.level for f in run_case(name) if f.code == name} == {expected}


def test_the_german_message_names_the_component_in_german():
    found = [f for f in run_case("c_rate") if f.code == "c_rate"][0]

    assert finding_text(found, DE) == "Batteriespeicher: Die Lade-/Entladerate (C-Rate) muss größer als 0 sein."


def test_a_message_with_two_components_in_german():
    selected = ["demand", "pv", "wind"]
    tech = {"pv": FIXED, "wind": FIXED}
    series = {**DEMAND, "pv": OK, "wind": OK}

    found = [f for f in check_system(selected, tech, {"timeindex": timeindex(24), **series})
             if f.code == "renewables_alone"][0]

    assert finding_text(found, DE).startswith("PV-Anlage und Windkraftanlage allein können")
    assert found.message.startswith("pv and wind alone cannot cover demand")      # no names given: the keys


# the repairs that each message proposes (components that would solve it); a message that is not
# listed proposes none. The interfaces build their buttons from them. (test_fixes.py checks that each of
# them really repairs.)
FIXES = {
    "no_demand": (("demand",), ("heat_demand",)),
    "demand_no_supply": (("grid",),),
    "heat_not_supplied": (("gas_boiler", "gas_import"), ("chp", "gas_import"),
                          ("heat_pump", "grid"), ("heating_rod", "grid")),
    "renewables_alone": (("grid",),),
    "surplus_not_exported": (("grid_feedin",),),
    "feedin_unused": (("pv",), ("wind",), ("chp", "gas_import", "heat_demand")),
    "no_fuel": (("gas_import",),),
    "chp_no_heat_demand": (("heat_demand",),),
    "chp_only_heat_source": (("grid_feedin",),),
    "needs_electricity": (("grid",),),
    "gas_unused": (("gas_boiler",), ("chp",)),
    "battery_no_source": (("grid",), ("pv",), ("wind",)),
    "no_heat_demand": (("heat_demand",),),
}


@pytest.mark.parametrize("name", list(CASES))
def test_a_message_proposes_the_repairs_it_is_expected_to(name):
    for finding in run_case(name):
        if finding.code == name:
            assert finding.fixes == FIXES.get(name, ()), name


def test_a_repair_only_names_what_is_still_missing():
    # the heat pump is there already: only the grid is missing
    selected = ["demand", "heat_demand", "heat_pump"]
    tech = {"heat_pump": {**FIXED, "cop_mode": "constant", "cop_value": 3.0}}

    found = [f for f in check_system(selected, tech, {"timeindex": timeindex(24), **DEMAND, **HEAT})
             if f.code == "heat_not_supplied"][0]

    assert found.fixes == (("gas_boiler", "gas_import"), ("chp", "gas_import"), ("grid",), ("heating_rod", "grid"))