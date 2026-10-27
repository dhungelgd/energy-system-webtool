"""The catalog of capability blocks and the checks of their settings."""

import pytest

from backend.blocks import BLOCKS, conversion_problems, series_references
from backend.component_specs import PV


def problems(block, values, owner="x"):
    return BLOCKS[block].problems(values, owner)


# ---------------------------------------------------------------------------
# the catalog itself
# ---------------------------------------------------------------------------

def test_the_blocks_and_the_kinds_that_may_have_them():
    assert {name: set(block.kinds) for name, block in BLOCKS.items()} == {
        "capacity": {"source", "sink", "converter", "storage"},
        "profile": {"source"},
        "demand": {"sink"},
        "costs": {"source", "sink", "converter"},
        "conversion": {"converter"},
        "storage": {"storage"},
        "on_off": {"source", "converter"},
    }


def test_only_the_on_off_block_is_not_supported_by_the_engine_yet():
    assert [name for name, block in BLOCKS.items() if not block.engine_supported] == ["on_off"]


def test_the_capacity_block_has_exactly_the_settings_of_the_pv_plant():
    assert BLOCKS["capacity"].fields == PV.fields


def test_every_block_and_setting_has_a_label_and_a_help_text_in_sentence_case():
    for block in BLOCKS.values():
        assert block.help, block.name
        for text in [block.label] + [f.label for f in block.fields]:
            first, *rest = text.split()
            assert first[0].isupper(), text
            assert all(word.islower() or word.isupper() for word in rest), text
        for field in block.fields:
            assert field.help, f"{block.name}.{field.key}"


def test_every_number_has_a_unit_and_a_minimum():
    for block in BLOCKS.values():
        for field in block.fields:
            if field.kind == "number":
                assert field.unit and field.minimum is not None, f"{block.name}.{field.key}"


def test_every_percentage_is_stored_as_a_percentage_between_0_and_100():
    percent_fields = [
        (block.name, field)
        for block in BLOCKS.values() for field in block.fields if "%" in field.unit
    ]

    assert {f.key for _, f in percent_fields} >= {
        "opex", "interest_rate", "efficiency_charge", "efficiency_discharge",
        "loss_rate", "initial_level", "minimum_load",
    }
    for name, field in percent_fields:
        assert field.minimum == 0 and field.maximum == 100, f"{name}.{field.key}"


# ---------------------------------------------------------------------------
# what is refused
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("block, values, text", [
    ("storage", {"efficiency_charge": 101}, "Charging efficiency must be at most 100 %"),
    ("storage", {"efficiency_discharge": -1}, "Discharging efficiency must be at least 0 %"),
    ("storage", {"loss_rate": 101}, "Self-discharge must be at most 100 % per hour"),
    ("storage", {"initial_level": 120}, "Initial charge level must be at most 100 % of the capacity"),
    ("storage", {"c_rate": -0.5}, "Charge and discharge power must be at least 0"),
    ("on_off", {"minimum_load": 150}, "Minimum load must be at most 100 % of the size"),
    ("on_off", {"startup_cost": -5}, "Start-up cost must be at least 0 € per start"),
    ("on_off", {"minimum_uptime": -1}, "Minimum run time must be at least 0 hours"),
    ("demand", {"annual_demand": -5}, "Annual demand must be at least 0 kWh per year"),
    ("demand", {"profile_type": "peak"}, "What does the profile hold? must be one of: annual_share, absolute"),
    ("costs", {"variable_costs": -0.1}, "Variable costs must be at least 0 € per kWh"),
    ("costs", {"revenue": -0.1}, "Revenue must be at least 0 € per kWh"),
    ("capacity", {"mode": "invest", "interest_rate": 250}, "Interest rate must be at most 100"),
])
def test_values_outside_the_range_are_named(block, values, text):
    found = problems(block, values)

    assert len(found) == 1
    assert text in found[0]


def test_good_settings_have_no_problems():
    assert problems("storage", {"c_rate": 0.5, "efficiency_charge": 95, "efficiency_discharge": 95,
                                "loss_rate": 0.1, "initial_level": 50}) == []
    assert problems("capacity", {"mode": "invest", "maximum": 40, "capex": 1200, "opex": 2,
                                 "lifetime": 25, "interest_rate": 0}) == []
    assert problems("demand", {"series": "d", "profile_type": "annual_share", "annual_demand": 30000}) == []
    assert problems("demand", {"series": "d", "profile_type": "absolute"}) == []


def test_empty_values_are_not_wrong():
    assert problems("storage", {"efficiency_charge": None, "initial_level": None}) == []
    assert problems("capacity", {"mode": "invest", "capex": None}) == []


def test_text_and_yes_no_are_not_numbers():
    assert "must be a number" in problems("storage", {"c_rate": "fast"})[0]
    assert "must be a number" in problems("storage", {"c_rate": True})[0]


