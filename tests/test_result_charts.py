"""The charts of a result: the cost items, the flows of a bus, the Sankey diagram (as data, no page needed)."""

import datetime

import pytest

from backend import service_v2
from backend.i18n import Translator
from backend.results import BusSummary, FlowTable, ScenarioResult, Table
from frontend_nicegui.result_charts import (
    CATEGORY_COLORS,
    OTHER_COLOR,
    cost_figure,
    flows_figure,
    sankey_figure,
)
from tests.helpers import needs_cbc
from tests.test_solving import many_components

DE = Translator("de")
START = datetime.datetime(2021, 1, 1)


def result_of(cost_rows=None, buses=None, cost_columns=("Item", "Category", "Cost (€)")):
    return ScenarioResult(
        objective=1.0, horizon_hours=24.0,
        cost_breakdown=Table(columns=list(cost_columns), rows=cost_rows or []),
        capacities=Table(columns=[]), buses=buses or {},
    )


def bus_of(columns=None, supply=(), use=(), step_hours=1.0, flows=True):
    table = lambda rows: Table(columns=["Component", "Energy (kWh)", "Share (%)"], rows=[list(r) for r in rows])
    flow_table = None
    if flows:
        names = list(columns or {})
        flow_table = FlowTable(start=START, step_hours=step_hours, columns=names, values=[list(columns[n]) for n in names]) \
            if names else FlowTable(start=START, step_hours=step_hours, columns=[], values=[])

    return BusSummary(energy_sums={}, supply=table(supply), use=table(use), flows=flow_table)


COSTS = [
    ["Heating rod", "Investment and fixed O&M", 19080.3],
    ["Grid import", "Energy purchase", 36272.7],
    ["Grid feed-in", "Revenue", -500.0],
    ["Battery", "Investment and fixed O&M", 0.001],
]


# ---------------------------------------------------------------------------
# the cost items
# ---------------------------------------------------------------------------

def test_the_cost_items_are_bars_in_the_colour_of_their_category_and_revenues_go_to_the_left():
    figure = cost_figure(result_of(COSTS))

    # in the order in which the categories first appear when the items are sorted by cost: the revenue is the smallest
    assert [trace.name for trace in figure.data] == ["Revenue", "Investment and fixed O&M", "Energy purchase"]
    by_name = {trace.name: trace for trace in figure.data}
    assert list(by_name["Revenue"].x) == [-500.0] and list(by_name["Revenue"].y) == ["Grid feed-in"]
    assert list(by_name["Energy purchase"].x) == [36272.7] and list(by_name["Energy purchase"].y) == ["Grid import"]
    assert by_name["Investment and fixed O&M"].marker.color == CATEGORY_COLORS["Investment and fixed O&M"]
    assert by_name["Revenue"].marker.color == CATEGORY_COLORS["Revenue"]
    assert all(trace.orientation == "h" for trace in figure.data)


def test_a_cost_item_below_half_a_cent_is_not_drawn_and_the_rest_is_in_order():
    figure = cost_figure(result_of(COSTS))

    drawn = [item for trace in figure.data for item in trace.y]
    assert sorted(drawn) == ["Grid feed-in", "Grid import", "Heating rod"]            # the battery is not there
    assert [x for trace in figure.data for x in trace.x].count(0.001) == 0


def test_the_items_and_the_categories_are_in_the_language_of_the_reader():
    figure = cost_figure(result_of(COSTS), DE)

    assert {trace.name for trace in figure.data} == {"Investition und feste Betriebskosten", "Energiebezug", "Erlös"}
    assert sorted(item for trace in figure.data for item in trace.y) == ["Heizstab", "Netzbezug", "Netzeinspeisung"]
    assert figure.layout.xaxis.title.text == "Kosten (€) – negative Werte sind Erlöse"
    assert cost_figure(result_of(COSTS)).layout.xaxis.title.text == "Cost (€) – negative values are revenues"


def test_the_amounts_on_the_bars_are_written_the_way_of_the_language():
    english = {t.name: t for t in cost_figure(result_of(COSTS)).data}
    german = {t.name: t for t in cost_figure(result_of(COSTS), DE).data}

    assert list(english["Energy purchase"].text) == ["36,273 €"] and list(german["Energiebezug"].text) == ["36.273 €"]
    assert list(german["Erlös"].text) == ["-500 €"]


def test_an_unknown_category_gets_the_grey_colour_and_is_shown_as_it_is():
    figure = cost_figure(result_of([["Something", "A new kind of cost", 12.0]]), DE)

    (trace,) = figure.data
    assert trace.name == "A new kind of cost" and trace.marker.color == OTHER_COLOR


