"""Reading and checking a load profile: the formats of the files, the unit, the time (start or end of a step, the clock
change), and what is wrong with the data."""

import datetime
import io
import pickle
import time

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

from backend.i18n import Translator
from backend.load_profile import (
    Count,
    DurationText,
    LoadProfile,
    ProfileFileError,
    ProfileNotice,
    ProfileOptions,
    UnitText,
    profile_text,
    read_load_profile,
)
from backend.timeseries_import import ImportOptions, TimeSeriesFileError

DE = Translator("de")
EN = Translator("en")
ZONE = "Europe/Berlin"


# ---------------------------------------------------------------------------
# files to read
# ---------------------------------------------------------------------------

def starts(first, last, freq="15min", tz=ZONE):
    """The start of each time step, in local time (tz=None: as written, no clock change)."""

    return pd.date_range(first, last, freq=freq, tz=tz)


def kw(index, seed=1):
    """A load that looks like a site: a base load, a day shape, less at the weekend, some noise."""

    hour = np.asarray(index.hour + index.minute / 60)
    weekday = np.asarray(index.dayofweek) < 5
    noise = np.random.default_rng(seed).normal(0, 0.4, len(index))

    return np.round(20 + 15 * np.clip(np.sin((hour - 6) / 24 * 2 * np.pi), 0, None) + weekday * 8 + noise, 3)


def number(value, decimal=","):
    return str(value).replace(".", decimal)


def render(index, values, conv="start", header="Zeitstempel;Leistung kW", date_format="%d.%m.%Y %H:%M", sep=";", decimal=",",
           step="15min", above=(), unit_line=None, divide=1):
    """The text of a file with one column for the time and one for the value. conv='end' writes the end of each step."""

    shift = pd.Timedelta(step) if conv == "end" else pd.Timedelta(0)
    lines = list(above) + [header] + ([unit_line] if unit_line else [])
    for stamp, value in zip(index + shift, values):
        lines.append(f"{stamp.strftime(date_format)}{sep}{number(round(value / divide, 8), decimal)}")

    return "\n".join(lines) + "\n"


def read(text, filename="Werkhalle.csv", options=None, encoding="utf-8"):
    return read_load_profile(text.encode(encoding), filename, options)


def codes(profile):
    return [notice.code for notice in profile.notices]


def find(profile, code):
    return next(notice for notice in profile.notices if notice.code == code)


def excel_file(rows, header=None):
    book = Workbook()
    sheet = book.active
    if header:
        sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)

    return buffer.getvalue()


def same_series(profile, index, values):
    """The profile has this index and these values (kW)."""

    assert len(profile.power_kw) == len(index)
    assert (profile.power_kw.index == index).all()
    np.testing.assert_allclose(profile.power_kw.to_numpy(), values, atol=1e-3)


# ---------------------------------------------------------------------------
# the formats of the files
# ---------------------------------------------------------------------------

def test_a_german_file_with_semicolons_and_decimal_commas_is_read():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)

    profile = read(render(index, values))

    assert profile.ready and profile.needs == [] and (profile.value_column, profile.unit) == ("Leistung kW", "kW")
    assert profile.step_minutes == 15 and profile.rows == 192 and profile.file_name == "Werkhalle.csv"
    same_series(profile, index, values)


def test_a_file_with_iso_times_commas_and_decimal_points_is_read():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)

    profile = read(render(index, values, header="time,power [kW]", date_format="%Y-%m-%d %H:%M:%S", sep=",", decimal="."))

    assert profile.ready and profile.unit == "kW"
    same_series(profile, index, values)


def test_iso_times_with_the_offset_of_summer_and_winter_time_are_read_on_one_line_of_time():
    index = starts("2024-03-30 00:00", "2024-04-01 23:45")
    values = kw(index)
    lines = ["time;kW"] + [f"{stamp.isoformat()};{number(value)}" for stamp, value in zip(index, values)]

    profile = read("\n".join(lines) + "\n")

    assert profile.ready and profile.time_basis == "local"
    assert "gaps" not in codes(profile)
    same_series(profile, index, values)


def test_the_date_and_the_time_of_the_day_can_be_in_two_columns():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)
    lines = ["Datum;Uhrzeit;Leistung kW"] + [
        f"{stamp.strftime('%d.%m.%Y;%H:%M')};{number(value)}" for stamp, value in zip(index, values)]

    profile = read("\n".join(lines) + "\n")

    assert profile.ready and profile.stamp_at == "start"
    same_series(profile, index, values)


def test_a_time_of_24_00_in_its_own_column_is_the_end_of_the_day_and_the_times_are_the_end_of_each_step():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)
    lines = ["Datum;Uhrzeit;Leistung kW"]
    for stamp, value in zip(index + pd.Timedelta("15min"), values):
        day = stamp.normalize() - pd.Timedelta(days=1) if stamp.hour == 0 and stamp.minute == 0 else stamp.normalize()
        clock = "24:00" if stamp.hour == 0 and stamp.minute == 0 else stamp.strftime("%H:%M")
        lines.append(f"{day.strftime('%d.%m.%Y')};{clock};{number(value)}")

    profile = read("\n".join(lines) + "\n")

    assert profile.stamp_at == "end" and "stamp_assumed" not in codes(profile)
    same_series(profile, index, values)


