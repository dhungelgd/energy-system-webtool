"""One file with all the time series: which column is for which component.

A scenario needs several series (the demands, the PV system, the wind turbine, the price of the grid, the COP of
the heat pump). They are often in one CSV or Excel file with a column for each. A BulkSession holds that file
while the visitor assigns the columns: it suggests a column for each component from the names of the columns, the
visitor can change that, and at any moment it can say what each assignment would give or why it cannot.

Nothing new is read or checked here: the file is read by one UploadSession (series_session.py), and a column is
made a series of a component by that session, exactly as in the upload of a single series. No NiceGUI code in
here, so it is easy to test.
"""

import copy
import math
import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

from backend.series_input import aggregate_for, has_series, series_notices
from backend.timeseries_import import TimeSeriesFileError
from frontend_nicegui.series_session import UploadSession

# what a column of a component is called (words of the name, without accents, upper case or signs), and what it
# is not: ('waerme', 'heat' ... say heat; 'preis' says a price). The first column that fits is taken.
RULES = {
    "heat_pump": (("cop", "arbeitszahl", "leistungszahl", "jaz"), ()),
    "heat_demand": (("warme", "waerme", "heat", "heiz", "thermal", "fernwarme"), ("cop", "preis", "price", "pump")),
    "pv": (("pv", "photovolt", "solar", "sonne"), ("preis", "price")),
    "wind": (("wind",), ("preis", "price")),
    "grid": (("preis", "price", "tarif", "spot", "borse", "boerse", "dayahead", "epex"),
             ("gas", "warme", "waerme", "heat", "einspeis", "feedin")),
    "demand": (("strom", "elektr", "electric", "last", "load", "demand", "bedarf", "verbrauch", "consumption"),
               ("warme", "waerme", "heat", "heiz", "thermal", "preis", "price", "cop", "pv", "wind", "solar",
                "erzeug", "einspeis", "feedin")),
}
# the specific ones first, so that a column that fits the PV system is not taken for the electricity demand
PRIORITY = ("heat_pump", "heat_demand", "pv", "wind", "grid", "demand")

NONE = None                      # no column: the series of the component is not taken from this file

# the order in which the components that fit the columns of a file are added (the demands first)
ADD_ORDER = ("demand", "heat_demand", "grid", "pv", "wind", "heat_pump")


@dataclass(frozen=True)
class FilePeriod:
    """The time that a file covers: when it starts and ends (None for a file without dates) and how many hours."""

    start: object
    end: object
    hours: int


def compact(name):
    """A column name as plain lower case letters and digits: 'Wärme-Bedarf [kWh]' becomes 'warmebedarfkwh'."""

    plain = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")

    return re.sub(r"[^a-z0-9]", "", plain.lower())


def fits(key, column):
    """True if the name of the column looks like a column for the component `key` (its template)."""

    include, exclude = RULES.get(key, ((), ()))
    name = compact(column)

    return any(word in name for word in include) and not any(word in name for word in exclude)


def kind_of(column):
    """The component that the name of the column looks like (its template), or None if it looks like none."""

    return next((key for key in PRIORITY if fits(key, column)), None)


def guess(keys, columns, taken=()):
    """A column for each component, from the names of the columns: {key: column or None}. A column is taken
    once; `taken` are columns that are used already."""

    used = set(taken)
    found = {}

    for key in sorted(keys, key=lambda k: PRIORITY.index(k) if k in PRIORITY else len(PRIORITY)):
        column = next((c for c in columns if c not in used and fits(key, c)), None)
        found[key] = column
        if column is not None:
            used.add(column)

    return found


