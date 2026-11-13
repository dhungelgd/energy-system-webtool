"""The charts of a carrier over the whole period: the energy of each month, the duration curve, the heat map."""

import datetime
import json

import numpy as np
import pytest

from backend.i18n import Translator
from backend.results import BusSummary, FlowTable, Table
from frontend_nicegui.chart_style import as_chart
from frontend_nicegui.palette import COLORS, DEMAND_LINE
from frontend_nicegui.result_charts_year import (
    DEMAND,
    duration_figure,
    heatmap_choices,
    heatmap_figure,
    heatmap_label,
    monthly_figure,
)

DE = Translator("de")
ENGLISH_TR = Translator("en")
START = datetime.datetime(2021, 1, 1)


def bus_of(columns, hours, step_hours=1.0, start=START):
    """A carrier whose flows are given as functions of the number of the step (or as constants)."""

    steps = round(hours / step_hours)
    names = list(columns)
    values = [[(columns[n](i) if callable(columns[n]) else columns[n]) for i in range(steps)] for n in names]
    flows = FlowTable(start=start, step_hours=step_hours, columns=names, values=values) if names else None

    return BusSummary(energy_sums={}, supply=Table(columns=[]), use=Table(columns=[]), flows=flows)


def traces_of(figure):
    return {trace.name: trace for trace in figure.data}


JAN_FEB = 59 * 24                                                       # 31 + 28 days
FLOWS = {"pv-->electricity": 2.0, "grid_import-->electricity": 1.0, "electricity-->demand": 3.0, "electricity-->heating_rod": 0.5}


# ---------------------------------------------------------------------------
# the energy of each month
# ---------------------------------------------------------------------------

def test_the_energy_of_each_month_is_the_power_times_the_hours_of_that_month():
    figure = monthly_figure("electricity", bus_of(FLOWS, JAN_FEB))
    traces = traces_of(figure)

    assert list(traces) == ["Grid import", "PV", "Demand", "Heating rod"]
    assert list(traces["PV"].y) == [2.0 * 744, 2.0 * 672]                    # January has 744 hours, February 672
    assert list(traces["Grid import"].y) == [744.0, 672.0]
    assert list(traces["Demand"].y) == [3.0 * 744, 3.0 * 672]
    assert list(traces["Heating rod"].y) == [-0.5 * 744, -0.5 * 672]        # what else uses the carrier is below the line
    assert [x.date() for x in traces["PV"].x] == [datetime.date(2021, 1, 1), datetime.date(2021, 2, 1)]


def test_supplies_and_other_uses_are_bars_and_the_demand_is_a_line_with_markers():
    figure = monthly_figure("electricity", bus_of(FLOWS, JAN_FEB))
    traces = traces_of(figure)

    assert traces["PV"].type == "bar" and traces["Heating rod"].type == "bar"
    assert traces["Demand"].type == "scatter" and traces["Demand"].mode == "lines+markers"
    assert traces["Demand"].line.color == DEMAND_LINE
    assert figure.layout.barmode == "relative"                               # the supplies up, the uses down
    assert traces["PV"].xperiod == "M1" and traces["PV"].xperiodalignment == "middle"      # a bar is as wide as a month


def test_a_step_of_half_an_hour_counts_half_an_hour():
    figure = monthly_figure("electricity", bus_of({"pv-->electricity": 1.0, "electricity-->demand": 1.0}, JAN_FEB, 0.5))

    assert list(traces_of(figure)["PV"].y) == [744.0, 672.0]                 # 1 kW for a month is not 2 x 744


def test_a_month_that_is_only_partly_in_the_period_has_the_energy_of_the_part_that_is_there():
    figure = monthly_figure("electricity", bus_of({"pv-->electricity": 2.0}, (31 + 9) * 24))

    assert list(traces_of(figure)["PV"].y) == [2.0 * 744, 2.0 * 9 * 24]


def test_each_bar_has_the_colour_of_its_component():
    traces = traces_of(monthly_figure("electricity", bus_of(FLOWS, JAN_FEB)))

    assert traces["PV"].marker.color == COLORS["pv"] and traces["Grid import"].marker.color == COLORS["grid_import"]
    assert traces["Heating rod"].marker.color == COLORS["heating_rod"]


def test_the_month_is_a_number_on_the_axis_and_in_the_hover_text_in_both_languages():
    english = monthly_figure("electricity", bus_of(FLOWS, JAN_FEB)).layout.xaxis
    german = monthly_figure("electricity", bus_of(FLOWS, JAN_FEB), DE).layout.xaxis

    assert (english.tickformat, english.hoverformat, english.dtick) == ("%Y-%m", "%Y-%m", "M1")
    assert (german.tickformat, german.hoverformat) == ("%m.%Y", "%m.%Y")
    assert english.title.text == "Month" and german.title.text == "Monat"