def test_a_time_of_24_00_in_one_column_is_the_start_of_the_next_day():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)
    lines = ["Zeitstempel;Arbeit kWh"]
    for stamp, value in zip(index + pd.Timedelta("15min"), values):
        text = stamp.strftime("%d.%m.%Y %H:%M")
        if stamp.hour == 0 and stamp.minute == 0:
            text = (stamp - pd.Timedelta(days=1)).strftime("%d.%m.%Y") + " 24:00"
        lines.append(f"{text};{number(round(value / 4, 4))}")

    profile = read("\n".join(lines) + "\n")

    assert profile.stamp_at == "end" and profile.unit == "kWh"
    same_series(profile, index, values)


def test_an_excel_file_with_dates_and_numbers_is_read():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45", tz=None)
    values = kw(index)
    content = excel_file([[stamp.to_pydatetime(), float(value)] for stamp, value in zip(index, values)],
                         header=["Zeit", "Wirkleistung kW"])

    profile = read_load_profile(content, "lastgang.xlsx")

    assert profile.ready and profile.unit == "kW" and profile.step_minutes == 15
    assert profile.time_zone == ZONE                      # the period has no clock change: local time
    np.testing.assert_allclose(profile.power_kw.to_numpy(), values, atol=1e-6)
    assert (profile.power_kw.index.tz_localize(None) == index).all()


def test_an_excel_file_with_the_date_and_the_time_in_two_columns_is_read():
    index = starts("2024-02-05 00:00", "2024-02-05 23:45", tz=None)
    values = kw(index)
    rows = [[stamp.to_pydatetime().replace(hour=0, minute=0), datetime.time(stamp.hour, stamp.minute), float(value)]
            for stamp, value in zip(index, values)]

    profile = read_load_profile(excel_file(rows, header=["Datum", "Uhrzeit", "Leistung kW"]), "lastgang.xlsx")

    assert profile.ready and profile.step_minutes == 15
    np.testing.assert_allclose(profile.power_kw.to_numpy(), values, atol=1e-6)


def test_a_windows_file_with_umlauts_and_a_utf8_file_with_a_mark_are_read():
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")
    values = kw(index)
    text = render(index, values, header="Zeitstempel;Wirkleistung in kW (Verbrauch)")

    for encoding in ("cp1252", "utf-8-sig"):
        profile = read(text.replace("Verbrauch", "Verbrauch äöü"), encoding=encoding)
        assert profile.ready and profile.unit == "kW"
        same_series(profile, index, values)


def test_lines_with_the_meter_and_the_period_above_the_table_are_skipped_and_the_unit_line_gives_the_unit():
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")
    values = kw(index)
    text = render(index, values, header="Zeitstempel;Leistung", unit_line="dd.mm.yyyy hh:mm;kWh", divide=4,
                  above=("Zaehlpunkt;DE0001234", "Export;2024", ""))

    profile = read(text)

    assert profile.ready and (profile.value_column, profile.unit) == ("Leistung", "kWh")
    same_series(profile, index, values)


@pytest.mark.parametrize("name, unit", [
    ("Last [kW]", "kW"), ("Arbeit (kWh)", "kWh"), ("Wirkleistung kW", "kW"), ("Verbrauch_kWh", "kWh"), ("Energie in MWh", "MWh"),
    ("Leistung MW", "MW"), ("Wert [W]", "W"), ("Wert (Wh)", "Wh"), ("LAST KW", "kW"),
])
def test_the_unit_is_taken_from_the_name_of_the_column(name, unit):
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")

    assert read(render(index, kw(index), header=f"Zeit;{name}")).unit == unit


@pytest.mark.parametrize("name", ["Last kWp", "Mwst netto", "Whirlpool"])
def test_a_name_that_only_looks_like_a_unit_is_not_one(name):
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")

    assert read(render(index, kw(index), header=f"Zeit;{name}")).unit is None


@pytest.mark.parametrize("name", ["Wert", "Last", "Verbrauch", "Last kW kWh"])
def test_a_name_without_a_unit_or_with_two_gives_none(name):
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")

    profile = read(render(index, kw(index), header=f"Zeit;{name}"))

    assert profile.unit is None and profile.needs == ["unit"] and not profile.ready


# ---------------------------------------------------------------------------
# the unit and the power
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("unit, divide", [
    ("kW", 1), ("W", 0.001), ("MW", 1000), ("kWh", 4), ("Wh", 0.004), ("MWh", 4000),
])
def test_every_unit_gives_the_same_power_in_kw(unit, divide):
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)

    profile = read(render(index, values, header=f"Zeit;Wert [{unit}]", divide=divide))

    assert profile.unit == unit
    np.testing.assert_allclose(profile.power_kw.to_numpy(), values, rtol=1e-3, atol=1e-3)


def test_energy_in_an_hourly_file_is_the_power_of_that_hour():
    index = starts("2024-02-05 00:00", "2024-02-07 23:00", freq="60min")
    values = kw(index)

    profile = read(render(index, values, header="Zeit;Arbeit kWh", step="60min"))

    assert profile.step_minutes == 60
    np.testing.assert_allclose(profile.power_kw.to_numpy(), values, atol=1e-3)


def test_the_energy_of_the_profile_is_the_sum_of_the_steps_and_the_peak_is_the_highest_step():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)

    profile = read(render(index, values))

    assert profile.energy_kwh() == pytest.approx(values.sum() / 4, rel=1e-6)
    assert profile.peak_kw() == pytest.approx(values.max())
    assert profile.missing_share() == 0.0


