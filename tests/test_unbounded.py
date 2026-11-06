"""A plant that is built without end: found before the run (an error), and in step with the real solvers."""

import math
import random
import shutil

import pytest

from backend import service, service_v2, solving
from backend.i18n import Translator
from backend.findings import finding_text
from backend.oemof_components import calculate_epc
from backend.scenario_checks import check_unbounded
from backend.scenario_convert import scenario_to_v1
from backend.scenario_v2 import SeriesData
from backend.service import ScenarioError, ScenarioNotReady
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.forms import set_value

DE = Translator("de")

needs_a_solver = pytest.mark.skipif(
    not (solving.highs_available() or shutil.which("cbc")), reason="neither HiGHS nor CBC is installed"
)

SUN = [max(0.0, math.sin((h - 6) / 12 * math.pi)) for h in range(24)]     # a day of sun: 7.6 full-load hours
WIND = [0.3 + 0.2 * math.sin(h / 4) for h in range(24)]                    # 7.2 full-load hours


def plant_scenario(key="pv", revenue=0.1, capex=1.0, opex=0.0, maximum=None, mode="invest", feedin=True,
                   profile=None, steps=24):
    """A demand, the grid, a plant (PV or wind) and maybe the feed-in, for `steps` hours."""

    draft = ScenarioDraft(steps=steps)
    draft.apply_template("PV system" if key == "pv" else "PV + wind")
    draft.set("grid_feedin", feedin)

    for other in ("pv", "wind"):
        if other != key and draft.is_selected(other):
            set_value(draft.component(other), "capacity", "capacity", 5.0)       # the other plant has a fixed size

    plant = draft.component(key)
    set_value(plant, "capacity", "mode", mode)
    if mode == "invest":
        set_value(plant, "capacity", "capex", capex)
        set_value(plant, "capacity", "opex", opex)
        if maximum is not None:
            set_value(plant, "capacity", "maximum", maximum)
    else:
        set_value(plant, "capacity", "capacity", 5.0)
        plant.blocks["capacity"].update(capex=capex, opex=opex)             # cheap, so that only the mode protects it

    if feedin and revenue is not None:
        set_value(draft.component("grid_feedin"), "costs", "revenue", revenue)
    elif feedin:
        draft.component("grid_feedin").blocks["costs"].pop("revenue", None)

    draft.set_series("demand", SeriesData(values=[1 / steps] * steps))
    draft.set_series("pv", SeriesData(values=(profile or SUN) if key == "pv" else SUN))
    if draft.is_selected("wind"):
        draft.set_series("wind", SeriesData(values=WIND))

    return draft.scenario()


def codes(scenario):
    return [f.code for f in check_unbounded(scenario)]


# ---------------------------------------------------------------------------
# when it is found
# ---------------------------------------------------------------------------

def test_a_plant_without_an_upper_limit_that_earns_more_than_it_costs_is_an_error():
    scenario = plant_scenario(capex=1.0, revenue=0.1)               # 0.1 EUR/kWh x 7.6 kWh = 0.76 against 0.06 a year

    (finding,) = check_unbounded(scenario)

    assert (finding.level, finding.code) == ("error", "unbounded_plant")


def test_the_gain_is_what_the_feed_in_earns_for_one_kw_minus_what_it_costs():
    scenario = plant_scenario(capex=10.0, opex=2.0, revenue=0.5)
    expected = 0.5 * sum(SUN) - calculate_epc(10.0, 2.0, 25.0, 3.0)         # the defaults: 25 years, 3 %

    (finding,) = check_unbounded(scenario)

    assert finding.params["margin"].value == pytest.approx(expected) and finding.params["margin"].decimals == 2
    assert finding.params["revenue"] == 0.5


def test_wind_is_found_too_and_each_plant_is_named():
    scenario = plant_scenario(key="wind", capex=1.0, revenue=0.1)
    pv = next(c for c in scenario.components if c.id == "pv")
    pv.blocks["capacity"].update(mode="invest", capex=1.0, opex=0.0, lifetime=25.0, interest_rate=3.0)

    found = check_unbounded(scenario)

    assert len(found) == 2 and {f.params["component"].key for f in found} == {"pv", "wind"}


def test_the_boundary_is_the_break_even_of_the_plant():
    epc = calculate_epc(1200.0, 0.0, 25.0, 3.0)
    output = sum(SUN)

    earns_more = plant_scenario(capex=1200.0, revenue=(epc + 0.05) / output)
    earns_less = plant_scenario(capex=1200.0, revenue=(epc - 0.05) / output)

    assert codes(earns_more) == ["unbounded_plant"] and codes(earns_less) == []


def test_only_the_values_of_the_simulated_period_count():
    # a profile of two days for a scenario of one day: the second day does not pay for the plant
    epc = calculate_epc(1200.0, 0.0, 25.0, 3.0)
    scenario = plant_scenario(capex=1200.0, revenue=(epc + 0.05) / sum(SUN), profile=SUN + SUN)

    assert codes(scenario) == ["unbounded_plant"]
    scenario = plant_scenario(capex=1200.0, revenue=(epc - 0.05) / sum(SUN), profile=SUN + SUN)
    assert codes(scenario) == []


def test_empty_values_of_the_profile_do_not_count():
    scenario = plant_scenario(capex=1.0, revenue=0.1, profile=[None] * 20 + [1.0, 1.0, 1.0, 1.0])

    assert codes(scenario) == ["unbounded_plant"]                    # 4 kWh x 0.1 = 0.4 against 0.06


