"""The tabs of a result on the NiceGUI page: carriers, costs, capacities; in both languages (simulated user)."""

import datetime
import shutil

import pytest

pytest.importorskip("nicegui")
from nicegui import ElementFilter, ui  # noqa: E402
from nicegui.testing import User  # noqa: E402

from backend.results import (  # noqa: E402
    BusSummary,
    FlowTable,
    KeyFigure,
    ScenarioResult,
    SolverInfo,
    Table,
)
from backend.solving import highs_available  # noqa: E402
from tests.test_nicegui_draft_run import (  # noqa: E402
    PRICE,
    build_draft,
    exists,
    field,
    give_demand,
    open_example,
    run_button,
    settle,
    switched_to,
    use_solver,
)

needs_a_solver = pytest.mark.skipif(shutil.which("cbc") is None and not highs_available(), reason="no solver is installed")

START = datetime.datetime(2021, 1, 1)
ENERGY = ["Component", "Energy (kWh)", "Share (%)"]


def rich_result(horizon=24.0, with_flows=True, costs=True, capacities=True):
    """A result by hand: electricity (supply, use, flows), heat, and a gas bus through which nothing flows."""

    def table(rows):
        return Table(columns=ENERGY, rows=rows)

    def flows(columns):
        names = list(columns)
        return FlowTable(start=START, step_hours=1.0, columns=names, values=[columns[n] for n in names]) if with_flows else None

    electricity = BusSummary(
        energy_sums={}, flows=flows({
            "grid_import-->electricity": [4.0, 2.0, 0.0], "pv-->electricity": [0.0, 1.0, 3.0],
            "electricity-->demand": [3.0, 2.0, 1.0], "electricity-->heating_rod": [1.0, 1.0, 0.0],
            "electricity-->grid_feedin": [0.0, 0.0, 2.0],
        }),
        supply=table([["Grid import", 6000.0, 60.0], ["PV", 4000.0, 40.0]]),
        use=table([["Electricity demand", 6000.0, 60.0], ["Heating rod", 2000.0, 20.0], ["Grid feed-in", 2000.0, 20.0]]),
    )
    heat = BusSummary(
        energy_sums={}, flows=flows({"heating_rod-->heat": [1.0, 1.0, 0.0], "heat-->heat_demand": [1.0, 1.0, 0.0]}),
        supply=table([["Heating rod", 2000.0, 100.0]]), use=table([["Heat demand", 2000.0, 100.0]]),
    )
    gas = BusSummary(
        energy_sums={}, flows=flows({"gas_import-->gas": [0.0, 0.0, 0.0], "gas-->chp": [0.0, 0.0, 0.0]}),
        supply=table([["Gas import", 0.0, 0.0]]), use=table([["CHP plant", 0.0, 0.0]]),
    )

    return ScenarioResult(
        objective=55353.0, horizon_hours=horizon,
        solver=SolverInfo(status="ok", termination="optimal", seconds=1.5, name="highs"),
        key_figures=[
            KeyFigure(label="System cost (simulated period)", value=55353.0, unit="€",
                      help="Objective of the optimization: annualised investment and fixed O&M plus energy costs, minus "
                           "feed-in revenue. Negative means a net revenue."),
            KeyFigure(label="Grid import", value=6000.0, unit="kWh", help="Electricity bought from the grid."),
        ],
        cost_breakdown=Table(columns=["Item", "Category", "Cost (€)"], rows=[
            ["Heating rod", "Investment and fixed O&M", 19080.3], ["Grid import", "Energy purchase", 36272.7],
            ["Grid feed-in", "Revenue", -500.0]] if costs else []),
        capacities=Table(columns=["Component", "Mode", "Capacity", "Unit", "Annualised cost (€/a)"], rows=[
            ["PV", "fixed (input)", 5.0, "kW", 0.0], ["Heating rod", "optimized", 2471.04, "kW (heat)", 19080.3],
            ["Battery", "optimized", 0.0, "kWh", 0.0]] if capacities else []),
        buses={"electricity": electricity, "heat": heat, "gas": gas},
    )


