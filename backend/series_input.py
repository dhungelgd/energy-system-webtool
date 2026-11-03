"""From an uploaded file to the time series of a component.

The file is read by `timeseries_import` (it finds the layout by itself). This module says what is
needed to use one of its columns for a component of the energy system: which component has a time
series and where, which part of the file is used, and in which unit it is stored.

Where a time series goes is given by the slot of the template of the component (see templates.py):
the demands, the PV system and the wind turbine need one, the grid (the price) and the heat pump
(the COP) can use a constant instead.

The model works with hourly values. A file with a shorter time step (15 minutes, for example) is
converted: by the average (power, profiles, prices) or by the sum (shares of the annual demand, energy
per time step). A demand in kW is the one case that the program cannot decide, because the column can
hold power or energy per time step; the user says (`aggregate_for` gives None). An hour in which a
value is missing stays empty; it is never averaged from fewer values.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

import math
from dataclasses import dataclass

import pandas as pd

from backend.price_units import DEFAULT_PRICE_UNIT, PRICE_UNIT_FACTORS
from backend.scenario_v2 import SeriesData, SeriesSource
from backend.templates import TEMPLATES
from backend.timeseries_import import Notice, StepText, TimeSeriesFileError, series_from_column

PRICE_UNITS = tuple(PRICE_UNIT_FACTORS)                # the units a price series can be uploaded in
OPTIONAL = ("grid", "heat_pump")                         # these can use a constant instead of a series
HOURLY_MINUTES = 60                                      # the model works with hourly values
AGGREGATES = ("mean", "sum")                             # how values with a shorter time step become hourly values
DEMANDS = ("demand", "heat_demand")


class Aggregate:
    """How hourly values were made, as words: 'average' or 'sum'."""

    def __init__(self, how):
        self.how = how

    def render(self, tr, names=None):
        return tr("import.aggregate.mean" if self.how == "mean" else "import.aggregate.sum")

    def __eq__(self, other):
        return isinstance(other, Aggregate) and other.how == self.how

    def __hash__(self):
        return hash(("Aggregate", self.how))


def aggregate_for(component):
    """How a file with a time step shorter than an hour becomes hourly values for this component.

    "mean" or "sum", or None if only the user knows: a demand in kW can be a power (the average) or an
    energy per time step (the sum). Shares of the annual demand are always added up.
    """

    if component.template in DEMANDS:
        kind = component.blocks.get("demand", {}).get("profile_type", "annual_share")
        return "sum" if kind == "annual_share" else None

    return "mean"


def needs_choice(component):
    """True if the user has to say how a file with a shorter time step is converted (a demand in kW)."""

    return has_series(component) and aggregate_for(component) is None


def slot_of(component):
    """Where the component keeps its time series (a SeriesSlot), or None if it has none."""

    template = TEMPLATES.get(component.template)

    return template.slots[0] if template and template.slots else None


def has_series(component):
    return slot_of(component) is not None


def is_optional(component):
    """True if the component can use a constant instead of a time series."""

    return component.template in OPTIONAL


def numeric_columns(table):
    """The names of the columns that hold numbers, in the order of the file."""

    return [name for name in table.df.columns if pd.api.types.is_numeric_dtype(table.df[name])]


def is_hourly(table):
    """False if the file says that its time step is not one hour (a file without dates is taken as hourly)."""

    return table.time is None or table.time.step_minutes == HOURLY_MINUTES


def _stamps(table):
    stamps = table.df[table.time.column]

    return stamps.dt.tz_localize(None) if stamps.dt.tz is not None else stamps


def covers(table, start):
    """True if the file has a date column that includes the start (a datetime)."""

    if table.time is None:
        return False

    stamps = _stamps(table).dropna()

    return bool(stamps.min() <= pd.Timestamp(start) <= stamps.max())


def _position(stamps, start):
    """The position of the first time stamp at or after the start. TimeSeriesFileError if it is outside."""

    first, last = stamps.min(), stamps.max()
    moment = pd.Timestamp(start)

    if not first <= moment <= last:
        def text(value):
            return value.strftime("%d.%m.%Y %H:%M")

        raise TimeSeriesFileError("start_outside", start=text(moment), first=text(first), last=text(last))

    return int((stamps >= moment).to_numpy().argmax())


def start_row(table, start):
    """The position of the first row at or after the start (a datetime).

    TimeSeriesFileError if the file has no date column or does not include the start.
    """

    if table.time is None:
        raise TimeSeriesFileError("no_time_column")

    return _position(_stamps(table), start)


def _hourly(table, column, aggregate):
    """The values of a column as hourly values, with the hour of each (None for a file without dates).

    A file with a time step of one hour (or without dates) is taken as it is. A shorter time step that
    divides the hour is converted by `aggregate` ("mean" or "sum"). An hour that does not have all its
    values (a missing row, an empty value, a repeated hour at the end of daylight saving time) is empty.
    """

    values = series_from_column(table, column)

    if table.time is None:
        return values, None

    stamps = _stamps(table)
    step = table.time.step_minutes

    if step == HOURLY_MINUTES:
        return values, stamps
    if step > HOURLY_MINUTES:
        raise TimeSeriesFileError("step_too_long", step=StepText(step))

    per_hour = HOURLY_MINUTES / step
    if abs(per_hour - round(per_hour)) > 1e-9:
        raise TimeSeriesFileError("step_not_divisor", step=StepText(step))
    if aggregate not in AGGREGATES:
        raise TimeSeriesFileError("convert_needed", step=StepText(step))

    per_hour = int(round(per_hour))
    frame = pd.DataFrame({
        "hour": stamps.dt.floor("h"),
        "value": pd.Series(values, index=stamps.index),
    }).dropna(subset=["hour"])

    grouped = frame.groupby("hour")["value"]
    complete = (grouped.size() == per_hour) & (grouped.count() == per_hour)
    result = (grouped.mean() if aggregate == "mean" else grouped.sum()).where(complete)

    hours = pd.date_range(result.index.min(), result.index.max(), freq="h")      # an hour without any row stays empty
    result = result.reindex(hours)

    return result.tolist(), pd.Series(hours)


def series_notices(table, column, aggregate=None):
    """What to tell the user about the conversion to hourly values (nothing for a file that is hourly)."""

    if table.time is None or is_hourly(table):
        return []

    values, hours = _hourly(table, column, aggregate)
    incomplete = [i for i, value in enumerate(values) if isinstance(value, float) and math.isnan(value)]

    notices = [Notice(
        "info", "converted",
        rows=len(table.df), step=StepText(table.time.step_minutes), hours=len(values), how=Aggregate(aggregate),
    )]
    if incomplete:
        notices.append(Notice(
            "warning", "incomplete_hours",
            n=len(incomplete), first=hours[incomplete[0]].strftime("%d.%m.%Y %H:%M"),
        ))

    return notices


def series_data(table, column, component, *, start=None, price_unit=None, aggregate=None, filename=None):
    """The values of a column as the time series of a component (a SeriesData), in hourly values.

    start       a datetime: use the file from the first row at or after it (the file needs dates)
    price_unit  for a price: the unit of the file (PRICE_UNITS); the series is stored in EUR/kWh
    aggregate   "mean" or "sum": how a file with a time step shorter than an hour becomes hourly values
                (see aggregate_for); a file that is hourly does not need it
    filename    where it came from, for the record
    """

    slot = slot_of(component)
    if slot is None:
        raise ValueError(f"the component '{component.template}' has no time series")

    values, hours = _hourly(table, column, aggregate)

    if any(isinstance(v, float) and math.isinf(v) for v in values):
        raise TimeSeriesFileError("infinite_values", column=column)

    if start is not None:
        if hours is None:
            raise TimeSeriesFileError("no_time_column")
        values = values[_position(hours, start):]

    if component.template == "grid":
        unit = price_unit or DEFAULT_PRICE_UNIT
        if unit not in PRICE_UNIT_FACTORS:
            raise ValueError(f"unknown price unit '{unit}'; use one of {', '.join(PRICE_UNITS)}")
        values = [v * PRICE_UNIT_FACTORS[unit] for v in values]

    # a demand can hold shares or kW (the choice is made in its form), so it has no unit of its own
    unit_text = "" if component.template in ("demand", "heat_demand") else slot.unit

    return SeriesData(
        unit=unit_text,
        source=SeriesSource(file=filename, column=column),
        values=values,
    )


@dataclass(frozen=True)
class SeriesSummary:
    """What to tell the user about a time series."""

    count: int
    empty: int
    minimum: float
    maximum: float
    total: float


def summarize(data):
    """Count, empty values, smallest, largest and sum of the values of a SeriesData."""

    numbers = [v for v in data.values if v is not None]

    return SeriesSummary(
        count=len(data.values),
        empty=len(data.values) - len(numbers),
        minimum=min(numbers) if numbers else math.nan,
        maximum=max(numbers) if numbers else math.nan,
        total=math.fsum(numbers),
    )