def test_a_file_that_does_not_say_its_unit_is_not_ready_and_shows_the_energy_under_both_readings():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)

    profile = read(render(index, values, header="Zeit;Wert"))

    assert not profile.ready and profile.power_kw is None and profile.needs == ["unit"]
    assert profile.preview["as_power_kwh"] == pytest.approx(values.sum() / 4, rel=1e-3)
    assert profile.preview["as_energy_kwh"] == pytest.approx(values.sum(), rel=1e-3)
    assert profile.step_minutes == 15 and "file_info" in codes(profile)            # what is known is there anyway


def test_the_caller_names_the_unit_and_the_file_is_read_again_as_that():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)
    text = render(index, values, header="Zeit;Wert", divide=4)

    profile = read(text, options=ProfileOptions(unit="kWh"))

    assert profile.ready and profile.unit == "kWh"
    same_series(profile, index, values)


def test_a_unit_that_the_caller_names_wins_over_the_name_of_the_column():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)

    profile = read(render(index, values, header="Zeit;Last kW", divide=4), options=ProfileOptions(unit="kWh"))

    assert profile.unit == "kWh"
    same_series(profile, index, values)


def test_a_unit_that_does_not_exist_is_refused():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")

    with pytest.raises(ProfileFileError) as error:
        read(render(index, kw(index)), options=ProfileOptions(unit="PS"))

    assert error.value.code == "unit_invalid" and "PS" in str(error.value)


# ---------------------------------------------------------------------------
# which column is the load
# ---------------------------------------------------------------------------

def two_columns(first, second):
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")
    values = kw(index)
    lines = [f"Zeit;{first};{second}"] + [
        f"{stamp.strftime('%d.%m.%Y %H:%M')};{number(value)};{number(round(value / 3, 3))}" for stamp, value in zip(index, values)]

    return "\n".join(lines) + "\n", index, values


def test_the_active_power_is_the_load_and_the_reactive_power_is_named_as_not_used():
    text, index, values = two_columns("Wirkleistung kW", "Blindleistung kvar")

    profile = read(text)

    assert profile.ready and profile.value_column == "Wirkleistung kW"
    assert find(profile, "other_columns").params["columns"] == ["Blindleistung kvar"]
    assert [c.name for c in profile.candidates] == ["Wirkleistung kW", "Blindleistung kvar"]
    same_series(profile, index, values)


def test_a_status_column_is_not_taken_for_the_load():
    text, _, _ = two_columns("Status", "Last kW")

    assert read(text).value_column == "Last kW"


def test_two_columns_that_could_be_the_load_are_not_guessed_and_the_caller_chooses():
    text, index, values = two_columns("Last Halle 1 kW", "Last Halle 2 kW")

    profile = read(text)
    assert not profile.ready and profile.needs == ["value_column"] and profile.unit == "kW"
    assert [c.name for c in profile.candidates] == ["Last Halle 1 kW", "Last Halle 2 kW"]
    assert [c.unit for c in profile.candidates] == ["kW", "kW"]

    chosen = read(text, options=ProfileOptions(value_column="Last Halle 2 kW"))
    assert chosen.ready and chosen.value_column == "Last Halle 2 kW"
    np.testing.assert_allclose(chosen.power_kw.to_numpy(), np.round(values / 3, 3), atol=1e-3)


def test_one_column_of_numbers_is_the_load_whatever_it_is_called():
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")

    profile = read(render(index, kw(index), header="Zeit;Wert [kW]"))

    assert profile.value_column == "Wert [kW]" and "other_columns" not in codes(profile)


def test_a_column_that_does_not_exist_is_refused():
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")

    with pytest.raises(ProfileFileError) as error:
        read(render(index, kw(index)), options=ProfileOptions(value_column="Nope"))

    assert error.value.code == "column_missing" and "Nope" in str(error.value)


def test_a_file_without_a_column_of_numbers_or_of_times_is_refused():
    with pytest.raises(ProfileFileError) as no_numbers:
        read("Zeit;Name\n01.01.2024 00:00;a\n01.01.2024 00:15;b\n01.01.2024 00:30;c\n")
    with pytest.raises(ProfileFileError) as no_time:
        read("Name;kW\na;1\nb;2\nc;3\nd;4\n")

    assert no_numbers.value.code == "no_numbers" and no_time.value.code == "no_time"


# ---------------------------------------------------------------------------
# the time step
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("step", ["1min", "5min", "10min", "15min", "30min", "60min"])
def test_every_usual_time_step_is_found(step):
    index = starts("2024-02-05 00:00", "2024-02-05 23:59", freq=step)
    values = kw(index)

    profile = read(render(index, values, step=step))

    assert profile.step_minutes == int(step[:-3]) and profile.ready
    same_series(profile, index, values)


def test_a_time_step_of_a_day_is_too_coarse_and_one_of_seven_minutes_is_not_supported():
    daily = starts("2024-01-01", "2024-01-10", freq="D")
    odd = starts("2024-02-05 00:00", "2024-02-05 23:59", freq="7min")

    with pytest.raises(ProfileFileError) as coarse:
        read(render(daily, np.arange(len(daily)) + 1.0, step="1D"))
    with pytest.raises(ProfileFileError) as unsupported:
        read(render(odd, kw(odd), step="7min"))

    assert coarse.value.code == "step_too_coarse" and unsupported.value.code == "step_unsupported"