class BulkSession:
    """One file for all the series of the draft, and which column is for which component."""

    def __init__(self, content, filename):
        self.master = UploadSession(content, filename)      # the file, its settings, the unit of a price ...
        self.mapping = {}                                   # component key -> column, or None for 'none'
        self.decided = set()                                # the components whose column the visitor chose himself
        self.applied = {}                                   # component key -> (column, choices) when its series was taken

    # ----- the file ----------------------------------------------------------

    @property
    def filename(self):
        return self.master.filename

    @property
    def readable(self):
        return self.master.readable

    @property
    def error(self):
        return self.master.error

    def columns(self):
        return self.master.columns()

    def overview(self):
        """What the file holds, a row for each column of numbers: {'column', 'values' (how many are filled), 'kind'
        (the component that its name looks like, or None)}."""

        if not self.readable:
            return []

        frame = self.master.table.df

        return [{"column": column, "values": int(frame[column].notna().sum()), "kind": kind_of(column)}
                for column in self.columns()]

    def period(self):
        """The time that the file covers (a FilePeriod), or None if it cannot be read. A file without dates has
        as many hours as it has rows (it is taken as hourly); a time step shorter than an hour counts as part of one."""

        if not self.readable:
            return None

        axis = self.master.table.time
        if axis is None:
            return FilePeriod(None, None, len(self.master.table.df))

        def naive(stamp):
            stamp = pd.Timestamp(stamp)
            return (stamp.tz_localize(None) if stamp.tzinfo is not None else stamp).to_pydatetime()

        return FilePeriod(naive(axis.start), naive(axis.end), math.ceil(axis.rows * axis.step_minutes / 60))

    def suggested_components(self, draft):
        """The components that the columns of the file look like and that the draft does not have yet, in the order
        in which they are added. A column suggests one component only (as in the assignment)."""

        found = guess(PRIORITY, self.columns())
        present = {component.template for component in draft.components()}

        return [key for key in ADD_ORDER if found.get(key) is not None and key not in present]

    # ----- the assignment ----------------------------------------------------

    @staticmethod
    def components_with_series(draft):
        """The components of the draft that have a time series, in the order of the draft."""

        return [component for component in draft.components() if has_series(component)]

    def update(self, components):
        """Bring the assignment in line with the components and the columns that there are now.

        What the visitor chose himself stays, also 'none', as long as the component is part of the draft and the
        column is in the file (a column that the file does not have any more, after it was read again with other
        settings, is forgotten). For every other component the column that its name suggests is taken, from the
        columns that the visitor did not choose for another component: a suggestion is made again each time, so
        it follows the components and the columns that there are now.
        """

        keys = [component.template for component in components]
        columns = self.columns()

        self.decided = {key for key in self.decided if key in keys}
        for key in list(self.decided):
            column = self.mapping.get(key)
            if column is not None and column not in columns:
                self.decided.discard(key)

        chosen = {key: self.mapping[key] for key in self.decided}
        taken = {column for column in chosen.values() if column is not None}
        self.mapping = {**chosen, **guess([key for key in keys if key not in self.decided], columns, taken=taken)}

    def choose(self, key, column):
        """The visitor chose a column for the component (None: no column)."""

        self.mapping[key] = column
        self.decided.add(key)

    def assigned(self, components):
        """(component, column) for each component that has a column."""

        return [(component, self.mapping[component.template]) for component in components
                if self.mapping.get(component.template) is not None]

    # ----- what it gives -----------------------------------------------------

    def child(self, column):
        """An UploadSession of the same file for one column (the settings and the choices are shared)."""

        session = copy.copy(self.master)
        session.column = column

        return session

    def build(self, component, column, scenario_start):
        """The time series (a SeriesData) of the component from the column. TimeSeriesFileError if it cannot be made."""

        return self.child(column).build(component, scenario_start)

    def results(self, components, scenario_start):
        """For each assigned component: (its SeriesData, None), or (None, why it cannot be made as a TimeSeriesFileError)."""

        found = {}
        for component, column in self.assigned(components):
            try:
                found[component.template] = (self.build(component, column, scenario_start), None)
            except TimeSeriesFileError as error:
                found[component.template] = (None, error)

        return found

    def choices(self, draft):
        """What the series that are made from the file depend on besides the column: the unit of a price, the answer
        for the hours, the part of the file, the settings of the import, and the start of the scenario."""

        master = self.master

        return (master.price_unit, master.aggregate, master.start_choice, repr(master.options), str(draft.start))

    def is_used(self, key, column, draft):
        """True if the component has the series of this column of this file, made with the choices that are now."""

        data = draft.series_of(key)

        return (
            self.applied.get(key) == (column, self.choices(draft))
            and data is not None and data.source is not None
            and data.source.file == self.filename and data.source.column == column
        )

    def pending(self, components, draft):
        """The keys of the assigned components whose column is not taken over yet (or not with the choices that are now)."""

        return [component.template for component, column in self.assigned(components)
                if not self.is_used(component.template, column, draft)]

    def usable(self, components, draft):
        """True if there is something to take over: a column is assigned and not used yet, and every one of those
        can be made a series."""

        results = self.results(components, draft.start)
        pending = self.pending(components, draft)

        return bool(pending) and all(results[key][1] is None for key in pending)

    def notices(self, component, column):
        """What to tell the visitor about one column: how it is converted, and what is missing in it. (What the
        import found in the file as a whole is in `master.table.messages`, and is told once.)"""

        try:
            return list(series_notices(self.master.table, column, aggregate_for(component) or self.master.aggregate))
        except TimeSeriesFileError:
            return []                                   # the problem is shown on its own

    def needs_aggregate(self, components):
        """True if a demand in kW is assigned and the file has a step shorter than an hour: the visitor says how it is converted."""

        return any(self.master.needs_aggregate(component) for component, _ in self.assigned(components))

    def apply(self, draft, components):
        """Give each assigned component its series, except those that have it already from this file. Returns the keys
        of the components that got one now."""

        done = []
        for key, (data, problem) in self.results(components, draft.start).items():
            if problem is None and not self.is_used(key, self.mapping[key], draft):
                draft.set_series(key, data)
                self.applied[key] = (self.mapping[key], self.choices(draft))
                done.append(key)

        return done