def test_the_chart_grows_with_the_number_of_items():
    small = cost_figure(result_of([["Heating rod", "Energy purchase", 5.0]]))
    large = cost_figure(result_of([[f"Item {n}", "Energy purchase", float(n + 1)] for n in range(10)]))

    assert small.layout.height == 260 and large.layout.height == 70 * 10 + 120


@pytest.mark.parametrize("result", [
    result_of(),                                                              # no items
    result_of([["Battery", "Revenue", 0.0]]),                                 # only items that are nothing
    result_of([["Battery", "Revenue", None]]),                                # an empty cost
    result_of(cost_columns=("Something", "Else")),                            # not the table of the costs
])
def test_there_is_no_chart_when_there_is_nothing_to_draw(result):
    assert cost_figure(result) is None


# ---------------------------------------------------------------------------
# the flows of a bus over time
# ---------------------------------------------------------------------------

FLOWS = {
    "grid_import-->electricity": [4.0, 2.0, 0.0],
    "pv-->electricity": [0.0, 1.0, 3.0],
    "electricity-->demand": [3.0, 2.0, 1.0],
    "electricity-->heating_rod": [1.0, 1.0, 0.0],
    "electricity-->grid_feedin": [0.0, 0.0, 2.0],
    "wind-->electricity": [0.0, 0.0, 0.0],                                    # never used
    "electricity-->battery": [0.0, 0.0, 0.0],                                 # never used
}


def traces_of(figure):
    return {trace.name: trace for trace in figure.data}


def test_the_flows_are_stacked_up_for_the_supply_and_down_for_the_other_uses_with_the_demand_as_a_line():
    figure = flows_figure("electricity", bus_of(FLOWS))
    traces = traces_of(figure)

    assert list(traces) == ["Grid import", "PV", "Demand", "Grid feed-in", "Heating rod"]            # the other uses by name
    assert [list(traces[n].y) for n in ("Grid import", "PV")] == [[4.0, 2.0, 0.0], [0.0, 1.0, 3.0]]
    assert traces["Grid import"].stackgroup == "supply" and traces["PV"].stackgroup == "supply"
    assert list(traces["Demand"].y) == [3.0, 2.0, 1.0] and traces["Demand"].line.color == "black"
    assert traces["Demand"].stackgroup is None
    assert list(traces["Heating rod"].y) == [-1.0, -1.0, -0.0] and traces["Heating rod"].stackgroup == "use"
    assert list(traces["Grid feed-in"].y) == [-0.0, -0.0, -2.0]


def test_a_flow_that_is_zero_all_the_time_is_not_drawn():
    names = list(traces_of(flows_figure("electricity", bus_of(FLOWS))))

    assert "Wind turbine" not in names and "Battery" not in names


def test_the_demand_line_is_the_sum_of_all_the_flows_to_demands():
    flows = {"heat_pump-->heat": [3.0, 3.0], "heat-->heat_demand": [1.0, 2.0], "heat-->another_demand": [1.0, 0.5]}

    figure = flows_figure("heat", bus_of(flows))

    assert list(traces_of(figure)["Demand"].y) == [2.0, 2.5]


def test_the_time_axis_follows_the_start_and_the_length_of_the_steps_without_the_end_row():
    figure = flows_figure("electricity", bus_of(FLOWS, step_hours=0.5))
    x = list(traces_of(figure)["Grid import"].x)

    assert x == [datetime.datetime(2021, 1, 1, 0, 0), datetime.datetime(2021, 1, 1, 0, 30), datetime.datetime(2021, 1, 1, 1, 0)]


def test_the_names_and_the_axes_are_in_the_language_of_the_reader():
    figure = flows_figure("electricity", bus_of(FLOWS), DE)

    assert list(traces_of(figure)) == ["Netzbezug", "PV-Anlage", "Bedarf", "Netzeinspeisung", "Heizstab"]
    assert figure.layout.xaxis.title.text == "Zeit" and figure.layout.yaxis.title.text == "Leistung (kW)"
    assert flows_figure("electricity", bus_of(FLOWS)).layout.yaxis.title.text == "Power (kW)"


def test_a_name_that_the_backend_does_not_know_is_made_readable():
    figure = flows_figure("electricity", bus_of({"some_new_part-->electricity": [1.0, 2.0]}))

    assert list(traces_of(figure)) == ["Some New Part"]


def test_a_result_without_hourly_flows_gives_no_chart():
    assert flows_figure("electricity", bus_of(flows=False)) is None
    assert flows_figure("electricity", bus_of({})) is None


def test_a_bus_through_which_nothing_flows_gives_a_figure_without_traces():
    figure = flows_figure("gas", bus_of({"gas_import-->gas": [0.0, 0.0], "gas-->chp": [0.0, 0.0]}))

    assert figure is not None and len(figure.data) == 0


