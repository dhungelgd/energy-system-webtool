"""The charts of the PDF report: the data of each chart, and that it is drawn."""

import io
from datetime import datetime

import numpy as np
import pytest
from PIL import Image

from backend.i18n import Translator
from backend.results import BusSummary, FlowTable, Table
from frontend_nicegui import report_charts as charts
from frontend_nicegui.palette import COLORS, DEMAND_LINE
from frontend_nicegui.report_data import ChartRef
from tests.report_samples import sample_result

DE = Translator("de")
EN = Translator("en")
START = datetime(2021, 1, 1)
PNG = b"\x89PNG\r\n\x1a\n"


def summary(columns, hours, step=1.0, start=START):
    """A carrier with flows that are given as functions of the number of the step (or as constants)."""

    steps = round(hours / step)
    names = list(columns)
    values = [[(columns[n](i) if callable(columns[n]) else columns[n]) for i in range(steps)] for n in names]
    flows = FlowTable(start=start, step_hours=step, columns=names, values=values) if names else None

    return BusSummary(energy_sums={}, supply=Table(columns=[]), use=Table(columns=[]), flows=flows)


FLOWS = {"pv-->electricity": 2.0, "grid_import-->electricity": 1.0, "electricity-->demand": 3.0, "electricity-->heating_rod": 0.5}
TWO_MONTHS = 59 * 24


def image(png):
    return Image.open(io.BytesIO(png))


# ---------------------------------------------------------------------------
# the flows over time
# ---------------------------------------------------------------------------

def test_a_period_of_two_weeks_or_less_is_drawn_with_every_hour():
    data = charts.flows_data("electricity", summary(FLOWS, 14 * 24), EN)

    assert not data.daily and len(data.index) == 14 * 24
    assert [l.name for l in data.supplies] == ["Grid import", "PV"] and [l.name for l in data.uses] == ["Heating rod"]


def test_a_longer_period_is_drawn_as_the_mean_of_each_day():
    flows = summary({"pv-->electricity": lambda i: float(i % 24), "electricity-->demand": 5.0}, 30 * 24)

    data = charts.flows_data("electricity", flows, EN)

    assert data.daily and len(data.index) == 30
    assert list(data.supplies[0].values) == [11.5] * 30                      # the mean of 0 to 23
    assert data.demand.values[0] == 5.0


def test_a_step_of_half_an_hour_counts_in_the_length_of_the_period():
    short = charts.flows_data("electricity", summary(FLOWS, 14 * 24, step=0.5), EN)
    long = charts.flows_data("electricity", summary(FLOWS, 15 * 24, step=0.5), EN)

    assert not short.daily and long.daily


def test_each_line_has_the_colour_of_its_component_and_the_demand_is_the_dark_line():
    data = charts.flows_data("electricity", summary(FLOWS, 48), EN)

    assert [l.color for l in data.supplies] == [COLORS["grid_import"], COLORS["pv"]]
    assert data.uses[0].color == COLORS["heating_rod"] and (data.demand.color, data.demand.name) == (DEMAND_LINE, "Demand")


def test_the_names_are_in_the_language_of_the_reader():
    data = charts.flows_data("electricity", summary(FLOWS, 48), DE)

    assert [l.name for l in data.supplies] == ["Netzbezug", "PV-Anlage"] and data.demand.name == "Bedarf"


def test_a_flow_that_is_zero_all_the_time_is_not_a_line():
    data = charts.flows_data("electricity", summary({**FLOWS, "wind-->electricity": 0.0, "electricity-->battery": 0.0}, 48), EN)

    assert "Wind turbine" not in [l.name for l in data.supplies] and "Battery" not in [l.name for l in data.uses]


def test_without_flows_there_is_no_data_and_a_carrier_without_a_flow_has_data_without_lines():
    assert charts.flows_data("electricity", summary({}, 48), EN) is None
    dead = charts.flows_data("gas", summary({"gas_import-->gas": 0.0, "gas-->chp": 0.0}, 48), EN)

    assert dead.supplies == [] and dead.uses == [] and dead.demand is None


# ---------------------------------------------------------------------------
# the energy of each month
# ---------------------------------------------------------------------------

def test_the_energy_of_each_month_is_the_power_times_the_hours_of_that_month():
    data = charts.monthly_data("electricity", summary(FLOWS, TWO_MONTHS), EN)

    assert [m.month for m in data.months] == [1, 2]
    assert list(data.supplies[1].values) == [2.0 * 744, 2.0 * 672] and data.supplies[1].name == "PV"
    assert list(data.demand.values) == [3.0 * 744, 3.0 * 672] and list(data.uses[0].values) == [0.5 * 744, 0.5 * 672]


