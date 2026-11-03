"""From a file that was chosen to a time series that is used: what happens in between.

No NiceGUI code in here, so it is easy to test. An UploadSession holds one file for one component
while the visitor prepares it: the settings of the import, the column, the part of the file that is
used, the unit of a price, and how a time step shorter than an hour is converted. At any moment it
can say what it would give (`build`) or why it cannot (`problem`), in a sentence.

The reading itself is `backend/timeseries_import.py`, the rules for a component are
`backend/series_input.py`.
"""

from dataclasses import replace
from datetime import datetime, time

import pandas as pd

from backend.price_units import DEFAULT_PRICE_UNIT
from backend.series_input import (
    aggregate_for,
    covers,
    is_hourly,
    needs_choice,
    numeric_columns,
    series_data,
    series_notices,
)
from backend.timeseries_import import ImportOptions, TimeSeriesFileError, read_table

PREVIEW_ROWS = 8

# a change of one of these changes the line numbers, so the detected lines are used again
LAYOUT_OPTIONS = ("encoding", "delimiter", "decimal", "sheet")
LINE_OPTIONS = ("header_line", "first_data_line")

START_SCENARIO, START_FILE = "scenario", "file"


def _cell(value, tr):
    """A cell of the preview as text, in the language of the reader."""

    if value is None or (isinstance(value, float) and value != value) or value is pd.NaT:
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, float):
        return tr.number(value)
    return str(value)


class UploadSession:
    """One file that is being prepared for one component."""

    def __init__(self, content, filename):
        self.content = content
        self.filename = filename
        self.options = ImportOptions()             # what the visitor decided; None means: detect it
        self.table = None                          # the ImportedTable, or None if the file cannot be read
        self.error = None                          # a TimeSeriesFileError: why it cannot be read
        self.column = None
        self.start_choice = None                   # START_SCENARIO or START_FILE; None: decided when it is needed
        self.price_unit = DEFAULT_PRICE_UNIT
        self.aggregate = None                      # "mean" or "sum": the visitor's answer for a demand in kW
        self.settings_open = False                 # the box with the import settings is open (for the page)
        self._read()

    # ----- reading the file --------------------------------------------------

    def _read(self):
        try:
            self.table = read_table(self.content, self.filename, self.options)
        except TimeSeriesFileError as error:
            self.table, self.error = None, error
            return

        self.error = None
        columns = self.columns()
        if self.column not in columns:
            self.column = columns[0] if columns else None

    def change(self, **changes):
        """Change import settings and read the file again. The line numbers are detected again if the layout changed."""

        options = replace(self.options, **changes)
        if any(name in changes for name in LAYOUT_OPTIONS) and not any(name in changes for name in LINE_OPTIONS):
            options = replace(options, header_line=None, first_data_line=None)

        self.options = options
        self._read()

    # ----- what the file holds -----------------------------------------------

    @property
    def readable(self):
        return self.table is not None

    def columns(self):
        """The columns that hold numbers."""

        return numeric_columns(self.table) if self.table is not None else []

    def sheets(self):
        """The sheets of an Excel file (empty for a CSV file)."""

        return list(self.table.sheets) if self.table is not None else []

    def has_dates(self):
        return self.table is not None and self.table.time is not None

    def is_hourly(self):
        return self.table is None or is_hourly(self.table)

    def preview(self, tr, rows=PREVIEW_ROWS):
        """(columns, rows) for a table that shows the first rows of the file, in the language of the reader."""

        shown = self.table.df.head(rows)
        columns = [{"name": str(i), "label": str(name), "field": str(i), "align": "left"}
                   for i, name in enumerate(shown.columns)]
        table_rows = [{str(i): _cell(value, tr) for i, value in enumerate(row)}
                      for row in shown.itertuples(index=False)]

        return columns, table_rows

    # ----- what the visitor decides ------------------------------------------

    def start_choice_for(self, scenario_start):
        """START_SCENARIO if the file includes the start of the scenario (the default), else START_FILE."""

        if self.start_choice is not None:
            return self.start_choice
        if self.has_dates() and covers(self.table, self._moment(scenario_start)):
            return START_SCENARIO
        return START_FILE

    @staticmethod
    def _moment(day):
        return day if isinstance(day, datetime) else datetime.combine(day, time.min)

    def needs_aggregate(self, component):
        """True if the visitor has to say how the file is converted to hourly values (a demand in kW)."""

        return self.table is not None and not self.is_hourly() and needs_choice(component)

    # ----- what it gives -----------------------------------------------------

    def build(self, component, scenario_start):
        """The time series (a SeriesData) for the component. TimeSeriesFileError if it cannot be made."""

        if self.table is None:
            raise self.error
        if self.column is None:
            raise TimeSeriesFileError("no_numeric_column")

        start = None
        if self.has_dates() and self.start_choice_for(scenario_start) == START_SCENARIO:
            start = self._moment(scenario_start)

        return series_data(
            self.table, self.column, component,
            start=start,
            price_unit=self.price_unit if component.template == "grid" else None,
            aggregate=aggregate_for(component) or self.aggregate,
            filename=self.filename,
        )

    def problem(self, component, scenario_start):
        """Why no time series can be made now (a TimeSeriesFileError), or None."""

        try:
            self.build(component, scenario_start)
        except TimeSeriesFileError as error:
            return error

        return None

    def notices(self, component):
        """What to tell the visitor about the file: what the import found, and how it was converted."""

        if self.table is None:
            return []

        found = list(self.table.messages)
        if self.column is not None:
            try:
                found += series_notices(self.table, self.column, aggregate_for(component) or self.aggregate)
            except TimeSeriesFileError:
                pass                                   # the problem is shown on its own

        return found