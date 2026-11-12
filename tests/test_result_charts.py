"""The charts of a result: the cost items, the flows of a bus, the Sankey diagram (as data, no page needed)."""

import datetime

import pytest

from backend import service_v2
from backend.i18n import Translator
from backend.results import BusSummary, FlowTable, ScenarioResult, Table
from frontend_nicegui.palette import BUS_COLOR, COLORS, DEMAND_LINE, GREY, with_alpha
from frontend_nicegui.result_charts import cost_figure, flows_figure, sankey_figure
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


def test_the_cost_items_are_bars_in_the_colour_of_their_component_and_revenues_go_to_the_left():
    figure = cost_figure(result_of(COSTS))

    # in the order in which the categories first appear when the items are sorted by cost: the revenue is the smallest
    assert [trace.name for trace in figure.data] == ["Revenue", "Investment and fixed O&M", "Energy purchase"]
    by_name = {trace.name: trace for trace in figure.data}
    assert list(by_name["Revenue"].x) == [-500.0] and list(by_name["Revenue"].y) == ["Grid feed-in"]
    assert list(by_name["Energy purchase"].x) == [36272.7] and list(by_name["Energy purchase"].y) == ["Grid import"]
    assert list(by_name["Revenue"].marker.color) == [COLORS["grid_feedin"]]
    assert list(by_name["Energy purchase"].marker.color) == [COLORS["grid_import"]]
    assert list(by_name["Investment and fixed O&M"].marker.color) == [COLORS["heating_rod"]]
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


def test_an_item_that_is_not_known_is_grey_and_shown_as_it_is():
    figure = cost_figure(result_of([["Something", "A new kind of cost", 12.0]]), DE)

    (trace,) = figure.data
    assert trace.name == "A new kind of cost" and list(trace.y) == ["Something"] and list(trace.marker.color) == [GREY]


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
    assert list(traces["Demand"].y) == [3.0, 2.0, 1.0] and traces["Demand"].line.color == DEMAND_LINE
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
    trace = traces_of(figure)["Grid import"]

    # a start and a step instead of a time stamp for each value: the values are at 0:00, 0:30 and 1:00
    assert len(trace.y) == 3 and trace.x0 == datetime.datetime(2021, 1, 1, 0, 0) and trace.dx == 30 * 60 * 1000


def test_the_names_and_the_axes_are_in_the_language_of_the_reader():
    figure = flows_figure("electricity", bus_of(FLOWS), DE)

    assert list(traces_of(figure)) == ["Netzbezug", "PV-Anlage", "Bedarf", "Netzeinspeisung", "Heizstab"]
    assert figure.layout.xaxis.title.text == "Datum und Uhrzeit" and figure.layout.yaxis.title.text == "Leistung (kW)"
    assert flows_figure("electricity", bus_of(FLOWS)).layout.yaxis.title.text == "Power (kW)"
    assert flows_figure("electricity", bus_of(FLOWS)).layout.xaxis.title.text == "Date and time"


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

    assert list(sankey.node.label) == [
        "Grid import, 120 kWh", "PV, 30 kWh", "Electricity, 150 kWh", "Electricity demand, 100 kWh",
        "Heating rod, 40 kWh", "Grid feed-in, 10 kWh"]
    assert list(sankey.link.source) == [0, 1, 2, 2, 2] and list(sankey.link.target) == [2, 2, 3, 4, 5]
    assert list(sankey.link.value) == [120.0, 30.0, 100.0, 40.0, 10.0]


def test_what_is_zero_or_empty_is_left_out():
    sankey = sankey_figure("electricity", bus_of(supply=SUPPLY, use=USE)).data[0]

    assert not any(label.startswith("Battery") for label in sankey.node.label) and 0 not in list(sankey.link.value)


def test_the_words_of_the_diagram_are_in_the_language_of_the_reader():
    figure = sankey_figure("electricity", bus_of(supply=SUPPLY, use=USE), DE)

    assert list(figure.data[0].node.label) == [
        "Netzbezug, 120 kWh", "PV-Anlage, 30 kWh", "Strom, 150 kWh", "Strombedarf, 100 kWh", "Heizstab, 40 kWh",
        "Netzeinspeisung, 10 kWh"]
    assert figure.layout.title.text == "Strom: Energie im simulierten Zeitraum (kWh)"
    assert sankey_figure("heat", bus_of(supply=SUPPLY[:1], use=USE[:1])).layout.title.text == \
        "Heat: energy over the simulated period (kWh)"


