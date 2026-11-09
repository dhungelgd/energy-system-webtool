"""The warning for components in investment mode when the period is shorter than a year."""

from backend import service_v2
from backend.findings import finding_text
from backend.i18n import Translator
from backend.scenario_checks import NEARLY_FULL_YEAR, check_period
from backend.scenario_v2 import SeriesData
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.forms import set_value

DE = Translator("de")
EN = Translator("en")


def scenario_of(steps, invest=("pv",)):
    """A PV system with demand and grid for `steps` hours; the components in `invest` are in investment mode."""

    draft = ScenarioDraft(steps=steps)
    draft.apply_template("PV + wind")
    for key in invest:
        set_value(draft.component(key), "capacity", "mode", "invest")
    for key in ("pv", "wind"):
        if key not in invest:
            set_value(draft.component(key), "capacity", "capacity", 5.0)

    draft.set_series("demand", SeriesData(values=[1 / steps] * steps))
    draft.set_series("pv", SeriesData(values=[0.5] * steps))
    draft.set_series("wind", SeriesData(values=[0.3] * steps))

    return draft.scenario()


def test_a_component_in_investment_mode_in_a_period_shorter_than_a_year_gets_a_warning():
    (finding,) = check_period(scenario_of(168))

    assert (finding.level, finding.code) == ("warning", "short_period_invest")
    assert finding.params["n"] == 1


def test_the_boundary_is_the_whole_year_as_the_key_figures_of_the_backend_count_it():
    assert NEARLY_FULL_YEAR == 8700

    assert check_period(scenario_of(NEARLY_FULL_YEAR - 1)) and not check_period(scenario_of(NEARLY_FULL_YEAR))
    assert not check_period(scenario_of(8760)) and not check_period(scenario_of(8784))


def test_no_investment_no_warning():
    assert check_period(scenario_of(24, invest=())) == []


def test_every_component_in_investment_mode_is_named_and_the_text_follows_the_number():
    (finding,) = check_period(scenario_of(24, invest=("pv", "wind")))

    assert finding.params["n"] == 2 and len(finding.params["components"]) == 2
    assert finding.message == (
        "PV system and Wind turbine are in investment mode, but the scenario covers less than a year. Their sizes are "
        "only reliable for a whole year: the seasons differ, and the yearly cost of a plant is not scaled to a shorter period.")
    assert finding_text(finding, DE) == (
        "PV-Anlage und Windkraftanlage sind im Investitionsmodus, aber das Szenario umfasst weniger als ein Jahr. Die "
        "Größen sind nur für ein ganzes Jahr verlässlich: Die Jahreszeiten unterscheiden sich, und die Jahreskosten einer "
        "Anlage werden nicht auf einen kürzeren Zeitraum umgerechnet.")


def test_one_component_gets_the_singular():
    (finding,) = check_period(scenario_of(24, invest=("wind",)))

    assert finding.message.startswith("Wind turbine is in investment mode, but the scenario covers less than a year. Its size")
    assert finding_text(finding, DE).startswith("Windkraftanlage ist im Investitionsmodus, aber das Szenario umfasst weniger")
    assert "Die Größe ist nur" in finding_text(finding, DE)


def test_the_system_check_has_the_warning_and_it_does_not_stop_the_run():
    scenario = scenario_of(168)

    findings = service_v2.check(scenario)

    assert [f.level for f in findings if f.code == "short_period_invest"] == ["warning"]
    assert not [f for f in findings if f.level == "error"]


def test_a_whole_year_has_no_such_warning_in_the_check():
    assert "short_period_invest" not in [f.code for f in service_v2.check(scenario_of(8760))]