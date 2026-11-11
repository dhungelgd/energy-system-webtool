"""The board: where each component belongs, what a tile says, and which findings belong to which tile."""

import pytest

from backend import service_v2
from backend.component_specs import INFO
from backend.findings import ComponentRef, Finding
from backend.i18n import ENGLISH, Translator
from frontend_nicegui.board import (
    BOARD,
    COLUMN_TEXTS,
    COLUMNS,
    LANES,
    STYLE,
    addable,
    every_component_has_a_place,
    finding_keys,
    findings_by_component,
    place_of,
    problem_texts,
    tile_detail,
    tile_problem_text,
    tile_state,
)
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.forms import set_value

DE = Translator("de")


def draft_with(*keys, steps=24):
    draft = ScenarioDraft(steps=steps)
    for key in keys:
        draft.set(key, True)

    return draft


def finding(level="error", code="x", **params):
    return Finding(level=level, message="the message", code=code, params=params)


# ---------------------------------------------------------------------------
# the places
# ---------------------------------------------------------------------------

def test_every_component_has_exactly_one_place_and_a_style():
    assert every_component_has_a_place()
    placed = [key for columns in BOARD.values() for keys in columns.values() for key in keys]

    assert sorted(placed) == sorted(INFO) and len(placed) == len(set(placed))
    assert set(STYLE) == set(INFO)


def test_the_board_has_three_lanes_with_four_columns_each_and_demand_comes_first():
    assert LANES == ("electricity", "heat", "gas") and COLUMNS == ("demand", "supply", "conversion", "storage")
    assert all(set(BOARD[lane]) == set(COLUMNS) for lane in LANES)
    assert set(COLUMN_TEXTS) == set(COLUMNS)


@pytest.mark.parametrize("key, place", [
    ("grid", ("electricity", "supply")), ("pv", ("electricity", "supply")), ("battery", ("electricity", "storage")),
    ("demand", ("electricity", "demand")), ("grid_feedin", ("electricity", "demand")),
    ("heat_pump", ("heat", "conversion")), ("chp", ("heat", "conversion")), ("heat_storage", ("heat", "storage")),
    ("heat_demand", ("heat", "demand")), ("gas_import", ("gas", "supply")),
])
def test_where_a_component_is(key, place):
    assert place_of(key) == place


def test_an_unknown_component_has_no_place():
    with pytest.raises(KeyError):
        place_of("fusion_reactor")


def test_what_can_still_be_added_in_a_place_keeps_the_order_of_the_board():
    assert addable("electricity", "supply", []) == ["grid", "pv", "wind"]
    assert addable("electricity", "supply", ["pv"]) == ["grid", "wind"]
    assert addable("electricity", "supply", ["grid", "pv", "wind"]) == []
    assert addable("gas", "storage", []) == [] and addable("heat", "supply", []) == []     # nothing fits there


# ---------------------------------------------------------------------------
# the short line of a tile
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key, english, german", [
    ("demand", "30,000 kWh per year", "30.000 kWh pro Jahr"),
    ("heat_demand", "90,000 kWh per year", "90.000 kWh pro Jahr"),
    ("grid", "Price 0.3 EUR/kWh", "Preis 0,3 €/kWh"),
    ("gas_import", "Price 0.1 EUR/kWh", "Preis 0,1 €/kWh"),
    ("grid_feedin", "Revenue 0.078 EUR/kWh", "Vergütung 0,078 €/kWh"),
])
def test_the_line_of_a_component_without_a_size_says_its_yearly_demand_or_its_price(key, english, german):
    component = draft_with(key).component(key)

    assert tile_detail(component, ENGLISH) == english and tile_detail(component, DE) == german


def test_a_demand_that_is_given_as_a_series_in_kw():
    draft = draft_with("demand")
    set_value(draft.component("demand"), "demand", "profile_type", "absolute")

    assert tile_detail(draft.component("demand"), ENGLISH) == "Time series in kW"
    assert tile_detail(draft.component("demand"), DE) == "Zeitreihe in kW"


def test_a_yearly_demand_with_decimals_is_rounded_to_whole_kwh():
    draft = draft_with("demand")
    draft.component("demand").blocks["demand"]["annual_demand"] = 12345.678

    assert tile_detail(draft.component("demand"), ENGLISH) == "12,346 kWh per year"
    assert tile_detail(draft.component("demand"), DE) == "12.346 kWh pro Jahr"


def test_what_is_not_set_says_so():
    draft = draft_with("demand", "grid", "grid_feedin")
    draft.component("demand").blocks["demand"].pop("annual_demand")
    draft.component("grid").blocks["costs"]["variable_costs"] = None
    draft.component("grid_feedin").blocks["costs"]["revenue"] = None

    assert [tile_detail(draft.component(k), ENGLISH) for k in ("demand", "grid", "grid_feedin")] == ["Not set yet"] * 3
    assert tile_detail(draft.component("grid"), DE) == "Noch nicht festgelegt"


def test_a_price_that_comes_from_a_series_says_so():
    draft = draft_with("grid")
    draft.component("grid").blocks["costs"].pop("variable_costs")

    assert tile_detail(draft.component("grid"), ENGLISH) == "Price as a time series"
    assert tile_detail(draft.component("grid"), DE) == "Preis als Zeitreihe"