def test_a_storage_is_a_node_on_each_side_when_it_charges_and_discharges():
    supply = [["Battery", 5.0, 100.0]]
    use = [["Battery", 6.0, 60.0], ["Electricity demand", 4.0, 40.0]]

    sankey = sankey_figure("electricity", bus_of(supply=supply, use=use)).data[0]

    assert list(sankey.node.label) == ["Battery, 5 kWh", "Electricity, 5 kWh", "Battery, 6 kWh", "Electricity demand, 4 kWh"]
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

    assert few == 380 and many == 64 * 8 + 160


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


# ---------------------------------------------------------------------------
# one colour for each component, in every chart
# ---------------------------------------------------------------------------

def test_the_cost_chart_has_no_legend_and_says_the_category_in_the_hover_text():
    figure = cost_figure(result_of(COSTS))

    assert figure.layout.showlegend is False
    assert all(trace.name in trace.hovertemplate for trace in figure.data)


def test_two_items_of_one_category_keep_the_colour_of_their_own_component():
    figure = cost_figure(result_of([
        ["Heating rod", "Investment and fixed O&M", 5000.0], ["Heat pump", "Investment and fixed O&M", 9000.0]]))

    (trace,) = figure.data
    assert list(trace.y) == ["Heating rod", "Heat pump"] and list(trace.marker.color) == [COLORS["heating_rod"], COLORS["heat_pump"]]


def test_each_flow_is_drawn_in_the_colour_of_its_component_and_the_demand_in_the_dark_line():
    traces = traces_of(flows_figure("electricity", bus_of(FLOWS)))

    assert traces["Grid import"].line.color == COLORS["grid_import"] and traces["PV"].line.color == COLORS["pv"]
    assert traces["Grid feed-in"].line.color == COLORS["grid_feedin"] and traces["Heating rod"].line.color == COLORS["heating_rod"]
    assert traces["Demand"].line.color == DEMAND_LINE


def test_an_area_is_filled_with_its_colour_a_little_see_through():
    traces = traces_of(flows_figure("electricity", bus_of(FLOWS)))

    assert traces["PV"].fillcolor == with_alpha(COLORS["pv"], 0.85)
    assert traces["Heating rod"].fillcolor == with_alpha(COLORS["heating_rod"], 0.85)


def test_a_flow_that_the_palette_does_not_know_is_grey():
    traces = traces_of(flows_figure("electricity", bus_of({"some_new_part-->electricity": [1.0, 2.0]})))

    assert traces["Some New Part"].line.color == GREY


def test_the_legend_is_below_the_chart_and_the_zero_line_is_marked():
    figure = flows_figure("electricity", bus_of(FLOWS))

    assert figure.layout.legend.orientation == "h" and figure.layout.legend.y < 0
    assert figure.layout.yaxis.zerolinecolor


def test_the_sankey_diagram_has_the_colours_of_the_components_and_a_neutral_node_for_the_bus():
    sankey = sankey_figure("electricity", bus_of(supply=SUPPLY, use=USE)).data[0]

    assert list(sankey.node.color) == [
        COLORS["grid_import"], COLORS["pv"], BUS_COLOR, COLORS["demand"], COLORS["heating_rod"], COLORS["grid_feedin"]]


def test_each_band_of_the_sankey_diagram_has_the_colour_of_the_component_at_its_end_and_is_see_through():
    sankey = sankey_figure("electricity", bus_of(supply=SUPPLY, use=USE)).data[0]

    assert list(sankey.link.color) == [
        with_alpha(COLORS[k], 0.35) for k in ("grid_import", "pv", "demand", "heating_rod", "grid_feedin")]


# ---------------------------------------------------------------------------
# a window of time
# ---------------------------------------------------------------------------