def test_an_unknown_setting_is_named_with_the_owner_and_the_block():
    assert problems("storage", {"colour": "blue"}, owner="h2_tank") == [
        "h2_tank: Storage: unknown setting 'colour'"
    ]


def test_a_series_setting_must_be_the_id_of_a_series():
    assert problems("profile", {"series": "pv_profile"}) == []
    assert "id of a time series" in problems("profile", {"series": 5})[0]


def test_hidden_settings_are_not_checked():
    assert problems("capacity", {"mode": "fixed", "capacity": 10, "capex": -50}) == []
    assert problems("capacity", {"mode": "invest", "capex": -50})


def test_a_normalized_demand_profile_is_the_default_and_asks_for_the_annual_demand():
    demand = BLOCKS["demand"]

    assert demand.defaults() == {"profile_type": "annual_share"}
    assert [f.key for f in demand.visible_fields({})] == ["profile_type", "annual_demand"]
    assert [f.key for f in demand.visible_fields({"profile_type": "absolute"})] == ["profile_type"]


def test_the_annual_demand_is_not_checked_when_the_profile_is_absolute():
    assert problems("demand", {"profile_type": "absolute", "annual_demand": -5}) == []
    assert problems("demand", {"profile_type": "annual_share", "annual_demand": -5})


# ---------------------------------------------------------------------------
# the conversion block
# ---------------------------------------------------------------------------

def conversion(values, outputs=("hydrogen",)):
    return conversion_problems(values, set(outputs), "x")


def test_an_efficiency_a_ratio_and_a_ratio_series_are_accepted():
    assert conversion({"outputs": {"hydrogen": {"efficiency": 65}}}) == []
    assert conversion({"outputs": {"heat": {"ratio": 3.5}}}, outputs=("heat",)) == []
    assert conversion({"outputs": {"heat": {"ratio_series": "cop"}}}, outputs=("heat",)) == []
    assert conversion({}) == []
    assert conversion({"outputs": {"hydrogen": {}}}) == []


def test_efficiencies_of_a_chp_plant_are_accepted_when_they_add_up_to_at_most_100():
    chp = {"outputs": {"electricity": {"efficiency": 35}, "heat": {"efficiency": 50}}}

    assert conversion(chp, outputs=("electricity", "heat")) == []


def test_efficiencies_that_add_up_to_more_than_100_are_refused():
    chp = {"outputs": {"electricity": {"efficiency": 60}, "heat": {"efficiency": 50}}}

    found = conversion(chp, outputs=("electricity", "heat"))

    assert len(found) == 1 and "cannot exceed 100 %" in found[0]


def test_a_ratio_does_not_count_towards_the_100_percent():
    mixed = {"outputs": {"electricity": {"efficiency": 40}, "heat": {"ratio": 3.0}}}

    assert conversion(mixed, outputs=("electricity", "heat")) == []


@pytest.mark.parametrize("values, text", [
    ({"outputs": {"ghost": {"efficiency": 65}}}, "does not give energy to 'ghost'"),
    ({"outputs": {"hydrogen": {"efficiency": 65, "ratio": 2}}}, "give only one of"),
    ({"outputs": {"hydrogen": {"efficiency": 0}}}, "above 0 and at most 100 %"),
    ({"outputs": {"hydrogen": {"efficiency": 101}}}, "above 0 and at most 100 %"),
    ({"outputs": {"hydrogen": {"ratio": 0}}}, "ratio must be above 0"),
    ({"outputs": {"hydrogen": {"efficiency": "high"}}}, "efficiency must be a number"),
    ({"outputs": {"hydrogen": {"ratio_series": 3}}}, "id of a time series"),
    ({"outputs": {"hydrogen": {"cop": 3}}}, "unknown setting 'cop'"),
    ({"outputs": {"hydrogen": 65}}, "expected one of"),
    ({"outputs": [65]}, "'outputs' must list a value for each output carrier"),
    ({"efficiency": 65}, "unknown setting 'efficiency'"),
])
def test_conversion_mistakes_are_named(values, text):
    found = conversion(values)

    assert len(found) == 1
    assert text in found[0]


# ---------------------------------------------------------------------------
# which time series a block refers to
# ---------------------------------------------------------------------------

def test_series_references():
    assert series_references("profile", {"series": "pv_profile"}) == ["pv_profile"]
    assert series_references("demand", {"series": "load", "profile_type": "absolute"}) == ["load"]
    assert series_references("costs", {"variable_costs_series": "price"}) == ["price"]
    assert series_references("conversion", {"outputs": {"heat": {"ratio_series": "cop"}}}) == ["cop"]
    assert series_references("capacity", {"mode": "fixed"}) == []
    assert series_references("profile", {"series": None}) == []