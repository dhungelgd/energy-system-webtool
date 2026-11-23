"""The analysis of a load profile: the figures, the peaks, the typical days, and that nothing is made up."""

import pickle
import time
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.holidays_de import SATURDAY, SUNDAY, WORKDAY
from backend.i18n import Translator
from backend.load_analysis import (
    TOP_PEAKS,
    AnalysisHint,
    AnalysisOptions,
    analysis_text,
    analyze,
    default_year,
    years_of,
)

ZONE = "Europe/Berlin"
DE, EN = Translator("de"), Translator("en")


def week(freq="60min", start="2023-02-06 00:00", days=7, tz=ZONE, spike=True):
    """A week from a Monday: 100 kW on workdays from 8:00 to 16:00, 20 kW at all other times, and (if `spike`) 150 kW on
    the Wednesday at 10:00. The figures of it can be worked out by hand."""

    steps = {"60min": 1, "30min": 2, "15min": 4}[freq]
    index = pd.date_range(start, periods=days * 24 * steps, freq=freq, tz=tz)
    values = np.where((index.dayofweek < 5) & (index.hour >= 8) & (index.hour < 16), 100.0, 20.0)
    if spike:
        values[(index.dayofweek == 2) & (index.hour == 10)] = 150.0                  # the whole hour

    return pd.Series(values, index=index), int(freq[:-3])


def a_year(year=2023, freq="60min", level=50.0, tz=ZONE):
    index = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq=freq, tz=tz, inclusive="left")

    return pd.Series(np.full(len(index), level), index=index), int(freq[:-3])


def run(series_and_step, **options):
    series, step = series_and_step

    return analyze(series, step, AnalysisOptions(**options))


# ---------------------------------------------------------------------------
# the key figures
# ---------------------------------------------------------------------------

def test_the_key_figures_of_a_week_are_those_that_can_be_worked_out_by_hand():
    kpis = run(week()).kpis

    assert kpis.energy_kwh == 6610.0                                   # 5 x (8 x 100 + 16 x 20) + 2 x 24 x 20 + 50
    assert kpis.mean_kw == pytest.approx(6610 / 168) and kpis.min_kw == 20.0 and kpis.peak_kw == 150.0
    assert kpis.peak_time == pd.Timestamp("2023-02-08 10:00", tz=ZONE)
    assert kpis.load_factor == pytest.approx(6610 / 168 / 150)
    assert kpis.values == 168 and kpis.missing_share == 0.0 and kpis.days == 7.0
    assert kpis.start == pd.Timestamp("2023-02-06 00:00", tz=ZONE) and kpis.end == pd.Timestamp("2023-02-13 00:00", tz=ZONE)


def test_the_first_base_load_is_the_load_that_is_exceeded_95_percent_of_the_time():
    kpis = run(week()).kpis

    assert kpis.base_percentile_kw == 20.0                             # 128 of 168 hours are at 20 kW

    series, step = week(spike=False)
    series[series == 20.0] = np.linspace(1, 100, int((series == 20.0).sum()))
    assert analyze(series, step).kpis.base_percentile_kw == pytest.approx(series.quantile(0.05))


def test_the_second_base_load_is_the_mean_of_the_lowest_value_of_each_night():
    index = pd.date_range("2023-02-06", periods=3 * 24, freq="60min", tz=ZONE)
    values = np.full(len(index), 50.0)
    values[3], values[24 + 1], values[48 + 0] = 10.0, 30.0, 20.0             # the nights of the three days: 10, 30, 20
    values[30] = 5.0                                                          # 6:00 on the second day: not at night

    kpis = analyze(pd.Series(values, index=index), 60).kpis

    assert kpis.base_night_kw == pytest.approx(20.0)