def long_bus(hours, step_hours=1.0):
    n = round(hours / step_hours)
    return bus_of({
        "grid_import-->electricity": [float(i % 24) for i in range(n)],
        "pv-->electricity": [1.0] * n,
        "electricity-->demand": [float(i % 24) + 1.0 for i in range(n)],
    }, step_hours=step_hours)


def test_a_week_shows_168_hourly_values_from_the_start_of_the_window():
    figure = flows_figure("electricity", long_bus(1440), view=("week", 1))
    pv = traces_of(figure)["PV"]

    assert len(pv.y) == 168 and pv.x0 == datetime.datetime(2021, 1, 8) and pv.dx == 3_600_000


def test_a_day_shows_24_values_and_a_month_720():
    assert len(traces_of(flows_figure("electricity", long_bus(1440), view=("day", 3)))["PV"].y) == 24
    assert len(traces_of(flows_figure("electricity", long_bus(1440), view=("month", 0)))["PV"].y) == 720


def test_the_whole_period_shows_every_value():
    figure = flows_figure("electricity", long_bus(1440), view=("all", 0))
    pv = traces_of(figure)["PV"]

    assert len(pv.y) == 1440 and pv.dx == 3_600_000 and pv.x0 == START


def test_the_demand_line_of_a_window_is_the_sum_of_the_demands_of_that_window():
    figure = flows_figure("electricity", long_bus(1440), view=("day", 1))

    assert list(traces_of(figure)["Demand"].y[:3]) == [1.0, 2.0, 3.0]


MODES = ("day", "week", "month", "all")


def stops_of(figure):
    return [(tuple(s.dtickrange), s.value) for s in figure.layout.xaxis.tickformatstops]


def test_the_ticks_say_the_time_and_the_date_when_they_are_closer_than_a_day_and_the_date_when_they_are_not():
    expected = [((None, 86_399_999), "%H:%M<br>%Y-%m-%d"), ((86_400_000, None), "%Y-%m-%d")]

    for mode in MODES:
        figure = flows_figure("electricity", long_bus(1440), view=(mode, 0))
        assert stops_of(figure) == expected, mode
        assert figure.layout.xaxis.tickformat is None, mode               # no fixed format: the zoom decides
    assert stops_of(flows_figure("electricity", bus_of(FLOWS))) == expected      # also without a window


def test_the_month_is_a_number_not_a_name_and_the_date_is_written_the_german_way_in_german():
    german = stops_of(flows_figure("electricity", long_bus(1440), DE, view=("week", 0)))

    assert german == [((None, 86_399_999), "%H:%M<br>%d.%m.%Y"), ((86_400_000, None), "%d.%m.%Y")]
    assert not any("%b" in value or "%B" in value for _, value in german)


def test_pointing_at_a_value_says_the_date_and_the_time():
    for mode in MODES:
        assert flows_figure("electricity", long_bus(1440), view=(mode, 0)).layout.xaxis.hoverformat == "%Y-%m-%d %H:%M", mode
    assert flows_figure("electricity", bus_of(FLOWS)).layout.xaxis.hoverformat == "%Y-%m-%d %H:%M"
    assert flows_figure("electricity", long_bus(1440), DE, view=("day", 0)).layout.xaxis.hoverformat == "%d.%m.%Y %H:%M"


def test_the_axis_is_titled_date_and_time_in_every_window():
    for mode in MODES:
        assert flows_figure("electricity", long_bus(1440), view=(mode, 0)).layout.xaxis.title.text == "Date and time"


def test_without_a_view_every_step_is_drawn_as_before():
    assert len(traces_of(flows_figure("electricity", long_bus(1440)))["PV"].y) == 1440


def test_a_flow_that_is_zero_in_the_window_but_not_elsewhere_is_left_out_of_the_window_only():
    frame = {"pv-->electricity": [0.0] * 24 + [3.0] * 24, "electricity-->demand": [1.0] * 48}

    first = traces_of(flows_figure("electricity", bus_of(frame), view=("day", 0)))
    second = traces_of(flows_figure("electricity", bus_of(frame), view=("day", 1)))

    assert "PV" not in first and "PV" in second