def test_the_line_of_a_component_with_a_size_says_how_the_size_is_found():
    draft = draft_with("pv", "battery", "heat_pump")
    set_value(draft.component("pv"), "capacity", "capacity", 5.0)
    set_value(draft.component("battery"), "capacity", "mode", "invest")
    set_value(draft.component("battery"), "capacity", "maximum", 50.0)
    set_value(draft.component("heat_pump"), "capacity", "mode", "invest")

    assert tile_detail(draft.component("pv"), ENGLISH) == "fixed: 5 kW"
    assert tile_detail(draft.component("battery"), ENGLISH) == "invest: up to 50 kWh"          # a storage is in kWh
    assert tile_detail(draft.component("heat_pump"), ENGLISH) == "invest: no upper limit"
    assert tile_detail(draft.component("pv"), DE) == "fest: 5 kW"
    assert tile_detail(draft.component("battery"), DE) == "Investition: bis zu 50 kWh"


def test_a_fixed_size_that_is_not_set_says_so():
    assert tile_detail(draft_with("wind").component("wind"), ENGLISH) == "fixed: not set"


# ---------------------------------------------------------------------------
# which findings belong to which tile
# ---------------------------------------------------------------------------

def test_a_finding_belongs_to_the_component_that_it_names():
    assert finding_keys(finding(component=ComponentRef("pv")), {}) == {"pv"}


def test_a_finding_that_names_several_components_belongs_to_each_of_them():
    assert finding_keys(finding(components=[ComponentRef("pv"), ComponentRef("wind")]), {}) == {"pv", "wind"}


def test_a_component_with_a_name_of_its_own_is_named_by_that_name_and_still_found():
    assert finding_keys(finding(component="PV Dach Süd"), {"PV Dach Süd": "pv"}) == {"pv"}
    assert finding_keys(finding(component="Something else"), {"PV Dach Süd": "pv"}) == set()


def test_the_two_findings_about_the_price_of_the_feed_in_belong_to_the_grid_and_the_feed_in():
    assert finding_keys(finding(code="feedin_above_price", tariff=0.4, price=0.3), {}) == {"grid", "grid_feedin"}
    assert finding_keys(finding(code="feedin_above_lowest_price"), {}) == {"grid", "grid_feedin"}


def test_a_finding_about_nothing_in_particular_belongs_to_no_tile():
    assert finding_keys(finding(code="no_demand"), {}) == set() and finding_keys(finding(amount=3), {}) == set()


def test_findings_are_sorted_into_the_components_of_the_draft():
    draft = draft_with("demand", "grid", "pv")                       # the demand has no data, the PV has no size
    found = findings_by_component(service_v2.check(draft.scenario()), draft.components())

    assert set(found) == {"demand", "grid", "pv"}
    assert found["demand"] and not found["grid"]
    assert any(f.level == "error" for f in found["demand"])


def test_a_finding_about_a_component_that_is_not_in_the_draft_is_dropped():
    draft = draft_with("demand")

    found = findings_by_component([finding(component=ComponentRef("pv"))], draft.components())

    assert found == {"demand": []}


def test_a_finding_about_two_components_is_in_both_lists():
    draft = draft_with("pv", "wind")
    shared = finding("warning", components=[ComponentRef("pv"), ComponentRef("wind")])

    found = findings_by_component([shared], draft.components())

    assert found["pv"] == [shared] and found["wind"] == [shared]


def test_a_component_with_a_name_of_its_own_still_gets_its_findings_from_a_real_check():
    draft = draft_with("demand", "grid", "pv")
    draft.component("pv").name = "PV Dach Süd"                       # no data and no size yet

    found = findings_by_component(service_v2.check(draft.scenario()), draft.components())

    assert {f.code for f in found["pv"]} == {"profile_missing", "fixed_needs_capacity", "surplus_not_exported"}
    assert [f.code for f in found["demand"]] == ["profile_missing"] and found["grid"] == []


# ---------------------------------------------------------------------------
# the state and the words of a tile
# ---------------------------------------------------------------------------

def test_the_state_of_a_tile_is_the_worst_of_its_findings():
    assert tile_state([]) == "ok"
    assert tile_state([finding("warning")]) == "warning"
    assert tile_state([finding("warning"), finding("error")]) == "error"


@pytest.mark.parametrize("findings, english, german", [
    ([], "", ""),
    ([finding("error")], "1 error", "1 Fehler"),
    ([finding("error"), finding("warning")], "1 error, 1 warning", "1 Fehler, 1 Warnung"),
    ([finding("error")] * 2 + [finding("warning")] * 3, "2 errors, 3 warnings", "2 Fehler, 3 Warnungen"),
    ([finding("warning")], "1 warning", "1 Warnung"),
    ([finding("warning")] * 2, "2 warnings", "2 Warnungen"),
])
def test_what_a_tile_says_about_its_problems(findings, english, german):
    assert tile_problem_text(findings, ENGLISH) == english and tile_problem_text(findings, DE) == german


def test_the_full_sentences_come_with_the_errors_first():
    draft = draft_with("demand", "grid", "pv")
    found = findings_by_component(service_v2.check(draft.scenario()), draft.components())

    texts = problem_texts(found["demand"] + [finding("warning", code="short_period_invest", components=[ComponentRef("pv")], n=1)], ENGLISH)

    assert [level for level, _ in texts] == sorted((level for level, _ in texts), key=lambda level: level != "error")
    assert all(isinstance(text, str) and text for _, text in texts)