def test_times_that_do_not_follow_a_regular_step_are_refused():
    rng = np.random.default_rng(2)
    stamps = pd.Timestamp("2024-02-05") + pd.to_timedelta(np.sort(rng.choice(24 * 60, 120, replace=False)), unit="min")
    text = "Zeit;kW\n" + "\n".join(f"{s.strftime('%d.%m.%Y %H:%M')};{i + 1}" for i, s in enumerate(stamps))

    with pytest.raises(ProfileFileError) as error:
        read(text)

    assert error.value.code in ("step_irregular", "step_unsupported")


def test_a_few_times_off_the_regular_step_are_left_out_and_told():
    index = starts("2024-02-05 00:00", "2024-02-08 23:45")
    values = kw(index)
    lines = render(index, values).splitlines()
    lines.insert(50, "05.02.2024 12:07;55")

    profile = read("\n".join(lines) + "\n")

    assert find(profile, "off_grid").params["n"] == 1
    same_series(profile, index, values)


def test_a_file_with_too_few_times_is_refused():
    with pytest.raises(ProfileFileError) as error:
        read("Zeit;kW\n01.01.2024 00:00;1\n01.01.2024 00:15;2\n")

    assert error.value.code == "too_few_rows"


def test_a_file_that_cannot_be_read_at_all_is_refused_by_the_reader_of_files():
    with pytest.raises(TimeSeriesFileError):
        read_load_profile(b"", "x.csv")
    with pytest.raises(TimeSeriesFileError):
        read_load_profile(b"abc", "x.pdf")


# ---------------------------------------------------------------------------
# the start or the end of a step
# ---------------------------------------------------------------------------

def test_a_profile_of_whole_days_shows_by_its_first_and_last_time_what_the_times_mean():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)

    at_start = read(render(index, values))
    at_end = read(render(index, values, conv="end"))

    assert (at_start.stamp_at, at_end.stamp_at) == ("start", "end")
    assert "stamp_assumed" not in codes(at_start) and "stamp_assumed" not in codes(at_end)
    assert {"stamp_start"} <= set(codes(at_start)) and {"stamp_end"} <= set(codes(at_end))
    same_series(at_end, index, values)


def test_an_hourly_file_with_the_end_of_each_hour_is_found_too():
    index = starts("2024-02-05 00:00", "2024-02-07 23:00", freq="60min")
    values = kw(index)

    profile = read(render(index, values, conv="end", step="60min"))

    assert profile.stamp_at == "end"
    same_series(profile, index, values)


def test_a_profile_that_does_not_show_it_is_read_as_the_start_with_a_warning_and_the_caller_can_say_the_end():
    index = starts("2024-02-05 08:00", "2024-02-06 16:45")
    values = kw(index)

    guessed = read(render(index, values))
    told = read(render(index, values), options=ProfileOptions(stamp_at="end"))

    assert guessed.stamp_at == "start" and find(guessed, "stamp_assumed").level == "warning"
    assert told.stamp_at == "end" and "stamp_assumed" not in codes(told)
    assert (told.power_kw.index == index - pd.Timedelta("15min")).all()


def test_the_caller_can_say_start_for_a_profile_that_looks_like_the_end():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")

    profile = read(render(index, kw(index), conv="end"), options=ProfileOptions(stamp_at="start"))

    assert profile.stamp_at == "start" and profile.power_kw.index[0] == index[0] + pd.Timedelta("15min")


def test_a_value_that_is_not_start_or_end_is_refused():
    with pytest.raises(ValueError):
        ProfileOptions(stamp_at="middle")


# ---------------------------------------------------------------------------
# the clock change
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("conv", ["start", "end"])
def test_a_year_in_local_time_with_summer_time_comes_out_on_a_regular_line_with_the_right_hours(conv):
    index = starts("2024-01-01 00:00", "2024-12-31 23:45")
    values = kw(index)

    profile = read(render(index, values, conv=conv))

    assert profile.time_basis == "local" and profile.time_zone == ZONE and "time_local" in codes(profile)
    assert profile.rows == 35136 and not profile.power_kw.isna().any()
    assert not {"gaps", "unsorted", "duplicates_same", "duplicates_conflict"} & set(codes(profile))
    same_series(profile, index, values)
    assert profile.energy_kwh() == pytest.approx(values.sum() / 4, rel=1e-6)


def test_the_hours_of_the_clock_change_are_23_and_25_and_the_values_stay_with_their_hours():
    index = starts("2024-01-01 00:00", "2024-12-31 23:45", freq="60min")
    values = kw(index)
    profile = read(render(index, values, step="60min", header="Zeit;Last kW"))

    day = profile.power_kw
    spring, autumn = day["2024-03-31"], day["2024-10-27"]
    assert (len(spring), len(autumn)) == (23, 25)
    np.testing.assert_allclose(autumn.to_numpy(), values[(index >= "2024-10-27") & (index < "2024-10-28")], atol=1e-3)
    assert list(autumn.index.hour).count(2) == 2                           # the hour from 02:00 to 03:00 is there twice


def test_an_hourly_year_has_8784_values_with_no_gaps_and_a_leap_day():
    index = starts("2024-01-01 00:00", "2024-12-31 23:00", freq="60min")
    values = kw(index)

    profile = read(render(index, values, step="60min", header="Zeit;Last kW"))

    assert len(profile.power_kw) == 8784 and not profile.power_kw.isna().any()
    assert profile.power_kw["2024-02-29"].notna().all()