# ---------------------------------------------------------------------------
# a size and a font that stay readable
# ---------------------------------------------------------------------------

def test_the_flows_are_sent_as_single_precision_numbers_so_that_a_year_stays_light():
    figure = flows_figure("electricity", bus_of({"pv-->electricity": [1.23456, 2.0], "electricity-->demand": [0.5, 1.5]}))
    traces = traces_of(figure)

    assert traces["PV"].y.dtype == "float32" and traces["Demand"].y.dtype == "float32"
    assert list(traces["PV"].y) == pytest.approx([1.23456, 2.0], rel=1e-6) and list(traces["Demand"].y) == [0.5, 1.5]


def test_a_year_of_every_value_for_a_carrier_with_ten_flows_is_about_half_a_megabyte_and_a_window_is_light():
    import json
    import random

    from frontend_nicegui.chart_style import as_chart

    rng = random.Random(1)
    names = ["grid_import-->electricity", "pv-->electricity", "wind-->electricity", "chp-->electricity",
             "battery-->electricity", "electricity-->demand", "electricity-->heat_pump", "electricity-->heating_rod",
             "electricity-->grid_feedin", "electricity-->battery"]
    bus = bus_of({name: [rng.random() * 100 for _ in range(8760)] for name in names})    # random: the worst case

    def sent(mode, position=0):
        figure = flows_figure("electricity", bus, view=(mode, position))
        return len(json.dumps(as_chart(figure, "x"), default=str))

    assert sent("all") < 600_000                                           # it was 2.9 MB with a time stamp for each value
    assert sent("month") < 80_000 and sent("week") < 40_000 and sent("day") < 20_000


def test_the_axes_and_the_ticks_are_large_and_bold_in_every_chart_that_has_axes():
    figures = [
        flows_figure("electricity", bus_of(FLOWS)),
        flows_figure("electricity", long_bus(1440), view=("week", 0)),
        cost_figure(result_of(COSTS)),
    ]

    for figure in figures:
        for axis in (figure.layout.xaxis, figure.layout.yaxis):
            assert axis.tickfont.weight == "bold" and axis.tickfont.size == 15
            assert axis.title.font.weight == "bold" and axis.title.font.size == 17


def test_the_text_on_a_chart_is_large_and_bold_too():
    figure = flows_figure("electricity", bus_of(FLOWS))
    costs = cost_figure(result_of(COSTS))

    assert figure.layout.font.size == 15 and figure.layout.legend.font.weight == "bold" and figure.layout.legend.font.size == 15
    assert all(trace.textfont.weight == "bold" and trace.textfont.size == 15 for trace in costs.data)   # the amounts on the bars


def test_the_sankey_diagram_has_large_bold_names_and_a_bold_title_and_no_axes_were_added():
    figure = sankey_figure("electricity", bus_of(supply=SUPPLY, use=USE))

    assert figure.data[0].textfont.weight == "bold" and figure.data[0].textfont.size == 15
    assert figure.layout.title.font.weight == "bold" and figure.layout.title.font.size == 19
    assert figure.layout.xaxis.tickfont.size is None and figure.layout.yaxis.tickfont.size is None


def test_the_value_of_a_carrier_without_supply_is_the_sum_of_its_uses():
    sankey = sankey_figure("heat", bus_of(supply=[], use=[["Heat demand", 90.0, 100.0], ["Battery", 10.0, 0.0]])).data[0]

    assert list(sankey.node.label) == ["Heat, 100 kWh", "Heat demand, 90 kWh", "Battery, 10 kWh"]


def test_the_values_in_the_sankey_diagram_are_written_the_way_of_the_language():
    sankey = sankey_figure("electricity", bus_of(supply=[["Grid import", 120909.4, 100.0]], use=[["Electricity demand", 120909.4, 100.0]]))
    german = sankey_figure("electricity", bus_of(supply=[["Grid import", 120909.4, 100.0]], use=[["Electricity demand", 120909.4, 100.0]]), DE)

    assert sankey.data[0].node.label[0] == "Grid import, 120,909 kWh"
    assert german.data[0].node.label[0] == "Netzbezug, 120.909 kWh"