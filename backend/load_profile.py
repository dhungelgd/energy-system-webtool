"""Reading and checking a load profile (a Lastgang): how much electric power a site used, in steps of a quarter of an
hour or an hour, for months or a year.

A file is read with the reader of time series files (timeseries_import.py: encoding, delimiter, decimal sign, Excel,
lines above the table). This module adds what is special about a load profile:

- the time can be in one column or in two (date and time of day), "24:00" is the start of the next day;
- the values are power (kW, W, MW) or energy in each time step (kWh, Wh, MWh); energy is turned into power;
- a time can mean the start or the end of its time step; this is worked out from the first and the last time of the
  file, or the caller says it;
- the clock change: a file that has summer time has 23 and 25 hours on the two days of the change; the times are put on
  one regular line (UTC) and given back as local times; a file that has 24 hours on those days is used as written;
- a column whose values add up to 1 holds shares of the energy (a normalized profile): the energy that they stand for
  is asked for, and the power is made from it;
- what is wrong with the data is found and told, never repaired silently: gaps, times that appear twice, values that
  are empty, negative, far too high, or that do not change for hours.

The result is a LoadProfile with the power in kW on a regular line of time steps (a missing value is NaN). If the file
does not say which unit or which column is meant, `ready` is False and `needs` says what to ask; the caller reads the
file again with that answer (ProfileOptions). This module does not use NiceGUI, so any frontend can call it.
"""

import re
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from backend.column_names import kind_of
from backend.findings import Fixed, coded_text
from backend.i18n import ENGLISH
from backend.timeseries_import import ImportOptions, StepText, TimeSeriesFileError, import_text, read_table

DEFAULT_ZONE = "Europe/Berlin"

# the unit -> (factor to kW or kWh, is it energy in a time step)
UNITS = {
    "W": (0.001, False), "kW": (1.0, False), "MW": (1000.0, False),
    "Wh": (0.001, True), "kWh": (1.0, True), "MWh": (1000.0, True),
}
SUPPORTED_STEPS = (1, 2, 3, 5, 6, 10, 12, 15, 20, 30, 60)       # minutes: a step that fits into an hour
FLAT_RUN_HOURS = 24              # the same value, not zero, for this long: the meter may have stood still
SPIKE_FACTOR = 2.5               # a value above this times the 99th percentile is far above the others
MIN_VALUES_FOR_SPIKES = 200
SHORT_PERIOD_DAYS = 360          # shorter than this is not a year
LONG_PERIOD_DAYS = 370
COARSE_STEP_MINUTES = 15         # a coarser step averages the peaks
OFF_GRID_ERROR_SHARE = 0.01      # more times than this off the regular line: the file is not a regular series
SHARE_TOLERANCE = 0.02           # values that add up to 1 within this are shares of an energy
SHARE = "share"                  # the unit of such a column (not one of UNITS: it needs the energy)

# what the reader of time series files says about a file and a load profile says better or not at all
DROPPED_IMPORT_CODES = {"time_info", "time_step_not_hourly", "unsorted", "duplicates", "gaps", "no_date_column"}

_UNIT_RE = re.compile(r"(?<![a-zA-Z])(mwh|kwh|wh|mw|kw)(?![a-zA-Z])", re.IGNORECASE)
_BRACKET_W_RE = re.compile(r"[\[(]\s*w\s*[\])]", re.IGNORECASE)
_NOT_THE_LOAD_RE = re.compile(
    r"blind|kvar|reactive|status|qualit|flag|stand\b|z[aä]hler|temperatur|\btemp\b|nummer|\bid\b", re.IGNORECASE)
_THE_LOAD_RE = re.compile(
    r"wirk|leistung|power|\blast|load|verbrauch|arbeit|energie|energy|consumption|\bkw|\bmw|wh\b", re.IGNORECASE)
