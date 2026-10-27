"""Converting between scenario layout 1 and layout 2."""

import pickle

import pytest

from backend.scenario import Scenario
from backend.scenario_convert import NotSupportedByEngine, engine_gaps, scenario_to_v1
from backend.scenario_v2 import ScenarioV2
from examples.make_examples_v2 import EXAMPLES
from tests.v1_support import ConversionError, scenario_from_v1

FULL_YEAR = 8760


def year(value=0.5, steps=FULL_YEAR):
    return [value] * steps


def v1(components, settings=None, series=None, steps=24, **changes):
    return Scenario(components=components, settings=settings or {}, series=series or {},
                    time={"steps": steps}, **changes)


def first(scenario, component_id):
    return scenario.component(component_id)


# ---------------------------------------------------------------------------
# percentages
# ---------------------------------------------------------------------------

def test_fractions_become_percentages_and_back():
    old = v1(["battery"], {"battery": {
        "mode": "fixed", "capacity": 10.0, "c_rate": 0.5,
        "efficiency_charge": 0.95, "efficiency_discharge": 0.9, "loss_rate": 0.001,
    }})

    new = scenario_from_v1(old)
    block = first(new, "battery").blocks["storage"]

    assert block == {"c_rate": 0.5, "efficiency_charge": 95.0, "efficiency_discharge": 90.0, "loss_rate": 0.1}

    back = scenario_to_v1(new).settings["battery"]
    assert back["efficiency_charge"] == pytest.approx(0.95)
    assert back["efficiency_discharge"] == pytest.approx(0.9)
    assert back["loss_rate"] == pytest.approx(0.001)
    assert back["c_rate"] == 0.5


def test_converter_efficiencies_are_percentages_too():
    old = v1(["chp", "gas_boiler", "heating_rod"], {
        "chp": {"mode": "fixed", "capacity": 10.0, "efficiency_el": 0.35, "efficiency_th": 0.5},
        "gas_boiler": {"mode": "fixed", "capacity": 10.0, "efficiency": 0.9},
        "heating_rod": {"mode": "fixed", "capacity": 10.0, "efficiency": 0.99},
    })

    new = scenario_from_v1(old)

    assert first(new, "chp").blocks["conversion"] == {
        "outputs": {"electricity": {"efficiency": 35.0}, "heat": {"efficiency": 50.0}}}
    assert first(new, "gas_boiler").blocks["conversion"]["outputs"]["heat"] == {"efficiency": 90.0}
    assert first(new, "heating_rod").blocks["conversion"]["outputs"]["heat"] == {"efficiency": 99.0}
    assert first(new, "chp").blocks["capacity"]["rated_flow"] == "electricity"
    assert first(new, "gas_boiler").blocks["capacity"]["rated_flow"] == "heat"


# ---------------------------------------------------------------------------
# the demand profile
# ---------------------------------------------------------------------------

def demand_of(profile, factor, steps=None):
    settings = {"demand": {"scaling_factor": factor}} if factor is not None else {"demand": {}}
    old = v1(["demand"], settings, {"electricity_demand": profile} if profile is not None else {},
             steps=steps or max(len(profile or []), 1))
    new = scenario_from_v1(old)
    return first(new, "demand").blocks["demand"], new.series["electricity_demand"]


def test_a_full_year_profile_that_adds_up_to_1_is_shares_of_the_annual_demand():
    block, data = demand_of(year(1 / FULL_YEAR), 30000.0)

    assert block == {"series": "electricity_demand", "profile_type": "annual_share", "annual_demand": 30000.0}
    assert data.values == year(1 / FULL_YEAR)
    assert data.unit == "share of the annual demand"


def test_a_sum_within_one_percent_of_1_still_counts_as_shares():
    block, _ = demand_of(year(0.995 / FULL_YEAR), 30000.0)

    assert block["profile_type"] == "annual_share"


def test_a_full_year_profile_that_does_not_add_up_to_1_is_multiplied_out_to_kw():
    block, data = demand_of(year(0.5), 100.0)

    assert block == {"series": "electricity_demand", "profile_type": "absolute"}
    assert data.values == year(50.0)                          # the hourly numbers stay the same
    assert data.unit == "kW"


def test_a_sum_clearly_off_from_1_is_multiplied_out():
    block, _ = demand_of(year(0.97 / FULL_YEAR), 30000.0)

    assert block["profile_type"] == "absolute"


def test_a_factor_of_1_means_the_profile_is_already_in_kw():
    block, data = demand_of(year(0.5), 1.0)

    assert block["profile_type"] == "absolute" and "annual_demand" not in block
    assert data.values == year(0.5) and data.unit == "kW"