def test_a_night_is_from_0_to_5_o_clock_and_a_profile_without_a_night_has_no_second_base_load():
    index = pd.date_range("2023-02-06 06:00", periods=12, freq="60min", tz=ZONE)

    assert analyze(pd.Series(np.full(12, 40.0), index=index), 60).kpis.base_night_kw is None

    index = pd.date_range("2023-02-06 00:00", periods=24, freq="60min", tz=ZONE)
    values = np.full(24, 40.0)
    values[5] = 1.0                                                           # 5:00 is not in the night
    values[4] = 7.0

    assert analyze(pd.Series(values, index=index), 60).kpis.base_night_kw == 7.0


def test_the_hours_near_the_peak_and_the_days_on_which_that_happens_are_counted():
    series, step = week()
    series[(series.index.dayofweek == 4) & (series.index.hour == 9)] = 140.0     # a Friday hour above 135 kW

    kpis = analyze(series, step).kpis

    assert kpis.hours_near_peak == 2.0 and kpis.days_near_peak == 2


def test_a_week_has_no_figure_of_a_year_and_a_year_has():
    assert run(week()).kpis.yearly is False and run(week()).kpis.utilization_hours is None
    series, step = a_year()
    series.iloc[100] = 100.0                                                  # 50 kW all year and one hour of 100 kW

    kpis = analyze(series, step).kpis

    assert kpis.yearly is True and kpis.energy_kwh == 50 * 8760 + 50
    assert kpis.utilization_hours == pytest.approx((50 * 8760 + 50) / 100)
    assert kpis.load_factor == pytest.approx((50 * 8760 + 50) / 8760 / 100)


def test_330_days_are_enough_for_the_figures_of_a_year_and_329_are_not():
    long_enough = pd.Series(np.full(330 * 24, 10.0), index=pd.date_range("2023-01-01", periods=330 * 24, freq="60min", tz=ZONE))
    too_short = long_enough.iloc[:329 * 24]

    assert analyze(long_enough, 60).kpis.yearly and not analyze(too_short, 60).kpis.yearly


def test_a_gap_is_left_out_of_the_figures_and_the_energy_of_the_period_is_estimated_with_the_mean():
    series, step = week(spike=False)
    series.iloc[24:48] = np.nan                                               # all of Tuesday

    kpis = analyze(series, step).kpis

    assert kpis.values == 144 and kpis.missing_share == pytest.approx(24 / 168) and kpis.days == 7.0
    assert kpis.energy_kwh == 6560 - 1120                                     # the week without Tuesday
    assert kpis.energy_estimate_kwh == pytest.approx((6560 - 1120) / 144 * 168)


def test_the_peak_is_the_highest_value_that_there_is_and_a_missing_value_is_not_the_peak():
    series, step = week()
    series[series == 150.0] = np.nan

    kpis = analyze(series, step).kpis

    assert kpis.peak_kw == 100.0 and kpis.peak_time == pd.Timestamp("2023-02-06 08:00", tz=ZONE)       # the first of equal ones


def test_a_profile_without_any_value_cannot_be_analysed():
    series, step = week()

    with pytest.raises(ValueError, match="no values"):
        analyze(series * np.nan, step)


# ---------------------------------------------------------------------------
# the time step
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("freq", ["15min", "30min", "60min"])
def test_a_time_step_of_a_quarter_hour_or_more_is_kept_and_gives_the_same_energy_and_peak(freq):
    analysis = run(week(freq))

    assert analysis.step_minutes == int(freq[:-3]) and analysis.kpis.energy_kwh == 6610.0 and analysis.kpis.peak_kw == 150.0


def test_values_in_minutes_are_averaged_to_quarter_hours_and_the_peak_is_that_of_the_quarter_hour():
    index = pd.date_range("2023-02-06", periods=3 * 24 * 60, freq="1min", tz=ZONE)
    values = np.full(len(index), 100.0)
    values[600] = 700.0                                                       # one minute of 700 kW

    analysis = analyze(pd.Series(values, index=index), 1)

    assert analysis.step_minutes == 15
    assert analysis.kpis.peak_kw == pytest.approx(100 + 600 / 15)             # the quarter-hour that holds the minute
    assert analysis.kpis.energy_kwh == pytest.approx((100 * len(index) + 600) / 60)