def test_the_names_and_the_axes_are_in_the_language_of_the_reader():
    figure = monthly_figure("electricity", bus_of(FLOWS, JAN_FEB), DE)

    assert list(traces_of(figure)) == ["Netzbezug", "PV-Anlage", "Bedarf", "Heizstab"]
    assert figure.layout.yaxis.title.text == "Energie (kWh)"
    assert monthly_figure("electricity", bus_of(FLOWS, JAN_FEB)).layout.yaxis.title.text == "Energy (kWh)"


def test_a_flow_that_is_zero_in_every_month_is_not_drawn():
    figure = monthly_figure("electricity", bus_of({**FLOWS, "wind-->electricity": 0.0, "electricity-->battery": 0.0}, JAN_FEB))

    assert "Wind turbine" not in traces_of(figure) and "Battery" not in traces_of(figure)


@pytest.mark.parametrize("hours", [24, 30 * 24, 31 * 24])
def test_a_period_within_one_month_has_no_monthly_balance(hours):
    assert monthly_figure("electricity", bus_of(FLOWS, hours)) is None


def test_a_period_across_the_turn_of_a_month_has_two_bars_even_if_it_is_short():
    figure = monthly_figure("electricity", bus_of({"pv-->electricity": 1.0}, 48, start=datetime.datetime(2021, 1, 31)))

    assert list(traces_of(figure)["PV"].y) == [24.0, 24.0]


def test_a_result_without_flows_has_no_monthly_balance():
    assert monthly_figure("electricity", bus_of({}, JAN_FEB)) is None


def test_a_carrier_through_which_nothing_flows_gives_a_figure_without_traces():
    figure = monthly_figure("gas", bus_of({"gas_import-->gas": 0.0, "gas-->chp": 0.0}, JAN_FEB))

    assert figure is not None and len(figure.data) == 0


# ---------------------------------------------------------------------------
# the duration curve
# ---------------------------------------------------------------------------

def test_every_flow_is_sorted_from_the_highest_to_the_lowest_against_the_hours():
    figure = duration_figure("electricity", bus_of({"electricity-->demand": [1.0, 3.0, 2.0].__getitem__, "pv-->electricity": [0.0, 4.0, 1.0].__getitem__}, 3))
    traces = traces_of(figure)

    assert list(traces["Demand"].y) == [3.0, 2.0, 1.0] and list(traces["PV"].y) == [4.0, 1.0, 0.0]
    assert traces["PV"].x0 == 1.0 and traces["PV"].dx == 1.0                 # the hours of the period: 1, 2 and 3


def test_the_demand_is_the_black_line_and_the_other_flows_have_the_colour_of_their_component():
    traces = traces_of(duration_figure("electricity", bus_of(FLOWS, 48)))

    assert list(traces)[0] == "Demand" and traces["Demand"].line.color == DEMAND_LINE and traces["Demand"].line.width == 2.5
    assert traces["PV"].line.color == COLORS["pv"] and traces["Grid import"].line.color == COLORS["grid_import"]
    assert traces["Heating rod (use)"].line.color == COLORS["heating_rod"]      # a use is named as one


def test_a_use_is_not_mistaken_for_a_supply_of_the_same_component():
    figure = duration_figure("electricity", bus_of({"battery-->electricity": 1.0, "electricity-->battery": 2.0}, 24))

    assert list(traces_of(figure)) == ["Battery", "Battery (use)"]


def test_a_year_is_thinned_out_to_a_thousand_points_that_keep_the_highest_and_the_lowest_value():
    figure = duration_figure("electricity", bus_of({"electricity-->demand": lambda i: float((i * 37) % 8761)}, 8760))
    demand = traces_of(figure)["Demand"]

    values = [float((i * 37) % 8761) for i in range(8760)]

    assert len(demand.y) == 1000
    assert demand.y[0] == max(values) and demand.y[-1] == min(values)        # the highest and the lowest stay
    assert demand.x0 == 1.0 and demand.x0 + demand.dx * 999 == pytest.approx(8760.0)      # from the first hour to the last
    assert all(a >= b for a, b in zip(demand.y, demand.y[1:]))               # it only falls


def test_a_short_period_keeps_every_value():
    figure = duration_figure("electricity", bus_of({"electricity-->demand": lambda i: float(i)}, 300))

    assert len(traces_of(figure)["Demand"].y) == 300


