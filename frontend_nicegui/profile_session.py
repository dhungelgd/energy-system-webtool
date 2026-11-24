"""A load profile file that is being prepared: the file, what the visitor decided about it, and what was read.

The file is read again each time that the visitor gives an answer (the column, the unit, whether a time is the start or
the end of a step, the energy of a profile of shares), with all the answers given so far. Only what the visitor decided
is passed on as a decision: what the reader worked out by itself stays open to be worked out again, so that a warning
('it is not clear whether ...') is not silenced by a click that did not decide it. No NiceGUI code in here, so it is
easy to test.
"""

from backend.holidays_de import DEFAULT_STATE
from backend.load_analysis import AnalysisOptions, analyze, default_year, years_of
from backend.load_profile import ProfileFileError, ProfileOptions, read_load_profile
from backend.timeseries_import import TimeSeriesFileError

CHOICES = ("value_column", "unit", "stamp_at", "energy_kwh")
ANALYSIS_CHOICES = ("state", "catholic_municipality", "year")      # what the visitor chooses for the analysis


class ProfileSession:
    """One file of a load profile."""

    def __init__(self, content, filename):
        self.content = content
        self.filename = filename
        self.choices = {}               # what the visitor decided: some of CHOICES
        self.profile = None             # the LoadProfile that was read (ready or not)
        self.error = None               # a ProfileFileError or TimeSeriesFileError: why it cannot be read
        self.failed = False             # the reading broke in a way that was not foreseen (it is logged by the page)
        self.analysis = None            # the LoadAnalysis of the profile (None while there is none)
        self.analysis_failed = False    # the profile is ready but cannot be analysed (no value in the chosen period)
        self.analysis_choices = {}      # state, catholic_municipality and year (the year is there once the profile is ready)

    @property
    def ready(self):
        """True if there is a profile with its power: nothing more to ask."""

        return self.profile is not None and self.profile.ready

    def decide(self, **choices):
        """Give answers. A value of None takes a decision back. A new column makes the unit and the energy that were
        decided for the old one invalid. A ValueError (an energy that is not above zero) changes nothing."""

        unknown = set(choices) - set(CHOICES)
        if unknown:
            raise ValueError(f"unknown choice: {', '.join(sorted(unknown))}")

        new = dict(self.choices)
        if "value_column" in choices and choices["value_column"] != new.get("value_column"):
            for name in ("unit", "energy_kwh"):
                new.pop(name, None)
        for name, value in choices.items():
            if value is None:
                new.pop(name, None)
            else:
                new[name] = value

        ProfileOptions(**new)               # refuses what cannot be used, before anything is kept
        self.choices = new

    def read(self):
        """Read the file with the decisions so far, and analyse the profile if it is ready. This does the work (a year of
        quarter-hours takes a second or two), so a page calls it in a thread."""

        self.failed = False
        try:
            self.profile = read_load_profile(self.content, self.filename, ProfileOptions(**self.choices))
            self.error = None
        except (ProfileFileError, TimeSeriesFileError) as error:
            self.profile = None
            self.error = error

        self.analyse()

    # ----- the analysis ------------------------------------------------------

    def analysis_options(self):
        """The options of the analysis: the choices of the visitor, and for what was not chosen the state of Bavaria with
        its Assumption and the year that is analysed by default."""

        choices = self.analysis_choices

        return AnalysisOptions(
            state=choices.get("state", DEFAULT_STATE), catholic_municipality=choices.get("catholic_municipality", True),
            year=choices.get("year"))

    def years(self):
        """The calendar years of the profile as [(year, days with a value)] (empty if the profile is not ready)."""

        return years_of(self.profile.power_kw) if self.ready else []

    def choose_analysis(self, **choices):
        """Choose the state of the holidays, whether Mary's Assumption counts (in Bavaria) and the calendar year (None: the
        whole profile). A ValueError (an unknown state, a year that the profile does not have) changes nothing."""

        unknown = set(choices) - set(ANALYSIS_CHOICES)
        if unknown:
            raise ValueError(f"unknown choice: {', '.join(sorted(unknown))}")

        new = {**self.analysis_choices, **choices}
        AnalysisOptions(state=new.get("state", DEFAULT_STATE))
        if new.get("year") is not None and new["year"] not in [year for year, _ in self.years()]:
            raise ValueError(f"the profile has no values in {new['year']}")

        self.analysis_choices = new

    def analyse(self):
        """Analyse the profile that was read, for the choices made. Without a profile that is ready there is no analysis."""

        self.analysis, self.analysis_failed = None, False
        if not self.ready:
            return

        power, step = self.profile.power_kw, self.profile.step_minutes
        years = [year for year, _ in years_of(power)]
        if "year" not in self.analysis_choices or self.analysis_choices["year"] not in (None, *years):
            self.analysis_choices["year"] = default_year(power, step)       # the latest whole year if the profile is longer

        try:
            self.analysis = analyze(power, step, self.analysis_options())
        except ValueError:
            self.analysis_failed = True