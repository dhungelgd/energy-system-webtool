"""Warnings about the data of a layout 2 scenario."""

import pytest

from backend.scenario_checks import check_data
from backend.scenario_v2 import ScenarioV2

YEAR = 8760


def scenario(demand=None, profile=None, profile_type=None, wind=None):
    """A scenario with a demand and a PV system, and the given time series."""

    series, components = {}, []

    demand_block = {"series": "load"}
    if profile_type is not None:
        demand_block["profile_type"] = profile_type
    if demand is not None:
        series["load"] = {"values": demand}
    components.append({"id": "demand", "name": "Office demand", "kind": "sink",
                       "connections": [{"carrier": "electricity", "direction": "in"}],
                       "blocks": {"demand": demand_block}})

    components.append({"id": "pv", "name": "Roof PV", "kind": "source",
                       "connections": [{"carrier": "electricity", "direction": "out"}],
                       "blocks": {"profile": {"series": "sun"}}})
    if profile is not None:
        series["sun"] = {"values": profile}

    if wind is not None:
        components.append({"id": "wind", "name": "Field wind", "kind": "source",
                           "connections": [{"carrier": "electricity", "direction": "out"}],
                           "blocks": {"profile": {"series": "air"}}})
        series["air"] = {"values": wind}

    # a series that a block refers to must exist: an empty one for the ones not given
    for component in components:
        for block in component["blocks"].values():
            series.setdefault(block["series"], {"values": []})

    return ScenarioV2(carriers=[{"id": "electricity", "label": "Electricity"}], components=components,
                      series=series)


def messages(found):
    return [f.message for f in found]


# ---------------------------------------------------------------------------
# a demand profile of shares of the annual demand
# ---------------------------------------------------------------------------

def test_shares_that_add_up_to_1_over_a_year_are_fine():
    assert check_data(scenario(demand=[1 / YEAR] * YEAR)) == []


@pytest.mark.parametrize("total", [0.995, 1.005, 1.0099])
def test_a_sum_within_one_percent_is_fine(total):
    assert check_data(scenario(demand=[total / YEAR] * YEAR)) == []


@pytest.mark.parametrize("total", [0.9, 0.98, 1.02, 30000.0])
def test_a_sum_that_is_off_is_a_warning_with_the_sum_and_the_way_out(total):
    found = check_data(scenario(demand=[total / YEAR] * YEAR))

    assert [f.level for f in found] == ["warning"]
    assert f"adds up to {total:.3f}" in found[0].message
    assert found[0].message.startswith("Office demand:")           # the name, not the id
    assert "'The demand in kW'" in found[0].message


def test_a_leap_year_is_a_whole_year_too():
    assert check_data(scenario(demand=[1 / 8784] * 8784)) == []
    assert check_data(scenario(demand=[0.9 / 8784] * 8784))


def test_a_part_of_a_year_says_nothing_about_the_total_and_is_not_tested():
    assert check_data(scenario(demand=[0.5 / 24] * 24)) == []
    assert check_data(scenario(demand=[0.0001] * (YEAR - 1))) == []


def test_a_profile_with_gaps_cannot_be_summed_and_is_not_tested():
    assert check_data(scenario(demand=[None] + [0.1 / YEAR] * (YEAR - 1))) == []


def test_absolute_values_are_never_expected_to_add_up_to_1():
    assert check_data(scenario(demand=[10.0] * YEAR, profile_type="absolute")) == []


def test_without_a_choice_the_default_is_shares_of_the_annual_demand():
    assert check_data(scenario(demand=[10.0] * YEAR))
    assert check_data(scenario(demand=[10.0] * YEAR, profile_type="annual_share"))


def test_a_demand_without_data_has_nothing_to_warn_about():
    assert check_data(scenario(demand=[])) == []
    assert check_data(scenario(demand=None)) == []


# ---------------------------------------------------------------------------
# a generation profile is a capacity factor
# ---------------------------------------------------------------------------

def test_capacity_factors_up_to_1_are_fine():
    assert check_data(scenario(profile=[0.0, 0.5, 1.0])) == []


def test_a_rounding_error_above_1_is_fine():
    assert check_data(scenario(profile=[0.5, 1.0 + 1e-12])) == []


def test_values_above_1_are_a_warning_with_the_largest_value_and_the_way_out():
    found = check_data(scenario(profile=[0.0, 2.5, 5.0, 1.0]))

    assert [f.level for f in found] == ["warning"]
    assert "up to 5.00" in found[0].message
    assert found[0].message.startswith("Roof PV:")
    assert "divided by its size" in found[0].message


def test_wind_is_checked_like_pv_and_each_gets_its_own_warning():
    found = check_data(scenario(profile=[3.0], wind=[2.0]))

    assert [m.split(":")[0] for m in messages(found)] == ["Roof PV", "Field wind"]


def test_gaps_in_a_generation_profile_are_ignored_and_empty_data_is_fine():
    assert check_data(scenario(profile=[None, 0.5, None])) == []
    assert check_data(scenario(profile=[None, 3.0]))                  # the number that is there is checked
    assert check_data(scenario(profile=[])) == []


# ---------------------------------------------------------------------------
# together
# ---------------------------------------------------------------------------

def test_both_kinds_of_warnings_come_in_the_order_of_the_components():
    found = check_data(scenario(demand=[0.5 / YEAR] * YEAR, profile=[4.0]))

    assert [m.split(":")[0] for m in messages(found)] == ["Office demand", "Roof PV"]
    assert all(f.level == "warning" for f in found)


def test_checking_does_not_change_the_scenario():
    original = scenario(demand=[0.5 / YEAR] * YEAR, profile=[4.0])
    before = original.model_dump()

    check_data(original)

    assert original.model_dump() == before