def test_a_part_of_a_year_cannot_be_tested_and_is_taken_as_shares():
    block, data = demand_of([0.01] * 24, 10.0)

    assert block["profile_type"] == "annual_share" and block["annual_demand"] == 10.0
    assert data.values == [0.01] * 24


def test_a_missing_series_or_factor_stays_open_and_the_series_is_still_referenced():
    block, data = demand_of(None, 5.0)
    assert block == {"series": "electricity_demand", "profile_type": "annual_share", "annual_demand": 5.0}
    assert data.values == []

    block, _ = demand_of([0.01] * 24, None)
    assert block["profile_type"] == "annual_share" and "annual_demand" not in block


def test_the_way_back_gives_the_same_hourly_demand():
    for profile, factor in ((year(1 / FULL_YEAR), 30000.0), (year(0.5), 100.0), (year(0.5), 1.0), ([0.01] * 24, 10.0)):
        old = v1(["demand"], {"demand": {"scaling_factor": factor}}, {"electricity_demand": profile},
                 steps=len(profile))
        back = scenario_to_v1(scenario_from_v1(old))

        before = [v * factor for v in profile]
        after = [v * back.settings["demand"]["scaling_factor"] for v in back.series["electricity_demand"]]
        assert after == pytest.approx(before)


def test_shares_in_a_layout_2_scenario_become_the_scaling_factor_for_the_engine():
    old = scenario_to_v1(EXAMPLES["pv_and_grid"]())

    assert old.settings["demand"]["scaling_factor"] == 87600.0
    assert len(old.series["electricity_demand"]) == 24


def test_absolute_values_in_layout_2_get_a_factor_of_1():
    scenario = EXAMPLES["pv_and_grid"]().model_dump()
    scenario["components"][0]["blocks"]["demand"] = {"series": "electricity_demand", "profile_type": "absolute"}

    old = scenario_to_v1(ScenarioV2(**scenario))

    assert old.settings["demand"]["scaling_factor"] == 1.0


# ---------------------------------------------------------------------------
# prices, COP, series
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("unit, factor", [("€/kWh", 1.0), ("ct/kWh", 0.01), ("€/MWh", 0.001)])
def test_a_price_series_is_converted_to_euro_per_kwh(unit, factor):
    old = v1(["grid"], {"grid": {"price_mode": "timeseries", "price_unit": unit, "variable_costs": 0.3}},
             {"grid_price": [30.0, 40.0]}, steps=2)

    new = scenario_from_v1(old)

    assert first(new, "grid").blocks["costs"] == {"variable_costs": 0.3, "variable_costs_series": "grid_price"}
    assert new.series["grid_price"].values == pytest.approx([30.0 * factor, 40.0 * factor])
    assert new.series["grid_price"].unit == "€ per kWh"

    back = scenario_to_v1(new)
    assert back.settings["grid"]["price_mode"] == "timeseries" and back.settings["grid"]["price_unit"] == "€/kWh"
    assert back.series["grid_price"] == pytest.approx([30.0 * factor, 40.0 * factor])


def test_a_constant_price_needs_no_series_and_an_unused_price_series_is_kept():
    old = v1(["grid"], {"grid": {"price_mode": "constant", "variable_costs": 0.3}}, {"grid_price": [0.3, 0.4]}, steps=2)

    new = scenario_from_v1(old)

    assert first(new, "grid").blocks["costs"] == {"variable_costs": 0.3}
    assert new.series["grid_price"].values == [0.3, 0.4]            # kept, nobody uses it
    assert scenario_to_v1(new).series["grid_price"] == [0.3, 0.4]


def test_the_cop_is_a_ratio_or_a_ratio_series():
    constant = scenario_from_v1(v1(["heat_pump"], {"heat_pump": {"cop_mode": "constant", "cop_value": 3.5}}))
    assert first(constant, "heat_pump").blocks["conversion"] == {"outputs": {"heat": {"ratio": 3.5}}}

    series = scenario_from_v1(v1(["heat_pump"], {"heat_pump": {"cop_mode": "timeseries", "cop_value": 3.5}},
                                 {"cop_series": [3.0, 4.0]}, steps=2))
    assert first(series, "heat_pump").blocks["conversion"] == {"outputs": {"heat": {"ratio_series": "cop_profile"}}}
    assert series.series["cop_profile"].values == [3.0, 4.0]

    assert scenario_to_v1(series).settings["heat_pump"]["cop_mode"] == "timeseries"
    assert scenario_to_v1(constant).settings["heat_pump"] == {"cop_mode": "constant", "cop_value": 3.5}