@pytest.mark.parametrize("hours", [24, 31 * 24])
def test_a_period_within_one_month_has_no_monthly_data(hours):
    assert charts.monthly_data("electricity", summary(FLOWS, hours), EN) is None


def test_a_half_hour_step_gives_half_the_energy_of_the_power():
    data = charts.monthly_data("electricity", summary({"pv-->electricity": 1.0}, TWO_MONTHS, step=0.5), EN)

    assert list(data.supplies[0].values) == [744.0, 672.0]


# ---------------------------------------------------------------------------
# the duration curve
# ---------------------------------------------------------------------------

def test_each_flow_is_sorted_from_the_highest_to_the_lowest_against_the_hours():
    flows = summary({"electricity-->demand": [1.0, 3.0, 2.0].__getitem__, "pv-->electricity": [0.0, 4.0, 1.0].__getitem__}, 3)

    data = charts.duration_data("electricity", flows, EN)

    assert [l.name for l in data.lines] == ["Demand", "PV"]
    assert list(data.lines[0].values) == [3.0, 2.0, 1.0] and list(data.lines[1].values) == [4.0, 1.0, 0.0]
    assert list(data.hours) == [1.0, 2.0, 3.0]


def test_a_year_is_thinned_out_to_a_thousand_points_that_keep_the_highest_and_the_lowest():
    flows = summary({"electricity-->demand": lambda i: float((i * 37) % 8761)}, 8760)

    data = charts.duration_data("electricity", flows, EN)
    values = [float((i * 37) % 8761) for i in range(8760)]

    assert len(data.hours) == 1000 and data.lines[0].values[0] == max(values) and data.lines[0].values[-1] == min(values)
    assert data.hours[0] == 1.0 and data.hours[-1] == pytest.approx(8760.0)
    assert all(a >= b for a, b in zip(data.lines[0].values, data.lines[0].values[1:]))


def test_a_use_is_named_as_one_in_the_language_of_the_reader():
    flows = summary({"battery-->electricity": 1.0, "electricity-->battery": 2.0}, 24)

    assert [l.name for l in charts.duration_data("electricity", flows, EN).lines] == ["Battery", "Battery (use)"]
    assert [l.name for l in charts.duration_data("electricity", flows, DE).lines] == ["Batteriespeicher", "Batteriespeicher (Verwendung)"]


def test_the_hours_follow_the_length_of_the_steps():
    data = charts.duration_data("electricity", summary({"electricity-->demand": 1.0}, 6, step=0.5), EN)

    assert list(data.hours) == [0.5 * k for k in range(1, 13)]


def test_a_carrier_without_flows_has_no_duration_data():
    assert charts.duration_data("electricity", summary({}, 24), EN) is None


# ---------------------------------------------------------------------------
# the costs
# ---------------------------------------------------------------------------

def test_the_costs_are_sorted_from_the_revenues_to_the_highest_item_with_the_colour_of_each_component():
    data = charts.costs_data(sample_result(24), EN)

    assert data.labels == ["Grid feed-in", "PV", "Heating rod", "Grid import"]
    assert data.values == [-8400.0, 8400.0, 19080.3, 36272.7]
    assert data.colors[1] == COLORS["pv"] and data.colors[2] == COLORS["heating_rod"]


def test_a_cost_item_that_is_nearly_zero_is_left_out_and_without_costs_there_is_no_data():
    result = sample_result(24)
    result.cost_breakdown = Table(columns=result.cost_breakdown.columns, rows=[["PV", "Investment and fixed O&M", 0.2]])

    assert charts.costs_data(result, EN) is None
    assert charts.costs_data(sample_result(24, costs=False), EN) is None
    result.cost_breakdown = Table(columns=["Something", "Else"], rows=[["a", 1]])
    assert charts.costs_data(result, EN) is None


def test_of_very_many_cost_items_the_chart_has_the_largest_ones_in_order():
    result = sample_result(24)
    result.cost_breakdown = Table(columns=result.cost_breakdown.columns, rows=[
        [f"Item {i}", "Energy purchase", float(i) - 40.0] for i in range(120)])

    data = charts.costs_data(result, EN)

    assert len(data.labels) == charts.MAX_COST_ITEMS == 20
    assert data.values == [float(v) for v in range(60, 80)]                   # the 20 largest in size, from the lowest to the highest
    assert data.labels[0] == "Item 100" and data.labels[-1] == "Item 119"


