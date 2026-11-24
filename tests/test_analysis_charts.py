"""The charts of the analysis of a load profile: what is drawn, in which colour, and with which words."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backend.holidays_de import STATES
from backend.i18n import Translator
from backend.load_analysis import analyze
from frontend_nicegui.analysis_charts import (
    BASE_COLORS,
    DAY_TYPE_COLORS,
    ENERGY_COLOR,
    ENERGY_COLOR_PALE,
    clock,
    duration_figure,
    month_label,
    monthly_figure,
    typical_days_figure,
)
from frontend_nicegui.analysis_view import STATE_TEXTS
from tests.test_load_analysis import ZONE, a_year, week

DE, EN = Translator("de"), Translator("en")


def named(figure, start):
    return next(trace for trace in figure.data if (trace.name or "").startswith(start))


# ---------------------------------------------------------------------------
# the typical days
# ---------------------------------------------------------------------------

def test_a_typical_day_is_drawn_for_each_type_of_day_with_a_band_and_a_line():
    figure = typical_days_figure(analyze(*week(days=21, spike=False)), EN)

    assert len(figure.data) == 9                                                     # for each of three types: upper, lower, mean
    lines = [trace for trace in figure.data if trace.showlegend is not False]
    assert [trace.name for trace in lines] == ["Workday (n = 15)", "Saturday (n = 3)", "Sunday or holiday (n = 3)"]
    assert [trace.line.color for trace in lines] == [DAY_TYPE_COLORS["workday"], DAY_TYPE_COLORS["saturday"], DAY_TYPE_COLORS["sunday"]]


def test_the_line_is_the_mean_and_the_band_is_between_the_lower_and_the_upper_quarter_of_the_days():
    series, step = week(days=21, spike=False)
    workdays = np.flatnonzero((series.index.dayofweek < 5) & (series.index.hour == 12))
    series.iloc[workdays] = np.arange(1, 16, dtype=float)

    figure = typical_days_figure(analyze(series, step), EN)
    upper, lower, mean = figure.data[0], figure.data[1], figure.data[2]

    assert (upper.y[12], lower.y[12], mean.y[12]) == (11.5, 4.5, 8.0)
    assert lower.fill == "tonexty" and upper.hoverinfo == "skip" and lower.hoverinfo == "skip"
    assert lower.fillcolor.startswith("rgba(0, 93, 157,") and mean.x[12] == 12.0 and mean.customdata[12] == "12:00"


def test_the_axis_is_the_time_of_day_with_a_tick_every_three_hours_and_the_power():
    figure = typical_days_figure(analyze(*week(days=21, spike=False)), EN)

    assert list(figure.layout.xaxis.tickvals) == [0, 3, 6, 9, 12, 15, 18, 21, 24]
    assert list(figure.layout.xaxis.ticktext)[:3] == ["00:00", "03:00", "06:00"] and list(figure.layout.xaxis.range) == [0, 24]
    assert figure.layout.xaxis.title.text == "Time of day" and figure.layout.yaxis.title.text == "Power (kW)"
    assert typical_days_figure(analyze(*week(days=21, spike=False)), DE).layout.xaxis.title.text == "Uhrzeit"


def test_a_type_of_day_with_too_few_days_is_not_drawn_and_without_any_typical_day_there_is_no_figure():
    one_week = typical_days_figure(analyze(*week()), EN)

    assert [trace.name for trace in one_week.data if trace.showlegend is not False] == ["Workday (n = 5)"]
    assert typical_days_figure(analyze(*week(days=2)), EN) is None


def test_the_times_of_day_of_quarter_hours_run_from_0_to_24_hours():
    figure = typical_days_figure(analyze(*week("15min")), EN)

    assert len(figure.data[2].x) == 96 and figure.data[2].x[1] == 0.25 and list(figure.layout.xaxis.range) == [0, 24]


def test_the_words_of_the_typical_days_are_in_german_for_a_german_page():
    figure = typical_days_figure(analyze(*week(days=21, spike=False)), DE)

    assert [trace.name for trace in figure.data if trace.showlegend is not False] == [
        "Werktag (n = 15)", "Samstag (n = 3)", "Sonn- und Feiertag (n = 3)"]
    assert figure.layout.yaxis.title.text == DE("result.chart.power") and "kW" in figure.layout.yaxis.title.text


def test_the_clock_writes_minutes_as_hours_and_minutes():
    assert clock(0) == "00:00" and clock(495) == "08:15" and clock(1425) == "23:45"


# ---------------------------------------------------------------------------
# the duration curve
# ---------------------------------------------------------------------------

def test_the_duration_curve_has_the_hours_and_the_load_of_the_analysis():
    analysis = analyze(*week())
    figure = duration_figure(analysis, EN)
    curve = figure.data[0]

    assert list(curve.x) == list(analysis.duration.hours) and list(curve.y) == list(analysis.duration.kw)
    assert curve.line.color == ENERGY_COLOR and curve.showlegend is False
    assert figure.layout.xaxis.title.text == "Hours of the period, sorted" and list(figure.layout.xaxis.range) == [0, 168.0]


def test_the_two_base_loads_are_dotted_lines_with_their_value_in_the_name():
    figure = duration_figure(analyze(*week()), EN)
    first, second = figure.data[1], figure.data[2]

    assert first.name == "Base load (95 % value): 20 kW" and second.name == "Base load (night): 20 kW"
    assert (first.line.dash, second.line.dash) == ("dot", "dot") and (first.line.color, second.line.color) == BASE_COLORS
    assert list(first.y) == [20.0, 20.0] and list(first.x) == [0, 168.0]
    assert duration_figure(analyze(*week()), DE).data[1].name == "Grundlast (95-%-Wert): 20 kW"


def test_a_profile_without_a_night_has_only_the_first_base_load_as_a_line():
    index = pd.date_range("2023-02-06 06:00", periods=12, freq="60min", tz=ZONE)

    figure = duration_figure(analyze(pd.Series(np.full(12, 40.0), index=index), 60), EN)

    assert len(figure.data) == 2 and figure.data[1].name.startswith("Base load (95 %")


# ---------------------------------------------------------------------------
# the months
# ---------------------------------------------------------------------------

def test_the_months_are_bars_of_the_energy_and_a_line_of_the_peak_on_a_second_axis():
    series, step = week(days=14, start="2023-01-30", spike=False)
    analysis = analyze(series, step)

    figure = monthly_figure(analysis, EN)
    bars, line = figure.data[0], figure.data[1]

    assert list(bars.x) == ["2023-01", "2023-02"] and list(line.x) == ["2023-01", "2023-02"]
    assert list(bars.y) == pytest.approx([month.energy_kwh for month in analysis.months]) and list(line.y) == [100.0, 100.0]
    assert line.yaxis == "y2" and figure.layout.yaxis2.overlaying == "y" and figure.layout.yaxis2.side == "right"
    assert figure.layout.yaxis.title.text == "Energy (kWh)" and figure.layout.yaxis2.title.text == "Peak (kW)"


def test_a_month_that_is_not_complete_is_pale():
    index = pd.date_range("2023-01-15", "2023-03-31 23:00", freq="60min", tz=ZONE)            # January from the 15th, February whole
    analysis = analyze(pd.Series(np.full(len(index), 30.0), index=index), 60)

    bars = monthly_figure(analysis, EN).data[0]

    assert list(bars.marker.color) == [ENERGY_COLOR_PALE, ENERGY_COLOR, ENERGY_COLOR]
    assert list(bars.customdata) == [17, 28, 31]


def test_a_month_with_a_gap_is_pale_even_if_every_day_has_a_value():
    series, step = a_year()
    series.iloc[24 * 40 + 5] = np.nan                                                          # one hour in February

    bars = monthly_figure(analyze(series, step), EN).data[0]

    assert bars.marker.color[0] == ENERGY_COLOR and bars.marker.color[1] == ENERGY_COLOR_PALE and bars.marker.color[2] == ENERGY_COLOR


def test_the_months_are_written_as_the_language_writes_them():
    month = SimpleNamespace(year=2023, month=3)

    assert month_label(month, EN) == "2023-03" and month_label(month, DE) == "03.2023"


def test_no_months_give_no_figure():
    assert monthly_figure(SimpleNamespace(months=[]), EN) is None


def test_the_hover_text_of_the_bars_names_the_days_with_values_in_each_language():
    series, step = week(days=14, start="2023-01-30", spike=False)
    analysis = analyze(series, step)

    assert "Days with values:" in monthly_figure(analysis, EN).data[0].hovertemplate
    assert "Tage mit Werten:" in monthly_figure(analysis, DE).data[0].hovertemplate


# ---------------------------------------------------------------------------
# all of them
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("make", [typical_days_figure, duration_figure, monthly_figure])
def test_every_chart_has_the_fonts_of_the_other_charts_and_a_white_template(make):
    figure = make(analyze(*week(days=21, spike=False)), EN)

    assert figure.layout.font.size == 15 and figure.layout.xaxis.tickfont.size == 15 and figure.layout.template.layout.plot_bgcolor is not None


def test_a_year_of_quarter_hours_gives_the_three_charts_quickly():
    import time

    analysis = analyze(*a_year(freq="15min"))
    started = time.time()

    figures = [typical_days_figure(analysis, EN), duration_figure(analysis, EN), monthly_figure(analysis, EN)]

    assert time.time() - started < 10 and all(figure is not None for figure in figures)
    assert len(figures[1].data[0].x) <= 600


def test_every_state_has_a_name_in_both_languages_and_the_names_are_not_the_keys():
    assert set(STATE_TEXTS) == set(STATES)
    for tr in (EN, DE):
        names = [tr(key) for key in STATE_TEXTS.values()]
        assert all(name and not name.startswith("state.") for name in names) and len(set(names)) == 16