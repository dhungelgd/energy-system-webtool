"""The window of time that a chart of the flows shows: a day, a week, a month, or the whole period (every value).

A result of a year has 8,760 values for each flow. The chart shows a window that the visitor moves, so that a
day, a week or a month is read easily; the whole period has every value, to be zoomed into with the mouse. No
NiceGUI code in here, so it is easy to test.
"""

import math

MODES = ("day", "week", "month", "all")
MODE_TEXTS = {                                               # the words on the buttons
    "day": "result.range.day",
    "week": "result.range.week",
    "month": "result.range.month",
    "all": "result.range.all",
}
WINDOW_HOURS = {"day": 24, "week": 168, "month": 720}      # a month is 30 days here
LONG_HOURS = 14 * 24                                         # a period longer than this is a long one (two weeks)


def steps_in(flows, mode):
    """How many time steps a window of this mode holds (at least one)."""

    return max(1, round(WINDOW_HOURS[mode] / flows.step_hours))


def window_count(flows, mode):
    """How many windows of this mode the period has (1 for the whole period)."""

    if mode == "all":
        return 1

    return math.ceil(flows.n_steps / steps_in(flows, mode))


def is_long(flows):
    """True if the period is longer than two weeks (the page then tells how to zoom into the whole of it)."""

    return flows.n_steps * flows.step_hours > LONG_HOURS


def available_modes(flows):
    """The modes that make sense for this period, in the order of the buttons; empty if the whole period is
    all there is to see (then there is nothing to choose)."""

    modes = [mode for mode in ("day", "week", "month") if window_count(flows, mode) >= 2]
    if not modes:
        return []

    return modes + ["all"]


def view_frame(flows, mode, position=0):
    """What a chart shows: the DataFrame of the window, and how many windows there are.

    `position` counts the windows from the start and is held between the first and the last. The whole period
    ('all') is every time step.
    """

    frame = flows.to_frame(with_end_row=False)

    if mode == "all":
        return frame, 1

    count = window_count(flows, mode)
    position = min(max(int(position), 0), count - 1)
    size = steps_in(flows, mode)

    return frame.iloc[position * size:(position + 1) * size], count