def test_the_series_that_is_given_is_not_changed():
    series, step = week()
    before = series.copy()

    analyze(series, step)

    assert series.equals(before)


# ---------------------------------------------------------------------------
# the period and the state
# ---------------------------------------------------------------------------

def test_the_years_of_a_profile_and_the_days_of_each_that_have_a_value():
    series = pd.Series(np.full(2 * 365 * 24 + 10 * 24, 5.0), index=pd.date_range("2022-01-01", periods=2 * 365 * 24 + 10 * 24, freq="60min", tz=ZONE))

    assert years_of(series) == [(2022, 365), (2023, 365), (2024, 10)]


def test_a_profile_of_more_than_a_year_is_analysed_for_the_latest_whole_calendar_year_by_default():
    series = pd.Series(np.full(2 * 365 * 24 + 10 * 24, 5.0), index=pd.date_range("2022-01-01", periods=2 * 365 * 24 + 10 * 24, freq="60min", tz=ZONE))

    assert default_year(series, 60) == 2023


def test_a_profile_of_up_to_370_days_or_without_a_whole_year_is_analysed_as_a_whole():
    year, step = a_year()
    long_without = pd.Series(np.full(405 * 24, 5.0), index=pd.date_range("2022-11-01", periods=405 * 24, freq="60min", tz=ZONE))

    assert default_year(year, step) is None and default_year(long_without, 60) is None


def test_a_calendar_year_can_be_chosen_and_then_only_that_year_is_analysed():
    series = pd.Series(np.arange(2 * 365 * 24, dtype=float), index=pd.date_range("2022-01-01", periods=2 * 365 * 24, freq="60min", tz=ZONE))

    analysis = analyze(series, 60, AnalysisOptions(year=2023))

    assert analysis.year == 2023 and analysis.kpis.start == pd.Timestamp("2023-01-01", tz=ZONE)
    assert analysis.kpis.values == 8760 and analysis.kpis.peak_kw == 2 * 365 * 24 - 1 and analysis.years == [(2022, 365), (2023, 365)]
    assert analyze(series, 60).year is None and analyze(series, 60).kpis.values == 2 * 8760


def test_a_year_that_the_profile_does_not_have_is_refused():
    series, step = week()

    with pytest.raises(ValueError, match="no values in 2021"):
        analyze(series, step, AnalysisOptions(year=2021))


def test_the_state_decides_which_days_are_holidays():
    two_weeks = week(days=14, start="2023-01-02")                             # the 6th of January is a Friday

    bavaria, north_rhine = run(two_weeks, state="BY"), run(two_weeks, state="NW")

    assert bavaria.day_type_days == {WORKDAY: 9, SATURDAY: 2, SUNDAY: 3}
    assert north_rhine.day_type_days == {WORKDAY: 10, SATURDAY: 2, SUNDAY: 2}


def test_the_assumption_counts_in_a_catholic_municipality_of_bavaria_only():
    august = week(days=7, start="2023-08-14")

    assert run(august, state="BY").day_type_days[WORKDAY] == 4
    assert run(august, state="BY", catholic_municipality=False).day_type_days[WORKDAY] == 5


def test_a_state_that_does_not_exist_is_refused():
    with pytest.raises(ValueError):
        AnalysisOptions(state="XX")


# ---------------------------------------------------------------------------
# the peaks
# ---------------------------------------------------------------------------

def test_the_highest_peaks_are_one_for_each_day_the_highest_first_and_the_earlier_day_first_when_equal():
    peaks = run(week()).peaks

    assert [(p.time.strftime("%a %H:%M"), p.kw) for p in peaks] == [
        ("Wed 10:00", 150.0), ("Mon 08:00", 100.0), ("Tue 08:00", 100.0), ("Thu 08:00", 100.0), ("Fri 08:00", 100.0)]
    assert len(peaks) == TOP_PEAKS and all(p.day_type == WORKDAY and p.season == "winter" for p in peaks)