# ---------------------------------------------------------------------------
# the Sankey diagram
# ---------------------------------------------------------------------------

SUPPLY = [["Grid import", 120.0, 80.0], ["PV", 30.0, 20.0], ["Battery", 0.0, 0.0]]
USE = [["Electricity demand", 100.0, 66.7], ["Heating rod", 40.0, 26.7], ["Grid feed-in", 10.0, 6.6], ["Battery", None, 0.0]]


def test_the_sankey_diagram_goes_from_what_supplies_the_bus_through_it_to_what_uses_it():
    figure = sankey_figure("electricity", bus_of(supply=SUPPLY, use=USE))
    sankey = figure.data[0]

    assert list(sankey.node.label) == ["Grid import", "PV", "Electricity", "Electricity demand", "Heating rod", "Grid feed-in"]
    assert list(sankey.link.source) == [0, 1, 2, 2, 2] and list(sankey.link.target) == [2, 2, 3, 4, 5]
    assert list(sankey.link.value) == [120.0, 30.0, 100.0, 40.0, 10.0]


def test_what_is_zero_or_empty_is_left_out():
    sankey = sankey_figure("electricity", bus_of(supply=SUPPLY, use=USE)).data[0]

    assert "Battery" not in list(sankey.node.label) and 0 not in list(sankey.link.value)


def test_the_words_of_the_diagram_are_in_the_language_of_the_reader():
    figure = sankey_figure("electricity", bus_of(supply=SUPPLY, use=USE), DE)

    assert list(figure.data[0].node.label) == ["Netzbezug", "PV-Anlage", "Strom", "Strombedarf", "Heizstab", "Netzeinspeisung"]
    assert figure.layout.title.text == "Strom: Energie im simulierten Zeitraum (kWh)"
    assert sankey_figure("heat", bus_of(supply=SUPPLY[:1], use=USE[:1])).layout.title.text == \
        "Heat: energy over the simulated period (kWh)"


def test_a_storage_is_a_node_on_each_side_when_it_charges_and_discharges():
    supply = [["Battery", 5.0, 100.0]]
    use = [["Battery", 6.0, 60.0], ["Electricity demand", 4.0, 40.0]]

    sankey = sankey_figure("electricity", bus_of(supply=supply, use=use)).data[0]

    assert list(sankey.node.label) == ["Battery", "Electricity", "Battery", "Electricity demand"]
    assert list(sankey.link.source) == [0, 1, 1] and list(sankey.link.target) == [1, 2, 3]


@pytest.mark.parametrize("summary", [
    bus_of(),                                                                  # no energy at all
    bus_of(supply=[["PV", 0.0, 0.0]], use=[["Electricity demand", 0.0, 0.0]]),
    BusSummary(energy_sums={}, supply=Table(columns=["Else"]), use=Table(columns=[]), flows=None),
])
def test_there_is_no_diagram_when_no_energy_flows(summary):
    assert sankey_figure("electricity", summary) is None


def test_the_diagram_gets_taller_with_more_nodes():
    few = sankey_figure("electricity", bus_of(supply=SUPPLY[:1], use=USE[:1])).layout.height
    many = sankey_figure("electricity", bus_of(supply=[[f"S{n}", 1.0, 1.0] for n in range(8)], use=USE[:1])).layout.height

    assert few == 380 and many == 60 * 8 + 160


# ---------------------------------------------------------------------------
# a real result
# ---------------------------------------------------------------------------

@needs_cbc
def test_in_a_real_result_what_flows_in_is_what_flows_out_at_every_step_and_the_charts_agree_with_the_tables():
    result = service_v2.run(many_components(steps=48))

    for bus, summary in result.buses.items():
        figure = flows_figure(bus, summary)
        traces = traces_of(figure)
        supplied = [sum(t.y[i] for t in figure.data if t.stackgroup == "supply") for i in range(48)] if traces else []
        used = [
            (traces["Demand"].y[i] if "Demand" in traces else 0.0)
            - sum(t.y[i] for t in figure.data if t.stackgroup == "use")
            for i in range(48)
        ] if traces else []

        assert supplied == pytest.approx(used, rel=1e-6, abs=1e-6), bus             # the balance of the bus (CBC: 1e-7)

        sankey = sankey_figure(bus, summary)
        supply_total = sum(row[1] for row in summary.supply.rows)
        if sankey is not None:
            into_the_bus = sum(v for s, v in zip(sankey.data[0].link.source, sankey.data[0].link.value)
                               if s < len([r for r in summary.supply.rows if r[1] and r[1] > 0]))
            assert into_the_bus == pytest.approx(supply_total)                      # the diagram says what the table says

    assert "electricity" in result.buses and flows_figure("electricity", result.buses["electricity"]).data