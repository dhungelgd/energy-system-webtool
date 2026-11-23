"""A load profile file that is being prepared: the file, what the visitor decided about it, and what was read.

The file is read again each time that the visitor gives an answer (the column, the unit, whether a time is the start or
the end of a step, the energy of a profile of shares), with all the answers given so far. Only what the visitor decided
is passed on as a decision: what the reader worked out by itself stays open to be worked out again, so that a warning
('it is not clear whether ...') is not silenced by a click that did not decide it. No NiceGUI code in here, so it is
easy to test.
"""

from backend.load_profile import ProfileFileError, ProfileOptions, read_load_profile
from backend.timeseries_import import TimeSeriesFileError

CHOICES = ("value_column", "unit", "stamp_at", "energy_kwh")


class ProfileSession:
    """One file of a load profile."""

    def __init__(self, content, filename):
        self.content = content
        self.filename = filename
        self.choices = {}               # what the visitor decided: some of CHOICES
        self.profile = None             # the LoadProfile that was read (ready or not)
        self.error = None               # a ProfileFileError or TimeSeriesFileError: why it cannot be read
        self.failed = False             # the reading broke in a way that was not foreseen (it is logged by the page)

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
        """Read the file with the decisions so far. This does the work (a year of quarter-hours takes a second or two),
        so a page calls it in a thread."""

        self.failed = False
        try:
            self.profile = read_load_profile(self.content, self.filename, ProfileOptions(**self.choices))
            self.error = None
        except (ProfileFileError, TimeSeriesFileError) as error:
            self.profile = None
            self.error = error