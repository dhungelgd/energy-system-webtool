"""The analysis of a load profile: what the numbers say about how a site uses electricity.

It takes the power in kW on a regular line of time steps (LoadProfile.power_kw of load_profile.py: local times, NaN where
a value is missing) and gives, for the period that is analysed:

- the key figures: the energy, the peak (the highest time step, with its time), the mean, two base loads, the hours of
  use and the load factor;
- the highest peaks, one for each day;
- the duration curve (how many hours the load is at least as high as a value);
- the typical days: the mean and the middle half of the values at each time of day, for each type of day (workday,
  Saturday, Sunday or holiday) and each season (winter, summer, transition), as the standard load profiles have them
  (holidays_de.py);
- the energy and the peak of each month, the mean of each weekday, and the load at each time of each day (the heat map);
- a few sentences that say what is striking, with the numbers in them.

Nothing is filled in or made up: a missing value is left out of the figures and stays empty in the heat map, and a figure
that needs a whole year (the hours of use) is not given for a shorter profile. Time steps finer than a quarter of an hour
are averaged to quarter-hours first (that is what the grid operator bills the peak on); a coarser one is kept, and the
peak is then lower than it would be. No NiceGUI code in here, so any frontend can call it.
"""

from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from backend.findings import Fixed, coded_text
from backend.holidays_de import DAY_TYPES, DEFAULT_STATE, SATURDAY, SEASONS, STATES, SUNDAY, WORKDAY, day_types, season
from backend.i18n import ENGLISH

BILLING_STEP = 15                # minutes: the time step that a peak is measured on
YEAR_DAYS = 330                  # a profile of at least this many days gives the figures of a year
FULL_YEAR_DAYS = 360             # a calendar year with at least this many days with values counts as a whole year
LONG_PROFILE_DAYS = 370          # a profile longer than this is more than a year: one year is chosen
PEAK_SHARE = 0.9                 # "near the peak": this share of the peak and more
BASE_PERCENTILE = 0.05           # the first base load: the load that is exceeded 95 % of the time
NIGHT_HOURS = 5                  # the second base load: the lowest value between 0:00 and 5:00 of each day, averaged
MIN_TYPICAL_DAYS = 3             # a typical day needs at least this many days
TOP_PEAKS = 5
DURATION_POINTS = 600            # how many points of the duration curve are kept
BASE_HIGH, BASE_LOW = 0.5, 0.2   # the base load as a share of the mean: high or low
WEEKEND_LOW, WEEKEND_SIMILAR = 0.6, 0.9
PEAK_WINDOW_MINUTES = 180        # the highest peaks of days are "at the same time" if they fall within this


@dataclass(frozen=True)
class AnalysisOptions:
    state: str = DEFAULT_STATE       # the state whose holidays count
    catholic_municipality: bool = True
    year: int = None                 # a calendar year of the profile; None: the whole profile

    def __post_init__(self):
        if self.state not in STATES:
            raise ValueError(f"unknown state '{self.state}'")


class AnalysisHint(tuple):
    """A sentence about what is striking: (level, English sentence) with a `code` and `params` for wording it in another
    language (`analysis_text`)."""

    def __new__(cls, code, **params):
        item = super().__new__(cls, ("info", coded_text("analysis.hint", code, params, ENGLISH)))
        item.code = code
        item.params = params
        return item

    def __getnewargs_ex__(self):
        return (self.code,), self.params

    @property
    def text(self):
        return self[1]


def analysis_text(hint, tr):
    """The sentence of a hint in the language of `tr`."""

    return coded_text("analysis.hint", hint.code, hint.params, tr)


@dataclass(frozen=True)
class Kpis:
    start: pd.Timestamp              # the start of the first time step
    end: pd.Timestamp                # the end of the last time step
    days: float                      # the length of the period
    values: int                      # the time steps with a value
    missing_share: float             # 0 to 1
    energy_kwh: float                # of the values that there are
    energy_estimate_kwh: float       # with the gaps filled by the mean: what the period used, about
    yearly: bool                     # the period is long enough to give the figures of a year
    mean_kw: float
    min_kw: float
    peak_kw: float
    peak_time: pd.Timestamp
    base_percentile_kw: float        # the load that is exceeded 95 % of the time
    base_night_kw: float             # the mean of the lowest values of the nights (None if there is no night in the data)
    utilization_hours: float         # energy / peak: None unless `yearly`
    load_factor: float               # mean / peak
    hours_near_peak: float           # the hours with PEAK_SHARE of the peak or more
    days_near_peak: int              # the days on which that happens


@dataclass(frozen=True)
class Peak:
    time: pd.Timestamp
    kw: float
    day_type: str
    season: str


@dataclass(frozen=True)
class DurationCurve:
    hours: np.ndarray                # for a point: how many hours the load is at least `kw`
    kw: np.ndarray
    total_hours: float               # the hours that have a value


@dataclass(frozen=True)
class TypicalDay:
    season: str                      # None: all seasons
    day_type: str
    days: int
    slots: list                      # the times of day, in minutes after midnight
    mean: list
    p25: list
    p75: list