def label_of(user, marker):
    return field(user, marker).props["label"]


def table_cells(user, marker):
    return [list(row.values()) for row in field(user, marker).rows]


async def show(user, monkeypatch, result, language=None):
    async def solver(scenario):
        return result

    use_solver(monkeypatch, solver)
    await build_draft(user, language=language)
    user.find(marker="draft-run").click()
    await user.should_see(marker="draft-tab-costs")


# ---------------------------------------------------------------------------
# the tabs
# ---------------------------------------------------------------------------

async def test_a_result_has_a_tab_for_each_energy_carrier_the_costs_and_the_capacities(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())

    assert [label_of(user, f"draft-tab-{name}") for name in ("bus-electricity", "bus-heat", "bus-gas", "costs", "capacities")] == [
        "Electricity", "Heat", "Gas", "Costs", "Capacities"]
    with user.client:
        labels = [e.props["label"] for e in ElementFilter(kind=ui.tab)]
    # the three views of the page have tabs too: System, Check, Results
    assert labels.count("Electricity") == labels.count("Costs") == 1 and len(labels) == 3 + 5


async def test_the_tabs_are_in_german(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(), language="de")

    assert [label_of(user, f"draft-tab-{name}") for name in ("bus-electricity", "bus-heat", "bus-gas", "costs", "capacities")] == [
        "Strom", "Wärme", "Gas", "Kosten", "Größen"]


async def test_the_headline_figures_and_their_help_are_translated(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(), language="de")

    await user.should_see("Systemkosten (simulierter Zeitraum)")
    await user.should_see("Netzbezug")
    await user.should_see("Strom, der aus dem Netz bezogen wird.")


# ---------------------------------------------------------------------------
# an energy carrier
# ---------------------------------------------------------------------------

async def test_the_tab_of_a_carrier_has_the_flows_the_two_tables_and_the_sankey_diagram(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())

    flows = field(user, "draft-flows-electricity").figure
    assert [trace.name for trace in flows.data] == ["Grid import", "PV", "Demand", "Grid feed-in", "Heating rod"]
    assert table_cells(user, "draft-supply-electricity") == [["Grid import", "6,000", "60.0"], ["PV", "4,000", "40.0"]]
    assert table_cells(user, "draft-use-electricity") == [
        ["Electricity demand", "6,000", "60.0"], ["Heating rod", "2,000", "20.0"], ["Grid feed-in", "2,000", "20.0"]]
    assert [c["label"] for c in field(user, "draft-supply-electricity").columns] == ["Component", "Energy (kWh)", "Share (%)"]
    sankey = field(user, "draft-sankey-electricity").figure.data[0]
    assert list(sankey.node.label) == ["Grid import", "PV", "Electricity", "Electricity demand", "Heating rod", "Grid feed-in"]
    await user.should_see("Energy flows")
    await user.should_see("Supply and use")


async def test_the_tab_of_a_carrier_is_in_german_with_numbers_the_german_way(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(), language="de")

    assert [t.name for t in field(user, "draft-flows-electricity").figure.data] == [
        "Netzbezug", "PV-Anlage", "Bedarf", "Netzeinspeisung", "Heizstab"]
    assert table_cells(user, "draft-supply-electricity") == [["Netzbezug", "6.000", "60,0"], ["PV-Anlage", "4.000", "40,0"]]
    assert [c["label"] for c in field(user, "draft-use-electricity").columns] == ["Bauteil", "Energie (kWh)", "Anteil (%)"]
    assert list(field(user, "draft-sankey-electricity").figure.data[0].node.label)[:3] == ["Netzbezug", "PV-Anlage", "Strom"]
    await user.should_see("Energieflüsse")
    await user.should_see("Bereitstellung und Verwendung")
    await user.should_see("Sankey-Diagramm")


async def test_a_carrier_through_which_nothing_flows_says_so_instead_of_an_empty_chart(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())

    assert exists(user, "draft-nothing-flows-gas") and not exists(user, "draft-flows-gas")
    assert not exists(user, "draft-sankey-gas")
    await user.should_see("Nothing flows through this energy carrier in this run.")
    assert exists(user, "draft-flows-heat") and exists(user, "draft-sankey-heat")