def test_the_hours_follow_the_length_of_the_steps():
    figure = duration_figure("electricity", bus_of({"electricity-->demand": lambda i: float(i)}, 6, step_hours=0.5))

    demand = traces_of(figure)["Demand"]

    assert len(demand.y) == 12 and demand.x0 == 0.5 and demand.dx == 0.5     # the hours 0.5, 1.0 ... 6.0


def test_the_values_are_sent_as_single_precision_numbers():
    assert traces_of(duration_figure("electricity", bus_of(FLOWS, 48)))["PV"].y.dtype == "float32"


def test_the_names_and_the_axes_of_the_duration_curve_are_in_the_language_of_the_reader():
    figure = duration_figure("electricity", bus_of(FLOWS, 48), DE)

    assert list(traces_of(figure)) == ["Bedarf", "Netzbezug", "PV-Anlage", "Heizstab (Verwendung)"]
    assert figure.layout.xaxis.title.text == "Stunden des Zeitraums, sortiert" and figure.layout.yaxis.title.text == "Leistung (kW)"
    assert duration_figure("electricity", bus_of(FLOWS, 48)).layout.xaxis.title.text == "Hours of the period, sorted"


def test_a_flow_that_is_zero_all_the_time_has_no_line():
    figure = duration_figure("electricity", bus_of({**FLOWS, "wind-->electricity": 0.0}, 48))

    assert "Wind turbine" not in traces_of(figure)


def test_without_flows_there_is_no_duration_curve_and_a_dead_carrier_has_no_lines():
    assert duration_figure("electricity", bus_of({}, 48)) is None
    assert len(duration_figure("gas", bus_of({"gas_import-->gas": 0.0}, 48)).data) == 0


# ---------------------------------------------------------------------------
# the heat map
# ---------------------------------------------------------------------------