def test_a_year_that_has_24_hours_on_every_day_is_used_as_written():
    index = starts("2024-01-01 00:00", "2024-12-31 23:45", tz=None)
    values = kw(index)

    profile = read(render(index, values))

    assert profile.time_basis == "as_written" and profile.time_zone == "UTC" and "time_as_written" in codes(profile)
    assert not {"gaps", "unsorted"} & set(codes(profile))
    same_series(profile, index.tz_localize("UTC"), values)
    assert profile.power_kw["2024-03-31"].shape[0] == 96 and profile.power_kw["2024-10-27"].shape[0] == 96


def test_a_file_with_a_short_day_in_spring_and_a_normal_day_in_autumn_does_not_agree_with_itself():
    spring = starts("2024-03-30 00:00", "2024-04-01 23:45")                    # with summer time: 23 hours on the 31st
    autumn = starts("2024-10-26 00:00", "2024-10-28 23:45", tz=None)           # 24 hours on the 27th
    lines = [render(spring, kw(spring)).strip()]
    lines += [line for line in render(autumn, kw(autumn)).splitlines()[1:]]

    profile = read("\n".join(lines) + "\n")

    assert profile.time_basis == "as_written" and find(profile, "time_inconsistent").level == "warning"


def test_a_period_without_a_clock_change_says_nothing_about_it():
    index = starts("2024-01-15 00:00", "2024-02-15 23:45")

    profile = read(render(index, kw(index)))

    assert profile.time_basis == "local" and not {"time_local", "time_as_written", "time_inconsistent"} & set(codes(profile))
    same_series(profile, index, kw(index))


def test_a_summer_period_is_read_in_summer_time():
    index = starts("2024-07-01 00:00", "2024-07-07 23:45")
    values = kw(index)

    profile = read(render(index, values))

    assert profile.power_kw.index[0].utcoffset() == datetime.timedelta(hours=2)
    same_series(profile, index, values)


# ---------------------------------------------------------------------------
# what is wrong with the data
# ---------------------------------------------------------------------------

def test_rows_that_are_missing_make_gaps_and_the_gaps_are_counted_and_measured():
    index = starts("2024-02-05 00:00", "2024-02-11 23:45")
    values = kw(index)
    gone = np.zeros(len(index), dtype=bool)
    gone[10:13] = True                                # 3 steps
    gone[200:240] = True                              # 40 steps: 10 hours
    text = render(index[~gone], values[~gone])

    profile = read(text)

    notice = find(profile, "gaps")
    assert notice.params["n"] == 2 and notice.params["missing"] == Count(43) and notice.params["longest"] == DurationText(600)
    assert notice.params["share"].value == pytest.approx(100 * 43 / len(index), abs=0.05)
    assert len(profile.power_kw) == len(index) and profile.power_kw.isna().sum() == 43
    assert profile.missing_share() == pytest.approx(43 / len(index))
    np.testing.assert_allclose(profile.power_kw[~gone].to_numpy(), values[~gone], atol=1e-3)


def test_empty_cells_are_gaps_too_and_the_reader_of_files_says_where_the_first_is():
    index = starts("2024-02-05 00:00", "2024-02-07 23:45")
    values = kw(index)
    lines = render(index, values).splitlines()
    lines[11] = lines[11].split(";")[0] + ";"

    profile = read("\n".join(lines) + "\n")

    assert find(profile, "gaps").params["missing"] == Count(1) and profile.power_kw.isna().sum() == 1
    assert "empty_values" in codes(profile)


def test_a_time_that_appears_twice_with_the_same_value_is_used_once_and_with_different_values_the_first_counts():
    index = starts("2024-02-05 00:00", "2024-02-07 23:45")
    values = kw(index)
    lines = render(index, values).splitlines()
    same = lines[21]
    different = lines[41].split(";")[0] + ";999,9"
    lines = lines[:22] + [same] + lines[22:42] + [different] + lines[42:]

    profile = read("\n".join(lines) + "\n")

    assert find(profile, "duplicates_same").params["n"] == 1 and find(profile, "duplicates_conflict").params["n"] == 1
    same_series(profile, index, values)                          # the first value of each time was kept


def test_rows_that_are_not_in_time_order_are_sorted_and_it_is_said_but_the_clock_change_does_not_say_it():
    index = starts("2024-02-05 00:00", "2024-02-07 23:45")
    values = kw(index)
    lines = render(index, values).splitlines()
    head, body = lines[0], lines[1:]
    body = body[48:] + body[:48]

    profile = read("\n".join([head] + body) + "\n")

    assert "unsorted" in codes(profile)
    same_series(profile, index, values)

    year = read(render(starts("2024-01-01 00:00", "2024-12-31 23:45"), kw(starts("2024-01-01 00:00", "2024-12-31 23:45"))))
    assert "unsorted" not in codes(year)


def test_negative_values_are_counted_with_the_lowest():
    index = starts("2024-02-05 00:00", "2024-02-07 23:45")
    values = kw(index)
    values[[5, 6, 90]] = [-2.5, -7.25, -1.0]

    profile = read(render(index, values))

    notice = find(profile, "negative")
    assert notice.params["n"] == 3 and notice.params["min"].value == pytest.approx(-7.25)


def test_zero_is_not_negative_a_plant_that_stands_uses_nothing():
    index = starts("2024-02-05 00:00", "2024-02-07 23:45")
    values = kw(index)
    values[100:140] = 0.0

    assert "negative" not in codes(read(render(index, values)))


def test_a_value_far_above_the_others_is_found_when_there_are_enough_values():
    index = starts("2024-02-05 00:00", "2024-02-11 23:45")
    values = kw(index)
    values[300] = 5000.0

    profile = read(render(index, values))

    notice = find(profile, "spikes")
    assert notice.params["n"] == 1 and notice.params["max"].value == 5000.0 and notice.params["limit"].value < 200
    assert profile.peak_kw() == 5000.0                                   # it is not removed, only told