# ---------------------------------------------------------------------------
# a number on an axis
# ---------------------------------------------------------------------------

class FakeAxes:
    def __init__(self, ticks):
        self.ticks = ticks

    def get_yticks(self):
        return self.ticks

    get_xticks = get_yticks


@pytest.mark.parametrize("ticks, value, english, german", [
    ([0, 1000, 2000], 2000.0, "2,000", "2.000"),
    ([1.0, 1.5, 2.0], 1.5, "1.5", "1,5"),                                  # a small range gets decimals: not 1, 2, 2
    ([0.0, 0.25, 0.5], 0.25, "0.25", "0,25"),                              # a quarter needs two decimals
    ([0.0, 0.5, 1.0], 0.5, "0.5", "0,5"),
    ([0.0, 0.1, 0.2], 0.1, "0.1", "0,1"),
    ([0, 5, 10], 5.0, "5", "5"),
])
def test_a_number_on_an_axis_has_decimals_only_when_the_range_is_small_and_the_signs_of_the_reader(ticks, value, english, german):
    assert charts._number(EN, FakeAxes(ticks))(value, 0) == english
    assert charts._number(DE, FakeAxes(ticks))(value, 0) == german


def test_a_number_without_axes_has_no_decimals():
    assert charts._number(EN)(1234.6, 0) == "1,235"


# ---------------------------------------------------------------------------
# the drawing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["flows", "monthly", "duration"])
def test_each_chart_of_a_carrier_is_a_picture_as_wide_as_the_text_of_the_page(kind):
    result = sample_result(TWO_MONTHS)

    png = charts.chart_png(ChartRef(kind, "x", "electricity"), result, EN)

    assert png.startswith(PNG) and len(png) > 8_000
    picture = image(png)
    assert 1000 < picture.width < 1400 and 400 < picture.height < 800        # about 17 cm at 200 dpi, about 6 cm high


def test_the_chart_of_the_costs_is_as_high_as_the_number_of_items_needs():
    result = sample_result(24)
    few = image(charts.chart_png(ChartRef("costs", ""), result, EN))
    result.cost_breakdown = Table(columns=result.cost_breakdown.columns, rows=[[f"Item {i}", "Energy purchase", 100.0 * (i + 1)] for i in range(12)])
    many = image(charts.chart_png(ChartRef("costs", ""), result, EN))

    assert many.height > few.height * 1.8 and many.width == pytest.approx(few.width, rel=0.15)


def test_another_language_or_other_data_gives_another_picture():
    result = sample_result(TWO_MONTHS)
    ref = ChartRef("monthly", "x", "electricity")

    assert charts.chart_png(ref, result, EN) != charts.chart_png(ref, result, DE)
    assert charts.chart_png(ref, result, EN) != charts.chart_png(ref, sample_result(TWO_MONTHS + 24 * 31), EN)


def test_there_is_no_picture_when_there_is_nothing_to_draw():
    result = sample_result(24)

    assert charts.chart_png(ChartRef("monthly", "x", "electricity"), result, EN) is None        # one month
    assert charts.chart_png(ChartRef("flows", "x", "gas"), result, EN) is None                  # nothing flows
    assert charts.chart_png(ChartRef("flows", "x", "hydrogen"), result, EN) is None             # no such carrier
    assert charts.chart_png(ChartRef("costs", ""), sample_result(24, costs=False), EN) is None
    assert charts.chart_png(ChartRef("flows", "x", "electricity"), sample_result(24, with_flows=False), EN) is None


def test_a_year_of_hourly_values_is_drawn_quickly_and_the_picture_is_not_heavy():
    import time

    result = sample_result(8760)
    started = time.time()
    pictures = [charts.chart_png(ChartRef(kind, "x", "electricity"), result, EN) for kind in ("flows", "monthly", "duration")]

    assert time.time() - started < 15 and all(len(p) < 250_000 for p in pictures)


def test_the_picture_does_not_use_the_global_state_of_matplotlib():
    import matplotlib.pyplot  # noqa: F401  (only to look at the open figures)

    before = matplotlib.pyplot.get_fignums()
    charts.chart_png(ChartRef("flows", "x", "electricity"), sample_result(48), EN)

    assert matplotlib.pyplot.get_fignums() == before


def test_the_values_are_numpy_numbers_of_the_length_of_the_period():
    data = charts.flows_data("electricity", summary(FLOWS, 48), EN)

    assert isinstance(data.supplies[0].values, np.ndarray) and len(data.supplies[0].values) == 48