async def test_a_result_without_hourly_flows_says_so_and_still_has_the_tables_and_the_diagram(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(with_flows=False))

    assert exists(user, "draft-no-flows-electricity") and not exists(user, "draft-flows-electricity")
    await user.should_see("This result has no hourly flows.")
    assert exists(user, "draft-supply-electricity") and exists(user, "draft-sankey-electricity")


# ---------------------------------------------------------------------------
# costs and capacities
# ---------------------------------------------------------------------------

async def test_the_costs_tab_has_the_chart_and_the_table(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())

    chart = field(user, "draft-cost-chart").figure
    assert {trace.name for trace in chart.data} == {"Investment and fixed O&M", "Energy purchase", "Revenue"}
    assert table_cells(user, "draft-costs-table") == [
        ["Heating rod", "Investment and fixed O&M", "19,080"], ["Grid import", "Energy purchase", "36,273"],
        ["Grid feed-in", "Revenue", "-500"]]
    await user.should_see("Where the system cost comes from")


async def test_the_costs_tab_is_in_german(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(), language="de")

    assert table_cells(user, "draft-costs-table") == [
        ["Heizstab", "Investition und feste Betriebskosten", "19.080"], ["Netzbezug", "Energiebezug", "36.273"],
        ["Netzeinspeisung", "Erlös", "-500"]]
    assert {t.name for t in field(user, "draft-cost-chart").figure.data} == {
        "Investition und feste Betriebskosten", "Energiebezug", "Erlös"}
    await user.should_see("Woher die Systemkosten kommen")


async def test_the_capacities_tab_has_the_table_and_the_note_for_fixed_sizes(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())

    assert table_cells(user, "draft-capacities-table") == [
        ["PV", "fixed (input)", "5.0", "kW", "0"], ["Heating rod", "optimized", "2,471.0", "kW (heat)", "19,080"],
        ["Battery", "optimized", "0.0", "kWh", "0"]]
    await user.should_see("Components in fixed mode have no capital cost in the optimization.")


async def test_the_capacities_tab_is_in_german(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(), language="de")

    assert table_cells(user, "draft-capacities-table") == [
        ["PV-Anlage", "fest (Eingabe)", "5,0", "kW", "0"], ["Heizstab", "optimiert", "2.471,0", "kW (Wärme)", "19.080"],
        ["Batteriespeicher", "optimiert", "0,0", "kWh", "0"]]
    await user.should_see("Bauteile mit fester Größe haben in der Optimierung keine Kapitalkosten.")


async def test_a_result_without_costs_or_capacities_says_so(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(costs=False, capacities=False))

    await user.should_see("No cost items in this run.")
    await user.should_see("No components with a capacity in this system.")
    assert not exists(user, "draft-cost-chart") and not exists(user, "draft-fixed-note")


async def test_no_note_about_fixed_sizes_when_no_size_is_fixed(user: User, monkeypatch):
    result = rich_result()
    result.capacities.rows[0][1] = "optimized"

    await show(user, monkeypatch, result)

    assert not exists(user, "draft-fixed-note")


# ---------------------------------------------------------------------------
# the note for a period shorter than a year
# ---------------------------------------------------------------------------

async def test_a_period_shorter_than_a_year_gets_the_note_and_a_year_does_not(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(horizon=168.0))

    await user.should_see("The simulated period is 7 days.")
    assert exists(user, "draft-period-note")


async def test_the_note_is_in_german(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(horizon=24.0), language="de")

    await user.should_see("Der simulierte Zeitraum beträgt 1 Tag.")


async def test_a_whole_year_has_no_note(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result(horizon=8760.0))

    assert not exists(user, "draft-period-note")


# ---------------------------------------------------------------------------
# language, the opened file, and what is drawn again
# ---------------------------------------------------------------------------