def test_pv_and_wind_profiles_are_series_that_are_always_used():
    old = v1(["pv", "wind"], {"pv": {"mode": "fixed", "capacity": 5.0}, "wind": {"mode": "fixed", "capacity": 5.0}},
             {"pv": [0.1, 0.2], "wind": [0.3, 0.4]}, steps=2)

    new = scenario_from_v1(old)

    assert first(new, "pv").blocks["profile"] == {"series": "pv_profile"}
    assert first(new, "wind").blocks["profile"] == {"series": "wind_profile"}
    assert new.series["pv_profile"].unit == "capacity factor"


def test_a_missing_series_is_an_empty_series_so_that_the_check_can_say_so():
    new = scenario_from_v1(v1(["pv"], {"pv": {"mode": "fixed", "capacity": 5.0}}))

    assert first(new, "pv").blocks["profile"] == {"series": "pv_profile"}
    assert new.series["pv_profile"].values == []


def test_the_name_of_the_file_column_is_kept_for_the_record():
    old = v1(["pv"], {"pv": {"mode": "fixed", "capacity": 5.0, "pv": "Erzeugung PV"}}, {"pv": [0.1, 0.2]}, steps=2)

    new = scenario_from_v1(old)

    assert new.series["pv_profile"].source.column == "Erzeugung PV"
    assert scenario_to_v1(new).settings["pv"]["pv"] == "Erzeugung PV"


def test_a_series_without_a_component_is_kept_and_goes_back():
    old = v1(["demand"], {"demand": {"scaling_factor": 10.0}}, {"electricity_demand": [0.1, 0.2], "wind": [0.3, 0.4]},
             steps=2)

    new = scenario_from_v1(old)

    assert new.series["wind_profile"].values == [0.3, 0.4]
    assert scenario_to_v1(new).series["wind"] == [0.3, 0.4]


# ---------------------------------------------------------------------------
# what cannot be converted from layout 1
# ---------------------------------------------------------------------------

def test_an_unknown_setting_is_named_and_never_dropped():
    old = v1(["gas_boiler"], {"gas_boiler": {"mode": "fixed", "capacity": 5.0, "colour": "red"}})

    with pytest.raises(ConversionError, match="gas_boiler: the setting 'colour' cannot be converted"):
        scenario_from_v1(old)


def test_an_unknown_price_unit_and_cop_mode_are_named():
    with pytest.raises(ConversionError, match="unknown price unit 'ct/MWh'"):
        scenario_from_v1(v1(["grid"], {"grid": {"price_mode": "timeseries", "price_unit": "ct/MWh"}},
                            {"grid_price": [1.0]}, steps=1))


def test_values_layout_2_does_not_allow_are_reported_as_a_conversion_error():
    old = v1(["gas_boiler"], {"gas_boiler": {"mode": "fixed", "capacity": 5.0, "efficiency": 1.5}})

    with pytest.raises(ConversionError, match="does not fit layout 2"):
        scenario_from_v1(old)


# ---------------------------------------------------------------------------
# what the engine cannot run
# ---------------------------------------------------------------------------

def pv_and_grid():
    return EXAMPLES["pv_and_grid"]().model_dump()


def gaps_of(scenario):
    return engine_gaps(ScenarioV2(**scenario))


def test_the_pv_and_grid_example_has_no_gaps():
    assert engine_gaps(EXAMPLES["pv_and_grid"]()) == []


def test_two_systems_of_one_template_are_a_gap():
    gaps = engine_gaps(EXAMPLES["two_pv_systems"]())

    assert gaps == ["The engine can only run one PV system (found pv_south, pv_east)"]


def test_the_hydrogen_chain_reports_everything_the_engine_cannot_do():
    gaps = engine_gaps(EXAMPLES["hydrogen_chain"]())

    assert "The carrier 'hydrogen' is user-defined; the engine only knows electricity, heat and gas" in gaps
    assert "'electrolyser' is a custom component; the engine only runs the curated components" in gaps
    assert "'h2_tank' is a custom component; the engine only runs the curated components" in gaps
    assert "'h2_demand' is a custom component; the engine only runs the curated components" in gaps


