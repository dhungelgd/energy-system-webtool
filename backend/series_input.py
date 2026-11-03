"""From an uploaded file to the time series of a component.

The file is read by `timeseries_import` (it finds the layout by itself). This module says what is
needed to use one of its columns for a component of the energy system: which component has a time
series and where, which part of the file is used, and in which unit it is stored.

Where a time series goes is given by the slot of the template of the component (see templates.py):
the demands, the PV system and the wind turbine need one, the grid (the price) and the heat pump
(the COP) can use a constant instead.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

import math
from dataclasses import dataclass

import pandas as pd

from backend.price_units import DEFAULT_PRICE_UNIT, PRICE_UNIT_FACTORS
from backend.scenario_v2 import SeriesData, SeriesSource
from backend.templates import TEMPLATES
from backend.timeseries_import import TimeSeriesFileError, series_from_column

PRICE_UNITS = tuple(PRICE_UNIT_FACTORS)                # the units a price series can be uploaded in
OPTIONAL = ("grid", "heat_pump")                         # these can use a constant instead of a series
HOURLY_MINUTES = 60                                      # the model works with hourly values


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


def start_row(table, start):
    """The position of the first row at or after the start (a datetime).

    TimeSeriesFileError if the file has no date column or does not include the start.
    """

    if table.time is None:
        raise TimeSeriesFileError("no_time_column")

    stamps = _stamps(table)
    first, last = stamps.min(), stamps.max()
    moment = pd.Timestamp(start)

    if not first <= moment <= last:
        def text(value):
            return value.strftime("%d.%m.%Y %H:%M")

        raise TimeSeriesFileError("start_outside", start=text(moment), first=text(first), last=text(last))

    return int((stamps >= moment).to_numpy().argmax())


def series_data(table, column, component, *, start=None, price_unit=None, filename=None):
    """The values of a column as the time series of a component (a SeriesData).

    start       a datetime: use the file from the first row at or after it (the file needs dates)
    price_unit  for a price: the unit of the file (PRICE_UNITS); the series is stored in EUR/kWh
    filename    where it came from, for the record
    """

    slot = slot_of(component)
    if slot is None:
        raise ValueError(f"the component '{component.template}' has no time series")

    values = series_from_column(table, column)

    if any(isinstance(v, float) and math.isinf(v) for v in values):
        raise TimeSeriesFileError("infinite_values", column=column)

    if start is not None:
        values = values[start_row(table, start):]

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