"""check and run for a layout 2 scenario."""

import pickle

import pytest

from backend import service, service_v2
from backend.scenario_convert import scenario_to_v1
from backend.scenario_v2 import ScenarioV2
from backend.service import ScenarioNotReady
from examples.make_examples_v2 import EXAMPLES
from tests.helpers import needs_cbc


def pv_and_grid(**changes):
    values = EXAMPLES["pv_and_grid"]().model_dump()
    values.update(changes)
    return values


def with_series(name, **changes):
    values = pv_and_grid()
    values["series"] = {**values["series"], name: {**values["series"][name], **changes}}
    return ScenarioV2(**values)


def levels(findings):
    return [f.level for f in findings]


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def test_a_scenario_that_is_fine_has_no_findings():
    assert service_v2.check(EXAMPLES["pv_and_grid"]()) == []


def test_what_the_engine_cannot_run_is_an_error_for_each_gap():
    found = service_v2.check(EXAMPLES["two_pv_systems"]())

    assert levels(found) == ["error"]
    assert found[0].message == "The engine can only run one PV system (found pv_south, pv_east)"


def test_the_hydrogen_chain_gives_one_error_for_each_thing_and_nothing_else():
    found = service_v2.check(EXAMPLES["hydrogen_chain"]())

    # the engine check is skipped when the scenario cannot be passed to the engine
    assert levels(found) == ["error"] * 4


def test_the_system_check_of_the_engine_is_part_of_the_answer():
    found = service_v2.check(with_series("electricity_demand", values=[0.01] * 10))

    assert levels(found) == ["error"]
    assert found[0].message.startswith("Electricity demand: the time series has 10 values")


def test_the_names_of_the_templates_are_the_default_labels_and_own_labels_win():
    scenario = with_series("electricity_demand", values=[0.01] * 10)

    assert service_v2.check(scenario)[0].message.startswith("Electricity demand:")
    assert service_v2.check(scenario, labels={"demand": "Strombedarf"})[0].message.startswith("Strombedarf:")
    assert service_v2.check(scenario, labels={"pv": "Dach"})[0].message.startswith("Electricity demand:")


def test_data_warnings_are_part_of_the_answer_and_do_not_block():
    found = service_v2.check(with_series("pv_profile", values=[5.0] * 24))

    assert levels(found) == ["warning"]
    assert "up to 5.00" in found[0].message


def test_errors_come_before_warnings_whatever_found_them():
    values = EXAMPLES["two_pv_systems"]().model_dump()
    values["series"]["pv_south_profile"]["values"] = [5.0] * 24                  # a warning from the data check
    values["series"]["electricity_demand"]["values"] = [0.01] * 10               # an error, from the engine check

    found = service_v2.check(ScenarioV2(**values))

    assert levels(found) == sorted(levels(found), key=lambda level: level != "error")
    assert found[0].level == "error" and found[-1].level == "warning"
    assert {"error", "warning"} <= set(levels(found))


def test_an_error_of_the_system_check_comes_before_a_data_warning():
    # without engine gaps the data warning is found first, the error after it
    values = pv_and_grid()
    values["series"]["pv_profile"]["values"] = [5.0] * 24                        # a warning from the data check
    values["series"]["electricity_demand"]["values"] = [0.01] * 10               # an error, from the system check

    found = service_v2.check(ScenarioV2(**values))

    assert levels(found) == ["error", "warning"]
    assert "10 values" in found[0].message and "up to 5.00" in found[1].message


def test_the_data_warnings_are_given_even_when_the_engine_cannot_run_the_scenario():
    values = EXAMPLES["two_pv_systems"]().model_dump()
    values["series"]["pv_east_profile"]["values"] = [5.0] * 24

    found = service_v2.check(ScenarioV2(**values))

    assert levels(found) == ["error", "warning"]


def test_checking_does_not_change_the_scenario():
    scenario = with_series("pv_profile", values=[5.0] * 24)
    before = scenario.model_dump()

    service_v2.check(scenario)

    assert scenario.model_dump() == before


# ---------------------------------------------------------------------------
# run (needs the CBC solver)
# ---------------------------------------------------------------------------

@needs_cbc
def test_run_gives_the_known_cost_of_the_example():
    # a day in which the optimizer builds no PV (the investment is counted for a whole year):
    # 10 kW on average for 24 hours at 0.30 EUR/kWh
    result = service_v2.run(EXAMPLES["pv_and_grid"]())

    assert result.solver.termination == "optimal"
    assert result.objective == pytest.approx(72.0)
    assert result.horizon_hours == 24


@needs_cbc
def test_run_gives_what_running_the_converted_scenario_gives():
    scenario = EXAMPLES["pv_and_grid"]()

    through = service_v2.run(scenario)
    direct = service.run(scenario_to_v1(scenario))

    assert through.objective == pytest.approx(direct.objective, rel=1e-12)
    assert through.model_dump(exclude={"solver"}) == direct.model_dump(exclude={"solver"})


@needs_cbc
def test_run_can_leave_out_the_hourly_flows():
    result = service_v2.run(EXAMPLES["pv_and_grid"](), include_flows=False)

    assert all(bus.flows is None for bus in result.buses.values())


@needs_cbc
def test_a_warning_does_not_stop_a_run():
    scenario = with_series("pv_profile", values=[5.0] * 24)

    assert levels(service_v2.check(scenario)) == ["warning"]
    assert service_v2.run(scenario).solver.termination == "optimal"


def test_run_refuses_what_the_engine_cannot_run_and_says_what():
    with pytest.raises(ScenarioNotReady) as error:
        service_v2.run(EXAMPLES["two_pv_systems"]())

    assert all(f.level == "error" for f in error.value.findings)
    assert "The engine can only run one PV system" in str(error.value)


def test_run_refuses_a_mistake_found_by_the_system_check_before_the_solver_starts():
    with pytest.raises(ScenarioNotReady, match="has 10 values"):
        service_v2.run(with_series("electricity_demand", values=[0.01] * 10))


def test_the_refusal_can_travel_between_processes():
    with pytest.raises(ScenarioNotReady) as error:
        service_v2.run(EXAMPLES["hydrogen_chain"]())

    again = pickle.loads(pickle.dumps(error.value))

    assert [f.message for f in again.findings] == [f.message for f in error.value.findings]