def test_two_high_values_on_the_same_day_make_one_peak_and_a_peak_knows_its_kind_of_day():
    series, step = week()
    series[(series.index.dayofweek == 5) & (series.index.hour.isin([9, 17]))] = [130.0, 120.0]

    peaks = analyze(series, step).peaks

    assert [p.kw for p in peaks[:3]] == [150.0, 130.0, 100.0]
    assert peaks[1].day_type == SATURDAY and peaks[1].time.strftime("%a %H:%M") == "Sat 09:00"


def test_fewer_days_than_five_give_fewer_peaks():
    series, step = week(days=3)

    assert len(analyze(series, step).peaks) == 3


# ---------------------------------------------------------------------------
# the duration curve
# ---------------------------------------------------------------------------

def test_the_duration_curve_has_the_values_from_the_highest_to_the_lowest_and_the_hours_that_each_is_reached():
    curve = run(week()).duration

    assert curve.total_hours == 168.0 and curve.kw[0] == 150.0 and curve.kw[-1] == 20.0
    assert curve.hours[0] == 1.0 and curve.hours[-1] == 168.0
    assert curve.kw[39] == 100.0 and curve.kw[40] == 20.0                     # 40 hours are at 100 kW or more, with the peak
    assert np.all(np.diff(curve.kw) <= 0) and np.all(np.diff(curve.hours) > 0)


def test_a_long_profile_has_a_curve_of_a_few_hundred_points_that_still_has_the_highest_and_the_lowest_value():
    series, step = a_year(freq="15min")
    series.iloc[1000], series.iloc[2000] = 99.0, 1.0

    curve = analyze(series, step).duration

    assert len(curve.kw) <= 600 and curve.kw[0] == 99.0 and curve.kw[-1] == 1.0
    assert curve.hours[0] == 0.25 and curve.hours[-1] == pytest.approx(8760.0) and curve.total_hours == 8760.0


def test_a_gap_is_not_in_the_duration_curve():
    series, step = week()
    series.iloc[:24] = np.nan

    curve = analyze(series, step).duration

    assert curve.total_hours == 144.0 and curve.hours[-1] == 144.0


# ---------------------------------------------------------------------------
# the typical days
# ---------------------------------------------------------------------------

def typical(analysis, season=None, kind=WORKDAY):
    return next((t for t in analysis.typical_days if t.season == season and t.day_type == kind), None)


def test_the_typical_workday_of_a_week_has_the_mean_and_the_middle_half_of_the_five_days_at_each_time():
    day = typical(run(week()))

    assert day.days == 5 and day.slots == list(range(0, 1440, 60))
    assert day.mean[10] == 110.0 and day.p25[10] == 100.0 and day.p75[10] == 100.0        # 100, 100, 150, 100, 100
    assert day.mean[3] == 20.0 and day.mean[12] == 100.0


def test_the_lower_and_the_upper_quarter_of_the_typical_day_are_the_25th_and_the_75th_percentile_of_the_days():
    series, step = week(days=21, spike=False)
    workdays = np.flatnonzero((series.index.dayofweek < 5) & (series.index.hour == 12))
    series.iloc[workdays] = np.arange(1, 16, dtype=float)                       # the 15 workdays: 1, 2, ... 15 kW at 12:00

    day = typical(analyze(series, step))

    assert day.mean[12] == 8.0 and day.p25[12] == 4.5 and day.p75[12] == 11.5
    assert day.p25[3] == day.p75[3] == 20.0                                       # at 3:00 all the days are the same


def test_a_type_of_day_that_has_fewer_than_three_days_has_no_typical_day():
    analysis = run(week())

    assert typical(analysis, None, SATURDAY) is None and typical(analysis, None, SUNDAY) is None