def test_a_short_file_is_not_searched_for_far_too_high_values():
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")
    values = kw(index)
    values[30] = 5000.0

    assert "spikes" not in codes(read(render(index, values)))


def test_a_value_that_does_not_change_for_a_day_is_found_and_zero_is_not():
    index = starts("2024-02-05 00:00", "2024-02-12 23:45")
    values = kw(index)
    values[100:100 + 4 * 30] = 42.0                                      # 30 hours
    values[400:400 + 4 * 30] = 0.0                                       # 30 hours of zero: a plant that stands, no meter fault
    values[500:500 + 4 * 10] = 17.0                                      # 10 hours: not long enough

    profile = read(render(index, values))

    notice = find(profile, "flat_run")
    assert notice.params["n"] == 1 and notice.params["hours"].value == 30.0


def test_a_clean_profile_has_no_warnings_except_what_the_period_says():
    index = starts("2024-01-01 00:00", "2024-12-31 23:45")

    profile = read(render(index, kw(index)))

    assert [n.code for n in profile.notices if n.level == "warning"] == []


# ---------------------------------------------------------------------------
# the period and the resolution
# ---------------------------------------------------------------------------

def test_a_short_period_says_it_is_less_than_a_year_and_a_long_one_says_so_and_a_year_says_nothing():
    short = starts("2024-02-05 00:00", "2024-03-05 23:45")
    long = starts("2023-12-01 00:00", "2025-01-10 23:45", tz=None)
    year = starts("2024-01-01 00:00", "2024-12-31 23:45")

    assert find(read(render(short, kw(short))), "short_period").params["days"] == Count(30)
    assert find(read(render(long, kw(long))), "long_period").params["days"] == Count(407)
    assert not {"short_period", "long_period"} & set(codes(read(render(year, kw(year)))))


def test_an_hourly_file_says_that_the_peaks_are_averaged_and_a_quarter_hour_file_does_not():
    hourly = starts("2024-01-01 00:00", "2024-12-31 23:00", freq="60min")
    quarter = starts("2024-02-05 00:00", "2024-02-06 23:45")

    assert "coarse_step" in codes(read(render(hourly, kw(hourly), step="60min")))
    assert "coarse_step" not in codes(read(render(quarter, kw(quarter))))


# ---------------------------------------------------------------------------
# notices and their words
# ---------------------------------------------------------------------------

def test_every_notice_has_a_text_in_both_languages_without_a_gap_in_it():
    index = starts("2024-01-01 00:00", "2024-12-31 23:45")
    values = kw(index)
    values[[5, 6]] = [-1.0, -2.0]
    values[400] = 9000.0
    values[1000:1000 + 4 * 30] = 42.0
    text = render(index, values).splitlines()
    text = text[:3000] + text[3010:]                                                     # a gap
    text.insert(50, text[49])                                                           # a time twice with the same value
    text.insert(80, text[79].split(";")[0] + ";1,5")                                    # ... and with another value
    text.insert(90, "01.01.2024 00:07;5")                                               # off the regular steps
    profile = read("\n".join(text) + "\n", options=None)

    seen = {n.code for n in profile.notices}
    assert {"gaps", "negative", "spikes", "flat_run", "duplicates_same", "duplicates_conflict", "off_grid"} <= seen
    for notice in profile.notices:
        for tr in (EN, DE):
            sentence = profile_text(notice, tr)
            assert "{" not in sentence and "profile." not in sentence and sentence.strip(), (notice.code, sentence)
        assert notice.text == profile_text(notice, EN) or notice.code.endswith("_info")


def test_a_german_and_an_english_sentence_use_the_separators_and_the_dates_of_the_language():
    index = starts("2024-01-01 00:00", "2024-12-31 23:45")
    profile = read(render(index, kw(index)))

    german, english = profile_text(profile.notices[0], DE), profile_text(profile.notices[0], EN)

    assert german == "35.136 Zeitpunkte von 01.01.2024 00:00 bis 31.12.2024 23:45, Zeitschritt 15 Minuten."
    assert english == "35,136 times from 2024-01-01 00:00 to 2024-12-31 23:45, time step 15 minutes."


@pytest.mark.parametrize("code, params", [
    ("no_time", {}), ("no_numbers", {}), ("too_few_rows", {"rows": 2}), ("step_too_coarse", {"step": 1440}),
    ("step_unsupported", {"step": 7}), ("step_irregular", {"step": 15}), ("column_missing", {"column": "X"}),
    ("unit_invalid", {"unit": "PS"}),
])
def test_every_error_has_a_text_in_both_languages(code, params):
    error = ProfileFileError(code, **params)

    for tr in (EN, DE):
        sentence = profile_text(error, tr)
        assert sentence and "{" not in sentence and "profile.error" not in sentence
    assert str(error) == profile_text(error, EN)


def test_the_words_for_a_time_unit_and_a_length_of_time():
    assert DurationText(45).render(EN) == "45 minutes" and DurationText(90).render(DE) == "1,5 Stunden"
    assert DurationText(3 * 1440).render(EN) == "3 days" and DurationText(1440 * 2).render(DE) == "2 Tage"
    assert UnitText("kW").render(DE) == "kW (Leistung)" and "turned into power" in UnitText("kWh").render(EN)