async def test_the_result_stays_when_the_language_changes_and_the_tabs_follow(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())
    assert label_of(user, "draft-tab-bus-electricity") == "Electricity"

    await switched_to(user, "de")

    assert label_of(user, "draft-tab-bus-electricity") == "Strom"
    assert table_cells(user, "draft-supply-electricity")[0][0] == "Netzbezug"
    await user.should_see("Systemkosten (simulierter Zeitraum)")


async def test_the_result_of_an_opened_file_has_its_own_tabs_next_to_those_of_the_draft(user: User, monkeypatch):
    results = iter([rich_result(), rich_result(horizon=168.0)])

    async def solver(scenario):
        return next(results)

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see(marker="draft-tab-costs")

    await open_example(user, "pv_and_grid")
    user.find(marker="run").click()
    await user.should_see(marker="file-tab-costs")

    assert exists(user, "draft-flows-electricity") and exists(user, "file-flows-electricity")
    assert exists(user, "draft-cost-chart") and exists(user, "file-cost-chart")
    assert field(user, "draft-period-note").text.startswith("The simulated period is 1 day.")      # each has its own
    assert field(user, "file-period-note").text.startswith("The simulated period is 7 days.")


async def test_an_edit_that_changes_nothing_the_results_show_does_not_send_the_charts_again(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())

    user.find(marker=PRICE).clear().type("0.35")                     # the first change: the result is outdated now
    await user.should_see(marker="draft-outdated")
    drawn = field(user, "draft-flows-electricity")

    user.find(marker=PRICE).clear().type("0.4")                      # a second change: still outdated, nothing new to show
    await settle()

    assert field(user, "draft-flows-electricity") is drawn           # the same element, not drawn again


async def test_the_name_of_the_scenario_does_not_draw_the_charts_again(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())
    drawn = field(user, "draft-flows-electricity")

    user.find(marker="draft-name").clear().type("Another name")
    await settle()

    assert field(user, "draft-flows-electricity") is drawn


async def test_a_new_run_draws_the_new_result(user: User, monkeypatch):
    results = iter([rich_result(), rich_result(horizon=168.0)])

    async def solver(scenario):
        return next(results)

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see(marker="draft-tab-costs")
    assert exists(user, "draft-period-note")                                    # the first result: one day
    first = field(user, "draft-flows-electricity")

    user.find(marker="draft-run").click()
    await user.should_see("The simulated period is 7 days.")

    assert field(user, "draft-flows-electricity") is not first and run_button(user).enabled


async def test_clearing_the_selection_removes_the_tabs(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())

    user.find(marker="clear-selection").click()
    await settle()

    assert not exists(user, "draft-tab-costs") and not exists(user, "draft-results")


async def test_a_result_that_is_outdated_keeps_its_tabs(user: User, monkeypatch):
    await show(user, monkeypatch, rich_result())

    user.find(marker=PRICE).clear().type("0.35")
    await user.should_see("You changed the scenario after this run.")

    assert exists(user, "draft-tab-costs") and exists(user, "draft-flows-electricity")


# ---------------------------------------------------------------------------
# the real thing
# ---------------------------------------------------------------------------

@needs_a_solver
async def test_a_real_result_has_the_numbers_of_the_run(user: User):
    await build_draft(user)                                             # a demand and the grid, one day (shares of a year)
    field(user, "field-demand-demand-profile_type").value = "absolute"
    await settle()
    await give_demand(user, values=[10.0] * 24)                         # 10 kW for a day at 0.30 EUR/kWh
    user.find(marker=PRICE).clear().type("0.3")
    await settle()

    user.find(marker="draft-run").click()
    await user.should_see(marker="draft-tab-costs", retries=200)

    assert [t.name for t in field(user, "draft-flows-electricity").figure.data] == ["Grid import", "Demand"]
    assert table_cells(user, "draft-costs-table") == [["Grid import", "Energy purchase", "72"]]
    assert table_cells(user, "draft-supply-electricity")[0][:2] == ["Grid import", "240"]
    await user.should_see("No components with a capacity in this system.")
    await user.should_see("The simulated period is 1 day.")