_CANONICAL_UNITS = {unit.lower(): unit for unit in UNITS}
# a unit after these is a price per unit (ct/kWh, EUR per MWh, ct_kwh), not the unit of the values
_PRICE_BEFORE_RE = re.compile(r"(?:ct|cent|eur|euro|usd|[€$])[\s_\-]*$|(?:/|\bper|\bpro)[\s_]*$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# errors and notices
# ---------------------------------------------------------------------------

class ProfileFileError(ValueError):
    """The file cannot be read as a load profile.

    `code` and `params` say what is the matter; the sentence for the user is in the catalogs under "profile.error.<code>"
    (`profile_text` words it in a language). `str(error)` is the English sentence.
    """

    def __init__(self, code, **params):
        self.code = code
        self.params = params
        super().__init__(coded_text("profile.error", code, params, ENGLISH))

    def __reduce__(self):
        return (_error, (self.code, self.params))


def _error(code, params):
    return ProfileFileError(code, **params)


class ProfileNotice(tuple):
    """A message about a load profile: (level, English sentence), with a `code` and `params` for wording it in another
    language (`profile_text`). The level is "info" or "warning"."""

    def __new__(cls, level, code, **params):
        item = super().__new__(cls, (level, coded_text("profile", code, params, ENGLISH)))
        item.code = code
        item.params = params
        return item

    def __getnewargs_ex__(self):
        return (self[0], self.code), self.params

    @property
    def level(self):
        return self[0]

    @property
    def text(self):
        return self[1]


def profile_text(item, tr):
    """The sentence for a notice or an error of reading a load profile, in the language of `tr`. A notice of the reader of
    time series files (the decimal sign, a date that could not be read) is worded by that reader."""

    if isinstance(item, ProfileFileError):
        return coded_text("profile.error", item.code, item.params, tr)
    if isinstance(item, ProfileNotice):
        return coded_text("profile", item.code, item.params, tr)

    return import_text(item, tr)


@dataclass(frozen=True)
class Count:
    """A whole number, written with the separators of the language."""

    value: int

    def render(self, tr, names=None):
        return tr.integer(int(self.value))


@dataclass(frozen=True)
class DurationText:
    """A length of time as words: '45 minutes', '6 hours', '3 days'."""

    minutes: int

    def render(self, tr, names=None):
        if self.minutes < 60:
            return tr("profile.duration.minutes", value=tr.integer(int(self.minutes)))
        if self.minutes < 48 * 60:
            return tr("profile.duration.hours", value=tr.number(round(self.minutes / 60, 1)))

        return tr.plural("profile.duration.days", int(round(self.minutes / 1440)))


@dataclass(frozen=True)
class UnitText:
    """A unit as words: 'kW (power)' or 'kWh (energy in each time step, turned into power)'."""

    unit: str

    def render(self, tr, names=None):
        return tr("profile.unit.energy" if UNITS[self.unit][1] else "profile.unit.power", unit=self.unit)


@dataclass(frozen=True)
class StampText:
    """A time as words, written as the language writes dates: 01.01.2024 00:15."""

    stamp: pd.Timestamp

    def render(self, tr, names=None):
        return self.stamp.strftime(tr("profile.stamp_format"))


# ---------------------------------------------------------------------------
# what the caller can decide, and what comes back
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProfileOptions:
    """What the caller decided. None means: work it out from the file."""

    file: ImportOptions = None       # how to read the file itself (delimiter, decimal sign, lines)
    value_column: str = None         # the column with the load
    unit: str = None                 # one of UNITS
    stamp_at: str = None             # "start" or "end": what a time means for its time step
    timezone: str = DEFAULT_ZONE
    date_column: str = None
    energy_kwh: float = None         # the energy that a column of shares (adding up to 1) stands for

    def __post_init__(self):
        if self.stamp_at not in (None, "start", "end"):
            raise ValueError(f"stamp_at must be 'start' or 'end', not '{self.stamp_at}'")
        if self.energy_kwh is not None and not (self.energy_kwh > 0 and np.isfinite(self.energy_kwh)):
            raise ValueError(f"energy_kwh must be a number above zero, not '{self.energy_kwh}'")


@dataclass(frozen=True)
class Candidate:
    """A column that could hold the load, and the unit that its name or the line below it gives (or None)."""

    name: str
    unit: str = None


@dataclass(frozen=True)
class SheetInfo:
    """What a sheet of an Excel file holds, to choose the right one."""

    name: str
    rows: int = 0
    number_columns: int = 0          # the columns with numbers
    start: pd.Timestamp = None       # the first and the last time, if the sheet has a column of dates and times
    end: pd.Timestamp = None
    step_minutes: float = None
    problem: str = None              # "no_time" (no dates found) or "unreadable"


@dataclass
class LoadProfile:
    file_name: str
    ready: bool                      # False while a decision is open: see `needs`
    needs: list                      # "value_column", "unit" or "energy": what the file does not say
    candidates: list                 # the columns that could hold the load (Candidate)
    notices: list                    # ProfileNotice and notices of the reader of time series files
    value_column: str = None
    unit: str = None                 # one of UNITS, or SHARE for a column of shares
    step_minutes: int = None
    stamp_at: str = None             # "start" or "end", as it was used
    time_basis: str = None           # "local" (with the clock change) or "as_written" (used as written)
    time_zone: str = None            # the zone of the times of `power_kw`; "UTC" for a file that is used as written
    power_kw: pd.Series = None       # kW at the start of each time step, regular, NaN where a value is missing
    rows: int = 0                    # how many times the file had
    preview: dict = field(default_factory=dict)      # what the energy would be as power and as energy, if unit is open

    def energy_kwh(self):
        """The energy of all the time steps that have a value."""

        return float(self.power_kw.sum() * self.step_minutes / 60)

    def peak_kw(self):
        """The highest power of a time step."""

        return float(self.power_kw.max())

    def missing_share(self):
        """How much of the period has no value (0 to 1)."""

        return float(self.power_kw.isna().mean())


# ---------------------------------------------------------------------------
# the time
# ---------------------------------------------------------------------------

def _stamps(df, options):
    """The time of each row (as the file writes it, no time zone), and the columns that it came from."""

    date_name = options.date_column
    if date_name is not None and date_name not in df.columns:
        raise ProfileFileError("column_missing", column=date_name)
    if date_name is None:
        date_name = next((name for name in df.columns if pd.api.types.is_datetime64_any_dtype(df[name])), None)
    if date_name is None or df[date_name].notna().sum() == 0:
        raise ProfileFileError("no_time")

    return df[date_name], [date_name]                           # the reader has joined a date and a time of day in two columns


def _step_minutes(unique_stamps):
    """The usual time between two times, in minutes, if the time step is one that the analysis can use."""

    steps = pd.Series(unique_stamps).diff().dropna()
    steps = steps[steps > pd.Timedelta(0)]
    seconds = steps.mode().iloc[0].total_seconds()
    minutes = seconds / 60

    if minutes > 60:
        raise ProfileFileError("step_too_coarse", step=StepText(int(round(minutes))))
    if abs(minutes - round(minutes)) > 0.01 or int(round(minutes)) not in SUPPORTED_STEPS:
        raise ProfileFileError("step_unsupported", step=Fixed(round(minutes, 2), 2))

    return int(round(minutes))


def _stamp_convention(first, last, step):
    """Does a time mean the start or the end of its time step? From the first and the last time of the file: a profile
    of whole days begins at 00:00 (start) or at 00:15 (end), and ends at 23:45 (start) or at the next 00:00 (end).
    Gives (convention, sure)."""

    def minutes_of_day(stamp):
        return stamp.hour * 60 + stamp.minute

    start_score = (minutes_of_day(first) == 0) + (minutes_of_day(last) == 24 * 60 - step)
    end_score = (minutes_of_day(first) == step) + (minutes_of_day(last) == 0)

    if start_score > end_score:
        return "start", True
    if end_score > start_score:
        return "end", True

    return "start", False


def _clock_change_days(first, last, zone):
    """(day, hours that the clock moves) for each day between the first and the last day on which the clock changes,
    where the clock moves forward by a positive number (so the day has fewer hours) and back by a negative one."""

    days = pd.date_range(first.normalize(), last.normalize(), freq="D")
    offsets = [(day + pd.Timedelta(hours=12)).tz_localize(zone).utcoffset() for day in days]

    return [
        (days[i], (offsets[i] - offsets[i - 1]).total_seconds() / 3600)
        for i in range(1, len(days))
        if offsets[i] != offsets[i - 1] and days[i] > first.normalize() and days[i] < last.normalize()
    ]


def _time_basis(stamps, step, zone):
    """'local' if the days of the clock change have 23 and 25 hours in the file, 'as_written' if they have 24 (the file is
    in winter time or has no clock change). Gives (basis, notice or None)."""

    changes = _clock_change_days(stamps.min(), stamps.max(), zone)
    if not changes:
        return "local", None

    per_hour = 60 / step
    rows = stamps.dt.normalize().value_counts()
    votes = []
    for day, shift in changes:
        count = int(rows.get(day, 0))
        if count == int(round((24 - shift) * per_hour)):             # the clock moves forward: 23 hours
            votes.append("local")
        elif count == int(round(24 * per_hour)):
            votes.append("as_written")

    if not votes:
        return "local", None
    if all(vote == "local" for vote in votes):
        return "local", ProfileNotice("info", "time_local")
    if all(vote == "as_written" for vote in votes):
        return "as_written", ProfileNotice("info", "time_as_written")

    return "as_written", ProfileNotice("warning", "time_inconsistent")


def _instants(stamps, basis, zone):
    """The times as moments on one line (UTC). In a file with summer time the hour at the end of it appears twice: the
    first time is summer time, the second winter time."""

    index = pd.DatetimeIndex(stamps)

    if basis == "as_written":
        return index.tz_localize("UTC")

    summer = ~index.duplicated(keep="first")

    return index.tz_localize(zone, ambiguous=summer, nonexistent="shift_forward").tz_convert("UTC")


# ---------------------------------------------------------------------------
# the values
# ---------------------------------------------------------------------------

def _looks_like_shares(values):
    """True if the values are not negative and add up to 1: shares of an energy (a normalized profile)."""

    present = values.dropna()

    return len(present) >= 3 and bool((present >= 0).all()) and abs(float(present.sum()) - 1.0) <= SHARE_TOLERANCE


def _unit_in(text):
    """The unit that a text names (a column name, a line of units), or None if it names none or several."""

    if not isinstance(text, str):
        return None

    units = {
        found.group(1).lower() for found in _UNIT_RE.finditer(text) if not _PRICE_BEFORE_RE.search(text[:found.start()])
    }
    if len(units) == 1:
        return _CANONICAL_UNITS[units.pop()]
    if not units and _BRACKET_W_RE.search(text):
        return "W"

    return None


def _unit_below_the_header(table, content, position):
    """The unit that the line below the column names gives for the column at `position` (CSV only), or None."""

    used = table.used
    if table.kind != "csv" or not used.header_line or used.first_data_line is None or used.first_data_line - used.header_line < 2:
        return None

    try:
        lines = content.decode(used.encoding or "utf-8", errors="replace").splitlines()
        cells = lines[used.first_data_line - 2].split(used.delimiter or ";")
    except (LookupError, IndexError):
        return None

    return _unit_in(cells[position]) if position < len(cells) else None


def _value_columns(df, time_columns, content, table, options):
    """The columns that could hold the load, as Candidates, and the one that is meant (or None if it is not clear)."""

    numeric = [
        name for name in df.columns
        if name not in time_columns and pd.api.types.is_numeric_dtype(df[name]) and df[name].notna().any()
    ]
    if not numeric:
        raise ProfileFileError("no_numbers")

    names = list(df.columns)
    candidates = [
        Candidate(name, _unit_in(name) or _unit_below_the_header(table, content, names.index(name)))
        for name in numeric
    ]

    if options.value_column is not None:
        if options.value_column not in numeric:
            raise ProfileFileError("column_missing", column=options.value_column)
        return candidates, options.value_column

    # not the load: a column that looks like a price, a PV profile, a COP ... (the words of the files with all the series)
    likely = [name for name in numeric if not _NOT_THE_LOAD_RE.search(name) and kind_of(name) in (None, "demand")]
    if len(likely) == 1:
        return candidates, likely[0]

    named = [name for name in likely if _THE_LOAD_RE.search(name)]
    if len(named) == 1:
        return candidates, named[0]

    return candidates, None


# ---------------------------------------------------------------------------
# what is wrong with the data
# ---------------------------------------------------------------------------

def _runs(flags):
    """The lengths of the runs of True in a boolean array."""

    values = np.asarray(flags, dtype=bool)
    if not values.any():
        return []

    padded = np.concatenate(([False], values, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])

    return (changes[1::2] - changes[::2]).tolist()


def _flat_runs(power, step):
    """The lengths (in time steps) of the runs in which the value stays the same and is not zero, and is long enough."""

    values = power.to_numpy()
    same = np.zeros(len(values), dtype=bool)
    same[1:] = (values[1:] == values[:-1]) & (values[1:] != 0)
    minimum = FLAT_RUN_HOURS * 60 // step

    return [length + 1 for length in _runs(same) if length + 1 >= minimum]


def _quality_notices(power, step):
    """The warnings about the values of the regular series (before anything is filled in)."""

    notices = []
    missing = power.isna()

    gaps = _runs(missing)
    if gaps:
        notices.append(ProfileNotice(
            "warning", "gaps", n=len(gaps), missing=Count(int(missing.sum())), share=Fixed(100 * float(missing.mean()), 1),
            longest=DurationText(max(gaps) * step)))

    present = power.dropna()
    negative = present[present < 0]
    if len(negative):
        notices.append(ProfileNotice("warning", "negative", n=len(negative), min=Fixed(float(negative.min()), 1)))

    if len(present) >= MIN_VALUES_FOR_SPIKES:
        limit = SPIKE_FACTOR * float(present.quantile(0.99))
        high = present[present > limit]
        if limit > 0 and len(high):
            notices.append(ProfileNotice(
                "warning", "spikes", n=len(high), max=Fixed(float(high.max()), 1), limit=Fixed(limit, 1)))

    flat = _flat_runs(power, step)
    if flat:
        notices.append(ProfileNotice("warning", "flat_run", n=len(flat), hours=Fixed(max(flat) * step / 60, 1)))

    return notices


# ---------------------------------------------------------------------------
# the reader
# ---------------------------------------------------------------------------

def read_load_profile(content, filename, options=None, table=None):
    """Read a file as a load profile.

    content   the bytes of the file (CSV or Excel)
    filename  tells CSV from Excel (by the extension) and is kept in the result
    options   ProfileOptions; what is left at None is worked out
    table     the file as it was read already (the page lets the visitor change how it is read); None: it is read here

    Gives a LoadProfile. If the file does not say which of its columns is the load, or in which unit, `ready` is False
    and `needs` says what to ask; read the file again with the answer. Raises ProfileFileError (and, for a file that
    cannot be read at all, TimeSeriesFileError) with a message for the user.
    """

    options = options or ProfileOptions()
    table = table if table is not None else read_table(content, filename, options.file)
    df = table.df
    notices = []

    stamps, time_columns = _stamps(df, options)
    values_candidates, column = _value_columns(df, time_columns, content, table, options)

    rows = pd.DataFrame({"stamp": stamps.to_numpy(), "value": np.nan})
    if column is not None:
        rows["value"] = df[column].to_numpy()
    rows = rows[rows["stamp"].notna()]
    if rows["stamp"].nunique() < 3:
        raise ProfileFileError("too_few_rows", rows=int(rows["stamp"].nunique()))

    rows = rows.reset_index(drop=True)                  # the order of the file: the hour at the end of summer time depends on it
    stamps_sorted = rows["stamp"].sort_values(kind="stable").reset_index(drop=True)
    step = _step_minutes(stamps_sorted.drop_duplicates())

    first, last = stamps_sorted.iloc[0], stamps_sorted.iloc[-1]
    if options.stamp_at is not None:
        stamp_at = options.stamp_at
    else:
        stamp_at, sure = _stamp_convention(first, last, step)
        if not sure:
            notices.append(ProfileNotice("warning", "stamp_assumed"))
    notices.append(ProfileNotice("info", "stamp_end") if stamp_at == "end" else ProfileNotice("info", "stamp_start"))

    basis, basis_notice = _time_basis(stamps_sorted, step, options.timezone)
    if basis_notice is not None:
        notices.append(basis_notice)

    notices.insert(0, ProfileNotice(
        "info", "file_info", rows=Count(len(stamps_sorted)), start=StampText(first), end=StampText(last),
        step=StepText(step)))
    if len(table.sheets) > 1:                           # say which sheet it is: the profile may be on another one
        notices.insert(1, ProfileNotice("info", "sheet_info", sheet=table.used.sheet, count=len(table.sheets)))

    chosen = next((c for c in values_candidates if c.name == column), None)
    shared = {c.unit for c in values_candidates}                  # the columns agree on one unit: no need to ask
    unit = options.unit or (chosen.unit if chosen else (shared.pop() if len(shared) == 1 else None))
    if unit is not None and unit not in UNITS:
        raise ProfileFileError("unit_invalid", unit=unit)

    shares = column is not None and unit is None and _looks_like_shares(rows["value"])
    if shares:
        unit = SHARE

    needs = ([] if column is not None else ["value_column"])
    if shares:
        needs += [] if options.energy_kwh else ["energy"]
    elif unit is None:
        needs += ["unit"]
    profile = LoadProfile(
        file_name=filename, ready=False, needs=needs, candidates=values_candidates, notices=notices,
        value_column=column, unit=unit, step_minutes=step, stamp_at=stamp_at, time_basis=basis,
        time_zone=options.timezone if basis == "local" else "UTC", rows=len(stamps_sorted))

    if column is not None and unit is None:               # help the person who has to choose
        total = float(rows["value"].sum())
        profile.preview = {"as_power_kwh": total * step / 60, "as_energy_kwh": total}
    if shares and not options.energy_kwh:
        profile.notices.append(ProfileNotice("info", "share_found"))

    if needs:
        profile.notices.extend(m for m in table.messages if m.code not in DROPPED_IMPORT_CODES)
        return profile

    # --- the values: on one regular line, as power
    instants = _instants(rows["stamp"], basis, options.timezone).round("min")
    if stamp_at == "end":
        instants = instants - pd.Timedelta(minutes=step)
    series = pd.Series(rows["value"].to_numpy(), index=instants)
    if not series.index.is_monotonic_increasing:        # a clock change alone does not do this: on the line of moments it is in order
        series = series.sort_index(kind="stable")
        profile.notices.append(ProfileNotice("info", "unsorted"))

    minutes = (series.index - series.index.min()) // pd.Timedelta(minutes=1)
    off_grid = np.asarray(minutes % step != 0)
    if off_grid.mean() > OFF_GRID_ERROR_SHARE:
        raise ProfileFileError("step_irregular", step=StepText(step))
    if off_grid.any():
        profile.notices.append(ProfileNotice("warning", "off_grid", n=int(off_grid.sum())))
        series = series[~off_grid]

    groups = series.groupby(level=0)
    summary = groups.agg(["size", "nunique"])
    repeated = summary["size"] > 1
    conflicting = repeated & (summary["nunique"] > 1)
    if conflicting.any():
        profile.notices.append(ProfileNotice("warning", "duplicates_conflict", n=int(conflicting.sum())))
    if (repeated & ~conflicting).any():
        profile.notices.append(ProfileNotice("info", "duplicates_same", n=int((repeated & ~conflicting).sum())))
    series = groups.first()

    grid = pd.date_range(series.index.min(), series.index.max(), freq=f"{step}min")
    series = series.reindex(grid)

    if shares:
        power = series * options.energy_kwh * 60 / step            # a share of the energy in a step, as power
    else:
        factor, is_energy = UNITS[unit]
        power = series * factor * (60 / step if is_energy else 1.0)
    power.index = power.index.tz_convert(options.timezone if basis == "local" else "UTC")
    power.name = "kW"

    days = len(power) * step / 1440
    profile.power_kw, profile.ready = power, True

    head = [profile.notices.pop(0), ProfileNotice("info", "column_info", column=column)]      # the file, the column, the unit
    others = [c.name for c in values_candidates if c.name != column]
    if others:
        head.append(ProfileNotice("info", "other_columns", columns=others))
    if shares:
        head.append(ProfileNotice("info", "share_info", energy=float(options.energy_kwh)))
    else:
        head.append(ProfileNotice("info", "unit_info", unit=UnitText(unit)))
    profile.notices[:0] = head

    if step > COARSE_STEP_MINUTES:
        profile.notices.append(ProfileNotice("warning", "coarse_step", step=StepText(step)))
    if days < SHORT_PERIOD_DAYS:
        profile.notices.append(ProfileNotice("warning", "short_period", days=Count(int(round(days)))))
    elif days > LONG_PERIOD_DAYS:
        profile.notices.append(ProfileNotice("info", "long_period", days=Count(int(round(days)))))

    profile.notices.extend(_quality_notices(power, step))
    profile.notices.extend(m for m in table.messages if m.code not in DROPPED_IMPORT_CODES)

    return profile


def sheet_overview(content, filename, file_options=None, names=None):
    """What each sheet of an Excel file holds, as a list of SheetInfo (empty for a CSV file and for a file with one sheet). The
    sheet that is read now is read with the options as they are, the others are read with everything detected. `names` are the
    sheets that the file is known to have, for the case that the sheet that is read now cannot be read."""

    options = file_options or ImportOptions()
    try:
        current = read_table(content, filename, options)
    except (TimeSeriesFileError, ValueError):
        current = None
    sheets = list(current.sheets) if current is not None else list(names or [])
    if len(sheets) < 2:
        return []

    result = []
    for name in sheets:
        try:
            table = current if current is not None and name == current.used.sheet else read_table(
                content, filename, replace(options, sheet=name, header_line=None, first_data_line=None))
        except (TimeSeriesFileError, ValueError):
            result.append(SheetInfo(name, problem="unreadable"))
            continue

        frame = table.df
        numbers = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column]) and frame[column].notna().any()]
        axis = table.time
        result.append(SheetInfo(
            name, rows=len(frame), number_columns=len(numbers), start=axis.start if axis else None, end=axis.end if axis else None,
            step_minutes=axis.step_minutes if axis else None, problem=None if axis else "no_time"))

    return result