def test_the_text_of_the_flat_run_names_the_number_of_hours_that_the_check_uses():
    from backend.load_profile import FLAT_RUN_HOURS

    notice = ProfileNotice("warning", "flat_run", n=1, hours=FLAT_RUN_HOURS + 1.0)

    assert f"{FLAT_RUN_HOURS} hours or more" in profile_text(notice, EN) and f"{FLAT_RUN_HOURS} Stunden" in profile_text(notice, DE)


def test_the_messages_of_the_reader_of_files_are_in_the_list_and_those_that_would_mislead_are_not():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")

    profile = read(render(index, kw(index)))

    assert "decimal_sign" in codes(profile)                                      # the reader says it, in its own words
    assert not {"time_info", "time_step_not_hourly", "duplicates", "gaps_import"} & set(codes(profile))
    assert any("Komma" in profile_text(n, DE) for n in profile.notices)


def test_notices_and_errors_survive_being_pickled():
    notice = ProfileNotice("warning", "gaps", n=2, missing=Count(5), share=None, longest=DurationText(30))
    error = ProfileFileError("column_missing", column="X")

    assert pickle.loads(pickle.dumps(notice)).params == notice.params and pickle.loads(pickle.dumps(notice)) == notice
    assert pickle.loads(pickle.dumps(error)).code == "column_missing" and str(pickle.loads(pickle.dumps(error))) == str(error)


# ---------------------------------------------------------------------------
# size, speed, and what is not touched
# ---------------------------------------------------------------------------

def test_a_quarter_hour_year_is_read_in_a_few_seconds():
    index = starts("2024-01-01 00:00", "2024-12-31 23:45")
    text = render(index, kw(index), conv="end")

    started = time.time()
    profile = read(text)

    assert time.time() - started < 20 and profile.rows == 35136 and profile.ready


def test_reading_gives_the_same_result_twice_and_leaves_the_options_as_they_were():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    text = render(index, kw(index), header="Zeit;Wert")
    options = ProfileOptions(unit="kWh", file=ImportOptions(decimal=","))

    first, second = read(text, options=options), read(text, options=options)

    assert first.power_kw.equals(second.power_kw) and [n.text for n in first.notices] == [n.text for n in second.notices]
    assert options == ProfileOptions(unit="kWh", file=ImportOptions(decimal=","))


def test_a_profile_that_is_not_ready_has_no_series_and_its_methods_are_not_for_use_yet():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")

    profile = read(render(index, kw(index), header="Zeit;Wert"))

    assert isinstance(profile, LoadProfile) and profile.power_kw is None and not profile.ready


# ---------------------------------------------------------------------------
# a file with all the series of a workshop (the header and the shapes are those of a real file of the project)
# ---------------------------------------------------------------------------

WORKSHOP_COLUMNS = [
    "heat_demand_normalized", "electricity_demand_normalized", "pv_profile_1kwp", "wind_profile_1kw",
    "cop_air_source_heat_pump", "electricity_price_dynamic_ct_kwh",
]


def workshop(hours=8760, year=2021, drop=()):
    """Hourly, a point as the decimal sign, the demands as shares that add up to 1, a PV and a wind profile, a COP and a
    price in ct/kWh. Gives the text and the values of the columns."""

    index = pd.date_range(f"{year}-01-01", periods=hours, freq="h")
    hour = np.asarray(index.hour)
    rng = np.random.default_rng(3)
    electricity = 1 + 0.4 * np.sin((hour - 6) / 24 * 2 * np.pi)
    heat = 1 + 0.9 * np.cos(np.arange(hours) / hours * 2 * np.pi)
    columns = {
        "heat_demand_normalized": heat / heat.sum(),
        "electricity_demand_normalized": electricity / electricity.sum(),
        "pv_profile_1kwp": np.round(0.87 * np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None), 3),
        "wind_profile_1kw": np.round(rng.uniform(0.001, 0.99, hours), 3),
        "cop_air_source_heat_pump": np.round(rng.uniform(2.1, 4.1, hours), 6),
        "electricity_price_dynamic_ct_kwh": np.round(rng.uniform(8, 70, hours), 5),
    }
    names = [name for name in columns if name not in drop]
    lines = ["time," + ",".join(names)]
    for position, stamp in enumerate(index):
        lines.append(stamp.strftime("%Y-%m-%d %H:%M") + "," + ",".join(repr(float(columns[name][position])) for name in names))

    return "\n".join(lines) + "\n", columns


def test_the_electricity_demand_of_a_workshop_file_is_the_load_and_its_shares_ask_for_the_energy():
    text, _ = workshop()

    profile = read(text, "workshop.csv")

    assert not profile.ready and profile.needs == ["energy"] and profile.power_kw is None
    assert profile.value_column == "electricity_demand_normalized" and profile.unit == "share"
    assert [c.name for c in profile.candidates] == WORKSHOP_COLUMNS
    assert profile.step_minutes == 60 and profile.rows == 8760 and "share_found" in codes(profile)


def test_with_the_energy_the_shares_become_power_and_the_energy_and_the_peak_follow_from_it():
    text, columns = workshop()

    profile = read(text, "workshop.csv", options=ProfileOptions(energy_kwh=250000.0))

    shares = columns["electricity_demand_normalized"]
    assert profile.ready and profile.needs == [] and len(profile.power_kw) == 8760
    assert profile.energy_kwh() == pytest.approx(250000.0, rel=1e-6)
    assert profile.peak_kw() == pytest.approx(shares.max() * 250000.0)
    np.testing.assert_allclose(profile.power_kw.to_numpy(), shares * 250000.0, rtol=1e-9)
    assert profile.time_basis == "as_written" and "time_as_written" in codes(profile)          # 2021: 24 hours on both days
    assert profile.power_kw.index[0] == pd.Timestamp("2021-01-01 00:00", tz="UTC")
    assert find(profile, "share_info").params["energy"] == 250000.0
    assert find(profile, "other_columns").params["columns"] == [name for name in WORKSHOP_COLUMNS if name != "electricity_demand_normalized"]