# ---------------------------------------------------------------------------
# when it is not found
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("what, scenario", [
    ("an upper limit", plant_scenario(maximum=50.0)),
    ("a fixed size", plant_scenario(mode="fixed")),
    ("no feed-in", plant_scenario(feedin=False)),
    ("a feed-in without revenue", plant_scenario(revenue=0.0)),
    ("a feed-in whose revenue is not filled in", plant_scenario(revenue=None)),
    ("a plant that costs more than it earns", plant_scenario(capex=1200.0, revenue=0.078)),
    ("a profile of zeros", plant_scenario(profile=[0.0] * 24)),
])
def test_it_is_no_trap(what, scenario):
    assert codes(scenario) == [], what


def test_an_upper_limit_of_zero_is_a_limit():
    # the model is bounded: the plant cannot be built at all
    assert codes(plant_scenario(maximum=0.0)) == []


def test_a_plant_without_its_profile_or_its_costs_is_left_to_the_other_checks():
    scenario = plant_scenario(capex=1.0, revenue=0.1)
    pv = next(c for c in scenario.components if c.id == "pv")

    pv.blocks["capacity"].pop("lifetime")
    assert codes(scenario) == []

    pv.blocks["capacity"]["lifetime"] = 25.0
    pv.blocks["profile"].pop("series")
    assert codes(scenario) == []

    pv.blocks["capacity"]["lifetime"] = 0.0                         # (the form refuses it, a file could hold it)
    pv.blocks["profile"]["series"] = "pv_profile"
    assert codes(scenario) == []


# ---------------------------------------------------------------------------
# what the user is told, and what it stops
# ---------------------------------------------------------------------------

def test_the_finding_is_worded_in_both_languages():
    scenario = plant_scenario(capex=1.0, revenue=0.1)
    (finding,) = check_unbounded(scenario)

    english, german = finding_text(finding, Translator("en")), finding_text(finding, DE)

    assert english.startswith("PV system: without an upper limit this plant earns more from feeding in than it costs (")
    assert "EUR per kW in the simulated period at a feed-in revenue of 0.1 EUR/kWh" in english
    assert english.endswith("Set an upper limit for the plant or lower the feed-in revenue.")
    assert german.startswith("PV-Anlage: Ohne Obergrenze verdient diese Anlage mit der Einspeisung mehr, als sie kostet (")
    assert "€ je kW im simulierten Zeitraum bei einer Einspeisevergütung von 0,1 €/kWh" in german
    assert german.endswith("Setzen Sie eine Obergrenze für die Anlage oder senken Sie die Einspeisevergütung.")
    assert finding.message == english and "{" not in german


def test_the_system_check_of_the_scenario_has_it_and_it_stops_the_run():
    scenario = plant_scenario(capex=1.0, revenue=0.1)

    assert "unbounded_plant" in [f.code for f in service_v2.check(scenario) if f.level == "error"]
    with pytest.raises(ScenarioNotReady) as raised:
        service_v2.run(scenario)

    assert "without an upper limit this plant earns more" in str(raised.value)


def test_a_limit_lets_the_run_through_the_check():
    scenario = plant_scenario(capex=1.0, revenue=0.1, maximum=50.0)

    assert not [f for f in service_v2.check(scenario) if f.level == "error"]


# ---------------------------------------------------------------------------
# in step with the solvers
# ---------------------------------------------------------------------------

def ended_unbounded(scenario):
    """True if the solver ends with 'unbounded' (HiGHS sometimes only says 'unknown'), False if it finds an optimum."""

    try:
        service.run(scenario_to_v1(scenario), check_first=False)
    except ScenarioError as error:
        assert error.termination in ("unbounded", "unknown", "infeasibleOrUnbounded"), error
        return True

    return False


TRAPS = ("unbounded_plant", "feedin_above_price")       # the two ways to an optimization without an end


@needs_a_solver
def test_the_checks_and_the_solver_agree_on_random_systems():
    # the solver ends 'unbounded' exactly when one of the two checks finds a trap: a plant that earns more than it
    # costs (this module), or a feed-in tariff above the price of the grid (buy and sell for ever; system_check.py)
    rng = random.Random(7)
    plant_traps, price_traps, fine = 0, 0, 0

    for _ in range(50):
        key = rng.choice(["pv", "wind"])
        revenue = round(rng.uniform(0.01, 0.4), 3)                # the grid costs 0.30: above it is the second trap
        capex = round(rng.choice([0.2, 1.0, 5.0, 40.0, 400.0, 1200.0]) * rng.uniform(0.5, 1.5), 2)
        maximum = rng.choice([None, None, 50.0])
        scenario = plant_scenario(key=key, revenue=revenue, capex=capex, opex=rng.choice([0.0, 2.0]), maximum=maximum)
        found = {f.code for f in service_v2.check(scenario) if f.level == "error"}

        assert ended_unbounded(scenario) == bool(found & set(TRAPS)), (key, revenue, capex, maximum, found)
        plant_traps += "unbounded_plant" in found
        price_traps += "feedin_above_price" in found
        fine += not (found & set(TRAPS))

    assert plant_traps >= 6 and price_traps >= 6 and fine >= 8        # every kind was really tried


@needs_a_solver
def test_a_system_that_the_check_lets_through_has_a_result():
    scenario = plant_scenario(capex=1.0, revenue=0.1, maximum=50.0)

    result = service_v2.run(scenario)

    sizes = {row[0]: row[2] for row in result.capacities.rows}
    assert result.solver.termination == "optimal"
    assert sizes["PV"] == pytest.approx(50.0)                                    # it is built, up to its limit