def day_hour(i):
    """A value that says where it is: the number of the day times 100 plus the hour."""

    return (i // 24) * 100.0 + i % 24


def z_of(figure):
    return np.asarray(figure.data[0].z)


def test_a_heat_map_can_show_the_demand_and_every_supply_that_is_not_zero():
    bus = bus_of({**FLOWS, "wind-->electricity": 0.0}, 48)

    assert heatmap_choices("electricity", bus) == [DEMAND, "grid_import-->electricity", "pv-->electricity"]
    assert heatmap_choices("electricity", bus_of({}, 48)) == []
    assert heatmap_choices("electricity", bus_of({"pv-->electricity": 1.0}, 48)) == ["pv-->electricity"]      # no demand there


def test_a_choice_has_a_name_in_the_language_of_the_reader():
    assert heatmap_label(ENGLISH_TR, DEMAND) == "Demand" and heatmap_label(ENGLISH_TR, "pv-->electricity") == "PV"
    assert heatmap_label(DE, DEMAND) == "Bedarf" and heatmap_label(DE, "grid_import-->electricity") == "Netzbezug"


def test_each_hour_of_each_day_is_in_its_place():
    figure = heatmap_figure("electricity", bus_of({"pv-->electricity": day_hour, "electricity-->demand": 1.0}, 72), "pv-->electricity")
    z = z_of(figure)

    assert z.shape == (24, 3)                                              # 24 hours down, three days across
    assert z[0, 0] == 0.0 and z[5, 0] == 5.0 and z[23, 0] == 23.0          # the first day
    assert z[0, 1] == 100.0 and z[7, 2] == 207.0                           # the hour 0 of day 1, the hour 7 of day 2


def test_the_days_follow_from_the_first_date_in_steps_of_a_day_and_the_hours_are_0_to_23_with_midnight_on_top():
    figure = heatmap_figure("electricity", bus_of({"pv-->electricity": day_hour, "electricity-->demand": 1.0}, 72), "pv-->electricity")

    assert figure.data[0].x0 == START and figure.data[0].dx == 86_400_000
    assert list(figure.data[0].y) == list(range(24)) and figure.layout.yaxis.autorange == "reversed"


def test_the_demand_is_the_sum_of_the_flows_to_the_demands_in_the_dark_colour():
    flows = {"electricity-->demand": 1.0, "electricity-->another_demand": 2.0, "pv-->electricity": 1.0}

    figure = heatmap_figure("electricity", bus_of(flows, 48), DEMAND)

    assert set(z_of(figure).flatten()) == {3.0}
    assert figure.data[0].colorscale[-1][1] == DEMAND_LINE


def test_the_map_ends_in_the_colour_of_the_component_and_starts_white():
    figure = heatmap_figure("electricity", bus_of(FLOWS, 48), "pv-->electricity")

    assert figure.data[0].colorscale[0][1] == "#FFFFFF" and figure.data[0].colorscale[-1][1] == COLORS["pv"]


def test_a_day_that_is_only_partly_in_the_period_has_gaps_for_the_hours_that_are_not():
    start = datetime.datetime(2021, 1, 1, 6)
    figure = heatmap_figure("electricity", bus_of({"pv-->electricity": 1.0, "electricity-->demand": 1.0}, 36, start=start), "pv-->electricity")
    z = z_of(figure)

    assert z.shape == (24, 2) and np.isnan(z[:6, 0]).all() and (z[6:, 0] == 1.0).all()       # the first day starts at 6 o'clock
    assert (z[:18, 1] == 1.0).all() and np.isnan(z[18:, 1]).all()                              # the second ends at 18 o'clock
    assert figure.data[0].hoverongaps is False


def test_values_of_a_quarter_of_an_hour_are_averaged_to_hours():
    figure = heatmap_figure("electricity", bus_of({"pv-->electricity": lambda i: float(i % 4), "electricity-->demand": 1.0}, 48, step_hours=0.25), "pv-->electricity")

    assert set(z_of(figure).flatten()) == {1.5}                              # the mean of 0, 1, 2, 3


@pytest.mark.parametrize("hours, what, why", [
    (24, "pv-->electricity", "a single day has nothing to compare"),
    (48, "wind-->electricity", "not a choice of this result"),
])
def test_there_is_no_heat_map_when_there_is_nothing_to_show(hours, what, why):
    assert heatmap_figure("electricity", bus_of(FLOWS, hours), what) is None, why


def test_there_is_no_heat_map_for_steps_longer_than_an_hour_or_without_flows():
    assert heatmap_figure("electricity", bus_of(FLOWS, 96, step_hours=2.0), "pv-->electricity") is None
    assert heatmap_figure("electricity", bus_of({}, 96), DEMAND) is None


def test_the_axes_the_hover_text_and_the_colour_bar_are_in_the_language_of_the_reader():
    english = heatmap_figure("electricity", bus_of(FLOWS, 48), "pv-->electricity")
    german = heatmap_figure("electricity", bus_of(FLOWS, 48), "pv-->electricity", DE)

    assert english.layout.xaxis.title.text == "Date" and english.layout.yaxis.title.text == "Hour of the day"
    assert german.layout.xaxis.title.text == "Datum" and german.layout.yaxis.title.text == "Stunde des Tages"
    assert (english.layout.xaxis.tickformat, german.layout.xaxis.tickformat) == ("%Y-%m-%d", "%d.%m.%Y")
    assert english.data[0].colorbar.title.text == "kW"


def test_the_values_are_a_block_of_single_precision_numbers():
    figure = heatmap_figure("electricity", bus_of(FLOWS, 48), "pv-->electricity")

    assert z_of(figure).dtype == "float32"


# ---------------------------------------------------------------------------
# the size, and the font
# ---------------------------------------------------------------------------

def test_a_year_of_each_chart_is_light():
    flows = {name: (lambda i, k=k: ((i * (k + 3)) % 997) / 7.0) for k, name in enumerate(
        ["grid_import-->electricity", "pv-->electricity", "wind-->electricity", "chp-->electricity", "battery-->electricity",
         "electricity-->demand", "electricity-->heat_pump", "electricity-->heating_rod", "electricity-->grid_feedin",
         "electricity-->battery"])}
    bus = bus_of(flows, 8760)

    def sent(figure):
        return len(json.dumps(as_chart(figure, "x"), default=str))

    assert sent(monthly_figure("electricity", bus)) < 20_000
    assert sent(duration_figure("electricity", bus)) < 150_000               # ten lines of a thousand points
    assert sent(heatmap_figure("electricity", bus, DEMAND)) < 80_000          # a number for each hour of a year


def test_the_axes_are_large_and_bold_in_the_three_charts():
    bus = bus_of(FLOWS, JAN_FEB)

    for figure in (monthly_figure("electricity", bus), duration_figure("electricity", bus), heatmap_figure("electricity", bus, DEMAND)):
        for axis in (figure.layout.xaxis, figure.layout.yaxis):
            assert axis.tickfont.weight == "bold" and axis.tickfont.size == 15
            assert axis.title.font.weight == "bold" and axis.title.font.size == 17
    assert heatmap_figure("electricity", bus, DEMAND).data[0].colorbar.tickfont.weight == "bold"