def test_with_three_weeks_the_saturdays_and_sundays_have_typical_days_too():
    analysis = run(week(days=21, spike=False))

    assert typical(analysis, None, SATURDAY).days == 3 and typical(analysis, None, SUNDAY).days == 3
    assert set(typical(analysis, None, SATURDAY).mean) == {20.0} and typical(analysis, None, WORKDAY).days == 15


def test_the_typical_days_are_given_for_all_seasons_together_and_for_each_season_that_has_enough_days():
    index = pd.date_range("2023-03-06", "2023-03-26 23:00", freq="60min", tz=ZONE)       # winter to March 20, then the transition
    series = pd.Series(np.where((index.dayofweek < 5) & (index.hour >= 8) & (index.hour < 16), 100.0, 20.0), index=index)

    analysis = analyze(series, 60)

    assert typical(analysis, "winter", WORKDAY).days == 11 and typical(analysis, "transition", WORKDAY).days == 4
    assert typical(analysis, "summer", WORKDAY) is None                       # March 6 to 20 is winter, March 21 to 24 the transition
    assert typical(analysis, None, WORKDAY).days == 15


def test_the_hours_of_a_profile_of_quarter_hours_are_96_times_of_day():
    day = typical(run(week("15min")))

    assert len(day.slots) == 96 and day.slots[:3] == [0, 15, 30] and day.slots[-1] == 1425
    assert day.mean[40] == 110.0                                              # 10:00


def test_a_holiday_is_a_sunday_and_not_a_workday_in_the_typical_days():
    series, step = week(days=21, start="2023-04-03", spike=False)             # Good Friday and Easter Monday inside

    analysis = analyze(series, step)

    assert typical(analysis, None, WORKDAY).days == 13 and typical(analysis, None, SUNDAY).days == 5     # 3 Sundays + 2 holidays


# ---------------------------------------------------------------------------
# the clock change in the typical days and the heat map
# ---------------------------------------------------------------------------

def test_a_year_in_local_time_has_one_value_for_each_time_of_day_in_the_typical_days_despite_the_clock_change():
    series, step = a_year(freq="15min", level=40.0)

    analysis = analyze(series, step)

    assert all(len(t.slots) == 96 and set(t.mean) == {40.0} for t in analysis.typical_days)
    assert analysis.kpis.energy_kwh == pytest.approx(40.0 * 8760)


def test_the_heat_map_shows_the_day_of_the_clock_change_with_the_missing_hour_empty_and_the_doubled_hour_averaged():
    series, step = a_year(freq="15min", level=40.0)
    autumn = series.index[(series.index.tz_localize(None).date == date(2023, 10, 29)) & (series.index.hour == 2)]
    series[autumn[:4]], series[autumn[4:]] = 10.0, 30.0                       # the first and the second 2:00 to 3:00

    heat = analyze(series, step).heatmap
    spring_row = heat.dates.index(date(2023, 3, 26))
    autumn_row = heat.dates.index(date(2023, 10, 29))

    assert len(heat.dates) == 365 and heat.slots[:2] == [0, 15] and heat.values.shape == (365, 96)
    assert np.isnan(heat.values[spring_row, 8:12]).all() and not np.isnan(heat.values[spring_row, 12])        # 2:00 to 3:00 is not there
    assert list(heat.values[autumn_row, 8:12]) == [20.0] * 4                                                    # the mean of 10 and 30


def test_the_heat_map_has_a_row_for_each_day_and_a_column_for_each_time_with_the_values_in_kw_and_gaps_empty():
    series, step = week()
    series.iloc[26] = np.nan                                                  # Tuesday 2:00

    heat = analyze(series, step).heatmap

    assert heat.dates == [date(2023, 2, 6) + pd.Timedelta(days=i) for i in range(7)] and heat.values.shape == (7, 24)
    assert heat.values[2, 10] == 150.0 and heat.values[0, 8] == 100.0 and heat.values[5, 8] == 20.0
    assert np.isnan(heat.values[1, 2]) and np.isnan(heat.values).sum() == 1