@dataclass(frozen=True)
class Month:
    year: int
    month: int
    energy_kwh: float
    peak_kw: float
    days: int                        # the days with at least one value
    missing_share: float


@dataclass(frozen=True)
class Heatmap:
    dates: list                      # one row for each day
    slots: list                      # one column for each time of day, in minutes after midnight
    values: np.ndarray               # kW, NaN where there is no value; days x slots


@dataclass
class LoadAnalysis:
    options: AnalysisOptions
    year: int                        # the calendar year that was analysed, or None for the whole profile
    years: list                      # the calendar years that the profile has, as (year, days with a value)
    step_minutes: int                # the time step that the analysis worked on
    kpis: Kpis
    peaks: list
    duration: DurationCurve
    typical_days: list
    months: list
    weekdays: list                   # the mean kW of Monday to Sunday (None if the profile has no such day)
    heatmap: Heatmap
    hints: list
    day_type_days: dict = field(default_factory=dict)       # the days of each type in the period


# ---------------------------------------------------------------------------
# the period
# ---------------------------------------------------------------------------

def years_of(power_kw):
    """The calendar years that the profile has, as [(year, days that have at least one value)]."""

    present = power_kw.dropna()
    local = present.index.tz_localize(None)
    days = pd.Series(local.date).groupby([d.year for d in local.date]).nunique()

    return [(int(year), int(count)) for year, count in days.items()]


def default_year(power_kw, step_minutes):
    """The calendar year to analyse by default: for a profile of more than a year the latest whole year, else None (the
    whole profile)."""

    if len(power_kw) * step_minutes / 1440 <= LONG_PROFILE_DAYS:
        return None

    whole = [year for year, days in years_of(power_kw) if days >= FULL_YEAR_DAYS]

    return max(whole) if whole else None


def _to_quarter_hours(power_kw, step_minutes):
    if step_minutes >= BILLING_STEP:
        return power_kw, step_minutes

    return power_kw.resample(f"{BILLING_STEP}min").mean(), BILLING_STEP


# ---------------------------------------------------------------------------
# the parts
# ---------------------------------------------------------------------------

def _frame(series, options):
    """The time steps as a table: when (with its zone), the local time, the power, and what kind of day it is."""

    local = series.index.tz_localize(None)
    frame = pd.DataFrame({"when": series.index, "local": local, "kw": series.to_numpy()})
    frame["date"] = local.date
    frame["slot"] = (local.hour * 60 + local.minute).to_numpy()
    frame["weekday"] = local.dayofweek.to_numpy()
    days = sorted(set(frame["date"]))
    types = day_types(days, options.state, options.catholic_municipality)
    frame["day_type"] = frame["date"].map(types)
    frame["season"] = frame["date"].map({day: season(day) for day in days})

    return frame


def _kpis(series, frame, present, step):
    hours = len(series) * step / 60
    energy = float(present["kw"].sum() * step / 60)
    mean = float(present["kw"].mean())
    peak = float(present["kw"].max())
    peak_time = present.loc[present["kw"].idxmax(), "when"]
    days = hours / 24
    yearly = days >= YEAR_DAYS

    night = present[present["slot"] < NIGHT_HOURS * 60].groupby("date")["kw"].min()
    near = present[present["kw"] >= PEAK_SHARE * peak]

    return Kpis(
        start=series.index[0], end=series.index[-1] + pd.Timedelta(minutes=step), days=days, values=len(present),
        missing_share=float(series.isna().mean()), energy_kwh=energy, energy_estimate_kwh=mean * hours, yearly=yearly,
        mean_kw=mean, min_kw=float(present["kw"].min()), peak_kw=peak, peak_time=peak_time,
        base_percentile_kw=float(present["kw"].quantile(BASE_PERCENTILE)),
        base_night_kw=float(night.mean()) if len(night) else None,
        utilization_hours=mean * hours / peak if yearly and peak > 0 else None,
        load_factor=mean / peak if peak > 0 else None,
        hours_near_peak=len(near) * step / 60, days_near_peak=int(near["date"].nunique()),
    )


def _peaks(present):
    """The highest value of each day, the highest of those first (the earlier day first if they are equal)."""

    best = present.loc[present.groupby("date")["kw"].idxmax()].sort_values(["kw", "when"], ascending=[False, True])

    return [Peak(row.when, float(row.kw), row.day_type, row.season) for row in best.head(TOP_PEAKS).itertuples()]


def _duration(present, step):
    values = np.sort(present["kw"].to_numpy())[::-1]
    count = len(values)
    positions = np.unique(np.linspace(0, count - 1, num=min(DURATION_POINTS, count)).astype(int))

    return DurationCurve(
        hours=(positions + 1) * step / 60, kw=values[positions], total_hours=count * step / 60)


