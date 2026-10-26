"""The yearly cost of an investment (annuity plus running cost), including 0 % interest."""

import pytest

from backend.oemof_components import calculate_epc
from backend.scenario import Scenario
from backend.service import run
from tests.helpers import needs_cbc


def annuity_factor(rate_percent, years):
    rate = rate_percent / 100
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def test_with_interest_the_cost_is_the_annuity_plus_the_running_cost():
    # 1200 EUR/kW over 25 years at 3 %, running cost 2 % of the investment
    expected = 1200 * annuity_factor(3, 25) + 0.02 * 1200

    assert calculate_epc(capex=1200.0, opex=2.0, lifetime=25.0, interest_rate=3.0) == pytest.approx(expected)


def test_without_interest_the_investment_is_spread_evenly():
    # 1200 / 25 years = 48 EUR per year, plus 2 % of 1200 = 24 EUR
    assert calculate_epc(capex=1200.0, opex=2.0, lifetime=25.0, interest_rate=0.0) == pytest.approx(72.0)


def test_zero_interest_fits_the_values_next_to_it():
    # no jump: the cost at 0 % is the limit of the cost at ever smaller rates
    at_zero = calculate_epc(1200.0, 2.0, 25.0, 0.0)
    nearly_zero = calculate_epc(1200.0, 2.0, 25.0, 1e-6)
    small = calculate_epc(1200.0, 2.0, 25.0, 0.5)

    assert nearly_zero == pytest.approx(at_zero, rel=1e-4)
    assert at_zero < small < calculate_epc(1200.0, 2.0, 25.0, 3.0)


def test_a_higher_interest_rate_costs_more_per_year():
    costs = [calculate_epc(1000.0, 1.0, 20.0, rate) for rate in (0.0, 1.0, 3.0, 8.0)]

    assert costs == sorted(costs)


def test_only_the_running_cost_remains_without_an_investment():
    assert calculate_epc(0.0, 2.0, 25.0, 0.0) == 0.0
    assert calculate_epc(0.0, 2.0, 25.0, 3.0) == 0.0


@needs_cbc
def test_a_whole_optimization_with_zero_interest_runs():
    # PV at 1 EUR/kW and no interest is worth building even for one day
    scenario = Scenario(
        components=["demand", "grid", "grid_feedin", "pv"],
        settings={
            "demand": {"scaling_factor": 10.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
            "grid_feedin": {"feedin_tariff": 0.05},
            "pv": {"mode": "invest", "capex": 1.0, "opex": 0.0, "lifetime": 20.0,
                   "interest_rate": 0.0, "maximum": 50.0},
        },
        time={"steps": 24},
        series={"electricity_demand": [1.0] * 24, "pv": [1.0] * 24},
    )

    result = run(scenario)

    capacities = result.capacities.to_frame()
    assert result.solver.termination == "optimal"
    assert capacities[capacities["Component"] == "PV"].iloc[0]["Capacity"] > 0