def test_a_first_and_a_last_day_that_are_not_whole_have_empty_cells_for_the_time_that_the_profile_does_not_cover():
    index = pd.date_range("2023-02-06 18:00", "2023-02-08 05:00", freq="60min", tz=ZONE)

    heat = analyze(pd.Series(np.full(len(index), 30.0), index=index), 60).heatmap

    assert heat.values.shape == (3, 24) and np.isnan(heat.values[0, :18]).all() and not np.isnan(heat.values[0, 18:]).any()
    assert not np.isnan(heat.values[2, :6]).any() and np.isnan(heat.values[2, 6:]).all()


# ---------------------------------------------------------------------------
# the months, the weekdays
# ---------------------------------------------------------------------------

def test_the_energy_and_the_peak_of_each_month_and_how_much_of_it_is_missing():
    series, step = week(days=14, start="2023-01-30", spike=False)             # a day in January, then February
    series.iloc[24:36] = np.nan                                               # half of January 31

    months = analyze(series, step).months

    assert [(m.year, m.month) for m in months] == [(2023, 1), (2023, 2)]
    january, february = months
    assert january.days == 2 and january.missing_share == pytest.approx(12 / 48)
    assert january.energy_kwh == pytest.approx(series[:48].sum()) and february.energy_kwh == pytest.approx(series[48:].sum())
    assert february.days == 12 and february.missing_share == 0.0 and february.peak_kw == 100.0
    assert january.energy_kwh + february.energy_kwh == analyze(series, step).kpis.energy_kwh


def test_the_mean_of_each_weekday_and_none_for_a_weekday_that_the_profile_does_not_have():
    weekdays = run(week()).weekdays

    assert weekdays == pytest.approx([1120 / 24, 1120 / 24, 1170 / 24, 1120 / 24, 1120 / 24, 20.0, 20.0])
    assert run(week(days=5)).weekdays[5:] == [None, None]


# ---------------------------------------------------------------------------
# the hints
# ---------------------------------------------------------------------------

def hints(analysis):
    return {hint.code: hint for hint in analysis.hints}


def test_the_hint_about_the_peak_says_how_rare_it_is():
    hint = hints(run(week()))["peak_rare"]

    assert hint.params["limit"].value == pytest.approx(135.0) and hint.params["hours"].value == 1.0 and hint.params["days"] == 1
    assert "only 1.0 hours" in analysis_text(hint, EN) and "nur in 1,0 Stunden" in analysis_text(hint, DE)


def test_a_base_load_that_is_more_than_half_of_the_mean_is_called_high_and_one_below_a_fifth_low():
    assert "base_high" in hints(run(week())) and hints(run(week()))["base_high"].params["share"].value == pytest.approx(100 * 20 / (6610 / 168))

    series, step = week(spike=False)
    series[series == 20.0] = 2.0

    found = hints(analyze(series, step))
    assert "base_low" in found and "base_high" not in found


def test_the_load_on_saturdays_sundays_and_holidays_is_compared_with_that_of_a_workday():
    low = hints(run(week(days=21, spike=False)))["weekend_low"]

    assert low.params["share"].value == pytest.approx(100 * 20 / ((8 * 100 + 16 * 20) / 24))

    series = pd.Series(np.full(21 * 24, 50.0), index=pd.date_range("2023-02-06", periods=21 * 24, freq="60min", tz=ZONE))
    found = hints(analyze(series, 60))
    assert found["weekend_similar"].params["share"].value == 100.0 and "weekend_low" not in found


def test_a_week_has_no_hint_about_the_weekend_because_it_has_too_few_such_days():
    assert "weekend_low" not in hints(run(week())) and "weekend_similar" not in hints(run(week()))


def test_the_highest_peaks_of_days_that_fall_in_a_short_time_of_day_are_named_with_that_time():
    found = hints(run(week()))

    assert found["peak_window"].params == {"start": "08:00", "end": "10:00"}
    assert "between 08:00 and 10:00" in analysis_text(found["peak_window"], EN)