def test_the_shares_of_a_quarter_hour_profile_give_the_power_of_each_quarter_hour():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    shares = np.full(len(index), 1 / len(index))

    profile = read(render(index, shares, header="Zeit;Anteil"), options=ProfileOptions(energy_kwh=1920.0))

    assert profile.step_minutes == 15 and profile.ready
    np.testing.assert_allclose(profile.power_kw.to_numpy(), 1920.0 / len(index) * 4, rtol=1e-5)  # 10 kWh in 15 minutes: 40 kW
    assert profile.energy_kwh() == pytest.approx(1920.0, rel=1e-5)


def test_another_column_of_the_workshop_file_can_be_chosen_and_read_with_its_unit():
    text, columns = workshop()

    profile = read(text, "workshop.csv", options=ProfileOptions(value_column="pv_profile_1kwp", unit="kW"))

    assert profile.ready and profile.unit == "kW" and profile.peak_kw() == pytest.approx(0.87)
    np.testing.assert_allclose(profile.power_kw.to_numpy(), columns["pv_profile_1kwp"])


def test_a_price_in_cents_per_kwh_is_never_taken_for_the_load_or_for_energy():
    text, _ = workshop(drop=("heat_demand_normalized", "electricity_demand_normalized", "wind_profile_1kw", "cop_air_source_heat_pump"))

    profile = read(text, "workshop.csv")

    assert not profile.ready and profile.needs == ["value_column", "unit"] and profile.value_column is None
    assert [(c.name, c.unit) for c in profile.candidates] == [("pv_profile_1kwp", None), ("electricity_price_dynamic_ct_kwh", None)]


def test_a_column_that_looks_like_a_price_a_pv_profile_or_a_cop_is_not_the_load_even_when_it_is_the_only_one_with_numbers():
    for name in ("electricity_price_dynamic_ct_kwh", "pv_profile_1kwp", "cop_air_source_heat_pump", "wind_profile_1kw"):
        index = starts("2024-02-05 00:00", "2024-02-05 23:45")

        profile = read(render(index, kw(index), header=f"time;{name}"))

        assert profile.needs[0] == "value_column" and not profile.ready, name


@pytest.mark.parametrize("name, unit", [
    ("electricity_price_dynamic_ct_kwh", None), ("Preis [ct/kWh]", None), ("Strompreis EUR/MWh", None), ("Preis in € pro kWh", None),
    ("price EUR per MWh", None), ("Netzbezug ct kWh", None), ("Verbrauch kWh", "kWh"), ("Last [kW]", "kW"),
    ("Arbeit kWh/Viertelstunde", "kWh"), ("Leistung in MW", "MW"),
])
def test_a_unit_after_cents_or_euros_or_a_slash_is_a_price_per_unit_and_not_the_unit_of_the_values(name, unit):
    from backend.load_profile import _unit_in

    assert _unit_in(name) == unit


@pytest.mark.parametrize("total, shares", [(1.0, True), (1.015, True), (0.985, True), (1.05, False), (0.9, False), (100.0, False)])
def test_values_that_add_up_to_one_within_two_percent_are_shares(total, shares):
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")
    values = np.full(len(index), total / len(index))

    profile = read(render(index, values, header="Zeit;Wert"))

    assert (profile.unit == "share") == shares and profile.needs == (["energy"] if shares else ["unit"])


def test_values_with_a_negative_one_are_not_shares_and_a_unit_that_is_named_wins():
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")
    values = np.full(len(index), 1 / len(index))
    negative = values.copy()
    negative[3], negative[4] = values[3] + 0.01, -0.005 + values[4] - values[4]

    assert read(render(index, negative, header="Zeit;Wert")).unit is None
    named = read(render(index, values, header="Zeit;Wert"), options=ProfileOptions(unit="kW"))
    assert named.ready and named.unit == "kW" and named.peak_kw() == pytest.approx(1 / len(index))


def test_the_energy_that_the_shares_stand_for_must_be_a_number_above_zero():
    for bad in (0, -5.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            ProfileOptions(energy_kwh=bad)


def test_the_words_about_shares_are_in_both_languages():
    found, info = ProfileNotice("info", "share_found"), ProfileNotice("info", "share_info", energy=120000.0)

    assert "Anteile" in profile_text(found, DE) and "shares" in profile_text(found, EN)
    assert "120000" in profile_text(info, DE) and "shares of 120000 kWh" in profile_text(info, EN)


def test_a_column_that_is_almost_empty_and_has_a_single_one_is_not_a_column_of_shares():
    index = starts("2024-02-05 00:00", "2024-02-05 23:45")
    lines = ["Zeit;Wert;Last kW"] + [
        f"{stamp.strftime('%d.%m.%Y %H:%M')};{'1' if position == 40 else ''};{number(20 + position / 10)}"
        for position, stamp in enumerate(index)]

    profile = read("\n".join(lines) + "\n", options=ProfileOptions(value_column="Wert"))

    assert profile.unit is None and profile.needs == ["unit"]