def _typical_days(present):
    days = present.groupby(["season", "day_type"])["date"].nunique()
    days_all = present.groupby("day_type")["date"].nunique()
    result = []

    def quantile(share):
        return lambda values: values.quantile(share)

    def build(season_key, kind, count, table):
        table = table.sort_index()

        return TypicalDay(season_key, kind, int(count), [int(slot) for slot in table.index], table["mean"].tolist(),
                          table["p25"].tolist(), table["p75"].tolist())

    by_type = present.groupby(["day_type", "slot"])["kw"].agg(mean="mean", p25=quantile(0.25), p75=quantile(0.75))
    for kind in DAY_TYPES:
        if days_all.get(kind, 0) >= MIN_TYPICAL_DAYS:
            result.append(build(None, kind, days_all[kind], by_type.loc[kind]))

    by_season = present.groupby(["season", "day_type", "slot"])["kw"].agg(mean="mean", p25=quantile(0.25), p75=quantile(0.75))
    for name in SEASONS:
        for kind in DAY_TYPES:
            if days.get((name, kind), 0) >= MIN_TYPICAL_DAYS:
                result.append(build(name, kind, days[(name, kind)], by_season.loc[(name, kind)]))

    return result


def _months(frame, present, step):
    frame = frame.assign(month=[(day.year, day.month) for day in frame["date"]])
    present = present.assign(month=[(day.year, day.month) for day in present["date"]])
    rows = []

    for key, group in present.groupby("month"):
        everything = frame[frame["month"] == key]
        rows.append(Month(
            year=key[0], month=key[1], energy_kwh=float(group["kw"].sum() * step / 60), peak_kw=float(group["kw"].max()),
            days=int(group["date"].nunique()), missing_share=float(everything["kw"].isna().mean())))

    return rows


def _heatmap(frame, step):
    first, last = min(frame["date"]), max(frame["date"])
    dates = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    slots = list(range(0, 1440, step))
    table = frame.pivot_table(index="date", columns="slot", values="kw", aggfunc="mean", dropna=False)
    values = table.reindex(index=dates, columns=slots).to_numpy(dtype=float)

    return Heatmap(dates, slots, values)


def _clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hints(kpis, peaks, present):
    hints = []

    if kpis.peak_kw > 0:
        hints.append(AnalysisHint(
            "peak_rare", limit=Fixed(PEAK_SHARE * kpis.peak_kw, 0), hours=Fixed(kpis.hours_near_peak, 1), days=kpis.days_near_peak))

    if kpis.mean_kw > 0:
        share = kpis.base_percentile_kw / kpis.mean_kw
        if share >= BASE_HIGH:
            hints.append(AnalysisHint("base_high", share=Fixed(100 * share, 0)))
        elif share <= BASE_LOW:
            hints.append(AnalysisHint("base_low", share=Fixed(100 * share, 0)))

        working = present[present["day_type"] == WORKDAY]
        free = present[present["day_type"].isin([SATURDAY, SUNDAY])]
        if working["date"].nunique() >= MIN_TYPICAL_DAYS and free["date"].nunique() >= MIN_TYPICAL_DAYS and working["kw"].mean() > 0:
            ratio = free["kw"].mean() / working["kw"].mean()
            if ratio < WEEKEND_LOW:
                hints.append(AnalysisHint("weekend_low", share=Fixed(100 * ratio, 0)))
            elif ratio >= WEEKEND_SIMILAR:
                hints.append(AnalysisHint("weekend_similar", share=Fixed(100 * ratio, 0)))

    if len(peaks) >= 3:
        minutes = [peak.time.hour * 60 + peak.time.minute for peak in peaks]
        if max(minutes) - min(minutes) <= PEAK_WINDOW_MINUTES:
            hints.append(AnalysisHint("peak_window", start=_clock(min(minutes)), end=_clock(max(minutes))))

    return hints


# ---------------------------------------------------------------------------
# the analysis
# ---------------------------------------------------------------------------

def analyze(power_kw, step_minutes, options=None):
    """Analyse a load profile.

    power_kw      kW at the start of each time step, regular, in local times, NaN where a value is missing
    step_minutes  the length of a time step
    options       AnalysisOptions (the state of the holidays, the year)

    Raises ValueError if the year that is asked for is not in the profile or there is no value at all.
    """

    options = options or AnalysisOptions()
    years = years_of(power_kw)
    series, step = _to_quarter_hours(power_kw, step_minutes)

    if options.year is not None:
        series = series[series.index.year == options.year]
        if len(series) == 0:
            raise ValueError(f"the profile has no values in {options.year}")
    if series.notna().sum() == 0:
        raise ValueError("the profile has no values")

    frame = _frame(series, options)
    present = frame[frame["kw"].notna()]
    kpis = _kpis(series, frame, present, step)
    peaks = _peaks(present)
    types = present.groupby("day_type")["date"].nunique()
    weekdays = present.groupby("weekday")["kw"].mean()

    return LoadAnalysis(
        options=options, year=options.year, years=years, step_minutes=step, kpis=kpis, peaks=peaks,
        duration=_duration(present, step), typical_days=_typical_days(present), months=_months(frame, present, step),
        weekdays=[float(weekdays[number]) if number in weekdays.index else None for number in range(7)],
        heatmap=_heatmap(frame, step), hints=_hints(kpis, peaks, present),
        day_type_days={kind: int(types.get(kind, 0)) for kind in DAY_TYPES},
    )