def test_on_off_behaviour_and_the_initial_charge_level_are_reported():
    scenario = pv_and_grid()
    scenario["components"][2]["blocks"]["on_off"] = {"minimum_load": 10.0}

    assert gaps_of(scenario) == ["'pv': On/off behaviour is not supported by the engine yet"]

    battery = ScenarioV2(**{
        **pv_and_grid(),
        "components": pv_and_grid()["components"] + [{
            "id": "battery", "name": "Battery", "template": "battery", "kind": "storage",
            "connections": [{"carrier": "electricity", "direction": "both"}],
            "blocks": {"capacity": {"mode": "fixed", "capacity": 10.0},
                       "storage": {"c_rate": 0.5, "initial_level": 50.0}},
        }],
    })

    assert engine_gaps(battery) == ["'battery': the setting 'storage.initial_level' is not supported by the engine yet"]


def test_a_setting_that_does_not_belong_to_the_template_is_reported():
    scenario = pv_and_grid()
    scenario["components"][1]["blocks"]["costs"]["revenue"] = 0.05

    assert gaps_of(scenario) == ["'grid': the setting 'costs.revenue' is not supported by the engine yet"]


def test_a_block_that_is_not_part_of_the_template_is_reported():
    scenario = pv_and_grid()
    scenario["components"][1]["blocks"]["capacity"] = {"mode": "fixed", "capacity": 5.0}

    assert gaps_of(scenario) == ["'grid': the block 'capacity' is not part of Electricity grid"]


def test_a_template_that_was_changed_or_is_unknown_is_reported():
    scenario = pv_and_grid()
    scenario["carriers"].append({"id": "heat", "label": "Heat"})
    scenario["components"][0]["connections"] = [{"carrier": "heat", "direction": "in"}]
    scenario["components"][2]["template"] = "solar"

    assert gaps_of(scenario) == [
        "'pv' uses the unknown template 'solar'",
        "'demand' was changed from its template (kind or connections)",
    ]


def test_the_size_must_refer_to_the_flow_the_engine_uses():
    chp = {
        "id": "chp", "name": "CHP", "template": "chp", "kind": "converter",
        "connections": [{"carrier": "gas", "direction": "in"}, {"carrier": "electricity", "direction": "out"},
                        {"carrier": "heat", "direction": "out"}],
        "blocks": {"capacity": {"mode": "fixed", "capacity": 10.0, "rated_flow": "heat"}},
    }
    scenario = ScenarioV2(carriers=[{"id": c, "label": c} for c in ("electricity", "heat", "gas")], components=[chp])

    assert engine_gaps(scenario) == ["'chp': the size refers to 'heat', but the engine uses 'electricity'"]


def test_a_price_series_in_another_unit_is_reported():
    scenario = pv_and_grid()
    scenario["components"][1]["blocks"]["costs"] = {"variable_costs_series": "price"}
    scenario["series"]["price"] = {"unit": "ct per kWh", "values": [30.0] * 24}

    assert gaps_of(scenario) == ["'grid': the price series must be in € per kWh, not 'ct per kWh'"]


def test_all_gaps_are_reported_together_and_the_error_is_numbered():
    with pytest.raises(NotSupportedByEngine) as error:
        scenario_to_v1(EXAMPLES["hydrogen_chain"]())

    # the user-defined carrier and three custom components; what is inside a custom
    # component (on/off behaviour, the initial charge level) is not reported twice
    assert len(error.value.gaps) == 4
    assert str(error.value).startswith("The engine cannot run this scenario yet. (1) ")
    assert "(4) " in str(error.value) and "(5) " not in str(error.value)


def test_the_error_can_travel_between_processes():
    error = NotSupportedByEngine(["one", "two"])

    again = pickle.loads(pickle.dumps(error))

    assert again.gaps == ["one", "two"] and str(again) == str(error)


# ---------------------------------------------------------------------------
# there and back
# ---------------------------------------------------------------------------

def test_a_layout_2_scenario_survives_the_way_to_layout_1_and_back():
    original = EXAMPLES["pv_and_grid"]()

    assert scenario_from_v1(scenario_to_v1(original)) == original


def test_the_carriers_follow_the_components():
    new = scenario_from_v1(v1(["heat_demand", "gas_import", "gas_boiler"]))

    assert new.carrier_ids() == ["heat", "gas"]
    assert [c.label for c in new.carriers] == ["Heat", "Gas"]


def test_name_time_and_solver_are_carried_over():
    old = Scenario(name="My system", components=["demand"], time={"start": "2022-03-01T00:00:00", "steps": 48},
                   solver={"name": "cbc", "tee": True})

    new = scenario_from_v1(old)
    back = scenario_to_v1(new)

    assert (new.name, new.time.steps, new.solver.tee) == ("My system", 48, True)
    assert new.time.start.isoformat() == "2022-03-01T00:00:00"
    assert (back.name, back.time.steps, back.solver.tee) == ("My system", 48, True)