def test_peaks_that_are_spread_over_the_day_have_no_time_named():
    series, step = week(spike=False)
    series[(series.index.dayofweek == 0) & (series.index.hour == 8)] = 120.0
    series[(series.index.dayofweek == 1) & (series.index.hour == 11)] = 121.0
    series[(series.index.dayofweek == 2) & (series.index.hour == 14)] = 122.0       # six hours from the first to the last

    assert "peak_window" not in hints(analyze(series, step))


def test_peaks_within_three_hours_of_each_other_have_the_time_named_and_four_hours_are_too_many():
    series, step = week(spike=False)
    series[(series.index.dayofweek == 0) & (series.index.hour == 8)] = 120.0
    series[(series.index.dayofweek == 1) & (series.index.hour == 10)] = 121.0
    series[(series.index.dayofweek == 2) & (series.index.hour == 11)] = 122.0       # three hours

    assert hints(analyze(series, step))["peak_window"].params == {"start": "08:00", "end": "11:00"}

    series[(series.index.dayofweek == 2) & (series.index.hour == 11)] = 100.0
    series[(series.index.dayofweek == 2) & (series.index.hour == 12)] = 122.0       # four hours

    assert "peak_window" not in hints(analyze(series, step))


@pytest.mark.parametrize("code, params", [
    ("peak_rare", {"limit": 135, "hours": 1.5, "days": 2}), ("base_high", {"share": 60}), ("base_low", {"share": 10}),
    ("weekend_low", {"share": 40}), ("weekend_similar", {"share": 95}), ("peak_window", {"start": "08:00", "end": "10:00"}),
])
def test_every_hint_has_a_text_in_both_languages_and_it_survives_being_pickled(code, params):
    hint = AnalysisHint(code, **params)

    for tr in (EN, DE):
        sentence = analysis_text(hint, tr)
        assert sentence and "{" not in sentence and "analysis.hint" not in sentence
    assert pickle.loads(pickle.dumps(hint)) == hint and pickle.loads(pickle.dumps(hint)).params == hint.params


# ---------------------------------------------------------------------------
# the profile as it is read, speed
# ---------------------------------------------------------------------------

def test_a_profile_that_is_used_as_written_in_utc_is_analysed_by_the_times_as_they_are_written():
    series, step = week(tz="UTC")

    analysis = analyze(series, step)

    assert analysis.kpis.peak_time == pd.Timestamp("2023-02-08 10:00", tz="UTC") and typical(analysis).mean[10] == 110.0


def test_the_energy_of_the_analysis_is_that_of_the_profile_that_was_read():
    from backend.load_profile import read_load_profile
    from tests.test_load_profile import kw, render, starts

    index = starts("2024-02-05 00:00", "2024-02-11 23:45")
    values = kw(index)
    profile = read_load_profile(render(index, values).encode(), "Lastgang.csv")

    analysis = analyze(profile.power_kw, profile.step_minutes)

    assert analysis.kpis.energy_kwh == pytest.approx(profile.energy_kwh()) and analysis.kpis.peak_kw == pytest.approx(profile.peak_kw())
    assert analysis.step_minutes == 15 and len(analysis.heatmap.dates) == 7


def test_a_year_of_quarter_hours_is_analysed_in_a_few_seconds():
    index = pd.date_range("2023-01-01", "2024-01-01", freq="15min", tz=ZONE, inclusive="left")
    rng = np.random.default_rng(7)
    series = pd.Series(30 + 20 * np.clip(np.sin((index.hour - 6) / 24 * 2 * np.pi), 0, None) + rng.normal(0, 2, len(index)), index=index)

    started = time.time()
    analysis = analyze(series, 15)

    assert time.time() - started < 20 and analysis.kpis.yearly and analysis.heatmap.values.shape == (365, 96)
    assert len(analysis.typical_days) >= 9 and len(analysis.months) == 12