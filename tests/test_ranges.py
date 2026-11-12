"""The window of time that a chart shows: which windows a period has, and what is in each."""

import datetime

import pytest

from backend.results import FlowTable
from frontend_nicegui.ranges import (
    LONG_HOURS,
    MODES,
    WINDOW_HOURS,
    available_modes,
    is_long,
    steps_in,
    view_frame,
    window_count,
)

START = datetime.datetime(2021, 1, 1)


def flows(hours, step_hours=1.0, columns=("a-->b",)):
    n = round(hours / step_hours)
    return FlowTable(start=START, step_hours=step_hours, columns=list(columns),
                     values=[[float(i) for i in range(n)] for _ in columns])


def test_the_modes_and_their_lengths():
    assert MODES == ("day", "week", "month", "all")
    assert WINDOW_HOURS == {"day": 24, "week": 168, "month": 720}


@pytest.mark.parametrize("step_hours, day, week, month", [(1.0, 24, 168, 720), (0.25, 96, 672, 2880), (2.0, 12, 84, 360)])
def test_how_many_steps_a_window_holds_depends_on_the_length_of_a_step(step_hours, day, week, month):
    table = flows(24, step_hours)

    assert (steps_in(table, "day"), steps_in(table, "week"), steps_in(table, "month")) == (day, week, month)


def test_a_step_longer_than_a_window_still_holds_one_step():
    assert steps_in(flows(48, 48.0), "day") == 1


@pytest.mark.parametrize("hours, expected", [
    (24, {"day": 1, "week": 1, "month": 1, "all": 1}),
    (25, {"day": 2, "week": 1, "month": 1, "all": 1}),
    (168, {"day": 7, "week": 1, "month": 1, "all": 1}),
    (169, {"day": 8, "week": 2, "month": 1, "all": 1}),
    (8760, {"day": 365, "week": 53, "month": 13, "all": 1}),
])
def test_how_many_windows_a_period_has(hours, expected):
    table = flows(hours)

    assert {mode: window_count(table, mode) for mode in MODES} == expected


@pytest.mark.parametrize("hours, expected", [
    (24, []),                                        # a day: there is nothing to choose
    (12, []),
    (48, ["day", "all"]),
    (168, ["day", "all"]),
    (200, ["day", "week", "all"]),
    (LONG_HOURS + 1, ["day", "week", "all"]),
    (8760, ["day", "week", "month", "all"]),
])
def test_the_modes_that_make_sense_for_a_period(hours, expected):
    assert available_modes(flows(hours)) == expected


def test_a_window_is_a_slice_of_the_period_and_the_windows_follow_each_other():
    table = flows(8760)

    first, count = view_frame(table, "week", 0)
    second, _ = view_frame(table, "week", 1)

    assert count == 53 and len(first) == 168 and len(second) == 168
    assert first.index[0] == START and second.index[0] == START + datetime.timedelta(hours=168)
    assert list(first["a-->b"].iloc[:3]) == [0.0, 1.0, 2.0] and second["a-->b"].iloc[0] == 168.0


def test_the_last_window_is_shorter_when_the_period_does_not_divide():
    table = flows(8760)

    last, count = view_frame(table, "month", 12)

    assert count == 13 and len(last) == 120                      # 8760 - 12 x 720
    assert last.index[-1] == START + datetime.timedelta(hours=8759)


@pytest.mark.parametrize("position, expected_first", [(-5, 0), (0, 0), (52, 52 * 168), (53, 52 * 168), (9999, 52 * 168)])
def test_a_position_outside_the_windows_is_held_at_the_first_or_the_last(position, expected_first):
    frame, _ = view_frame(flows(8760), "week", position)

    assert frame["a-->b"].iloc[0] == float(expected_first)


def test_a_window_of_quarter_hours_holds_a_day_of_96_steps():
    frame, count = view_frame(flows(72, 0.25), "day", 1)

    assert len(frame) == 96 and count == 3 and frame.index[0] == START + datetime.timedelta(days=1)


def test_the_whole_period_has_every_step():
    table = flows(8760)

    frame, count = view_frame(table, "all")

    assert count == 1 and len(frame) == 8760
    assert frame["a-->b"].iloc[5] == 5.0 and frame.index[1] == START + datetime.timedelta(hours=1)


def test_a_period_is_long_when_it_is_more_than_two_weeks():
    assert not is_long(flows(LONG_HOURS)) and is_long(flows(LONG_HOURS + 1))
    assert is_long(flows(LONG_HOURS + 1, 0.25)) and not is_long(flows(LONG_HOURS, 0.25))


def test_an_end_row_that_oemof_adds_is_not_in_a_window():
    frame, _ = view_frame(flows(48), "day", 1)

    assert len(frame) == 24 and frame.index[-1] == START + datetime.timedelta(hours=47)