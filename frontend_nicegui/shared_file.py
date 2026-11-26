"""One file for the whole session: the file that the page of the load profile holds is also the file of the optimization.

A visitor who loads a file with many profiles (demand, PV, COP ...) on the page of the load profile should not have to load it
again in the optimization. This makes the session of the file with all the series (series_bulk.py) from the session of the load
profile: the same bytes, read in the same way (the sheet and the settings of the import that the visitor chose), with the
column that was analysed as the preferred column for the electricity demand, and with the answer for the hours of a time step
shorter than an hour that follows from the unit of that column (kW: the mean of the hours, kWh: the sum). The visitor sees all
of this in the card of the optimization and can change it there. No NiceGUI code in here, so it is easy to test.
"""

from backend.load_profile import UNITS
from backend.timeseries_import import ImportOptions
from frontend_nicegui.series_bulk import BulkSession

OPTION_NAMES = ("encoding", "delimiter", "decimal", "header_line", "first_data_line", "sheet")


def bulk_from_profile(profile_session):
    """The BulkSession for the file of a ProfileSession."""

    bulk = BulkSession(profile_session.content, profile_session.filename)
    options = profile_session.file.options
    if options != ImportOptions():
        bulk.master.change(**{name: getattr(options, name) for name in OPTION_NAMES})      # the lines are given, so they stay

    if profile_session.ready:
        profile = profile_session.profile
        if profile.value_column is not None:
            bulk.preferred["demand"] = profile.value_column
        if profile.unit in UNITS:
            bulk.master.aggregate = "sum" if UNITS[profile.unit][1] else "mean"

    return bulk


def is_the_file_of(bulk, profile_session):
    """True if the file of the optimization is the file that the load profile page holds."""

    return bulk is not None and profile_session is not None and bulk.master.content is profile_session.content