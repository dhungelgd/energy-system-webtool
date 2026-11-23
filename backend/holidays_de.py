"""The public holidays of the German states, and the types of day and the seasons of the standard load profiles.

A load profile looks different on a workday, on a Saturday and on a Sunday or holiday, and in winter, in summer and in
between. The analysis of a profile (load_analysis.py) needs to know which a day is. The days are those of the BDEW
(Bundesverband der Energie- und Wasserwirtschaft) that the standard load profiles use:

- workday: Monday to Friday that is no holiday (December 24 and 31 count as a Saturday if they fall on a workday)
- Saturday: a Saturday that is no holiday (and the two days above)
- Sunday: a Sunday or a holiday (a holiday on a Saturday counts as a Sunday)

- winter: November 1 to March 20; summer: May 15 to September 14; transition: March 21 to May 14 and September 15 to
  October 31

The holidays are those that the law of the state names for the whole state. Not included: holidays that only some
municipalities have (Corpus Christi in parts of Saxony and Thuringia, the peace festival of Augsburg of August 8) and
the days that are no holiday but are free in many companies (the days before Christmas and New Year, carnival).
Mary's Assumption (August 15) is a holiday in the Saarland and in the municipalities of Bavaria with a mainly Catholic
population (most of them), so Bavaria has it by default and `catholic_municipality=False` takes it out. No NiceGUI code
in here, so any frontend can call it.
"""

from datetime import date, timedelta

STATES = ("BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV", "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH")
DEFAULT_STATE = "BY"
FIRST_YEAR, LAST_YEAR = 1995, 2100                       # the years that the rules are right for

WORKDAY, SATURDAY, SUNDAY = "workday", "saturday", "sunday"
DAY_TYPES = (WORKDAY, SATURDAY, SUNDAY)                  # SUNDAY is a Sunday or a holiday
WINTER, SUMMER, TRANSITION = "winter", "summer", "transition"
SEASONS = (WINTER, SUMMER, TRANSITION)

ALL_STATES = frozenset(STATES)
# the holidays of some states only; the others are in `holidays_of`
_EPIPHANY = frozenset({"BW", "BY", "ST"})
_CORPUS_CHRISTI = frozenset({"BW", "BY", "HE", "NW", "RP", "SL"})
_ALL_SAINTS = frozenset({"BW", "BY", "NW", "RP", "SL"})
_REFORMATION_EARLY = frozenset({"BB", "MV", "SN", "ST", "TH"})                   # since the reformation day was brought back
_REFORMATION_FROM_2018 = frozenset({"HB", "HH", "NI", "SH"})
_ONCE = {                                                                         # one-off holidays: (state, day) -> name
    "BE": {date(2020, 5, 8): "liberation_day", date(2025, 5, 8): "liberation_day", date(2028, 6, 17): "uprising_day"},
}


def easter(year):
    """The date of Easter Sunday (the Gregorian calendar, the algorithm of Gauss)."""

    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1

    return date(year, month, day)


def repentance_day(year):
    """The Day of Repentance and Prayer: the Wednesday before November 23."""

    day = date(year, 11, 22)

    return day - timedelta(days=(day.weekday() - 2) % 7)


def holidays_of(state, year, catholic_municipality=True):
    """The holidays of a state in a year as {day: name}. The names are keys for texts (holiday.<name>)."""

    if state not in ALL_STATES:
        raise ValueError(f"unknown state '{state}'")
    if not FIRST_YEAR <= year <= LAST_YEAR:
        raise ValueError(f"the holidays are known for the years {FIRST_YEAR} to {LAST_YEAR}, not for {year}")

    base = easter(year)
    found = {
        date(year, 1, 1): "new_year",
        base - timedelta(days=2): "good_friday",
        base + timedelta(days=1): "easter_monday",
        date(year, 5, 1): "labour_day",
        base + timedelta(days=39): "ascension",
        base + timedelta(days=50): "whit_monday",
        date(year, 10, 3): "german_unity",
        date(year, 12, 25): "christmas_1",
        date(year, 12, 26): "christmas_2",
    }

    if state in _EPIPHANY:
        found[date(year, 1, 6)] = "epiphany"
    if (state == "BE" and year >= 2019) or (state == "MV" and year >= 2023):
        found[date(year, 3, 8)] = "womens_day"
    if state == "BB":
        found[base] = "easter_sunday"
        found[base + timedelta(days=49)] = "whit_sunday"
    if state in _CORPUS_CHRISTI:
        found[base + timedelta(days=60)] = "corpus_christi"
    if state == "SL" or (state == "BY" and catholic_municipality):
        found[date(year, 8, 15)] = "assumption"
    if state == "TH" and year >= 2019:
        found[date(year, 9, 20)] = "world_childrens_day"
    if year == 2017 or state in _REFORMATION_EARLY or (state in _REFORMATION_FROM_2018 and year >= 2018):
        found[date(year, 10, 31)] = "reformation"
    if state in _ALL_SAINTS:
        found[date(year, 11, 1)] = "all_saints"
    if state == "SN":
        found[repentance_day(year)] = "repentance"

    for day, name in _ONCE.get(state, {}).items():
        if day.year == year:
            found[day] = name

    return found


def _type_of(day, holidays):
    if day in holidays or day.weekday() == 6:
        return SUNDAY
    if day.weekday() == 5 or (day.month, day.day) in ((12, 24), (12, 31)):
        return SATURDAY

    return WORKDAY


def day_type(day, state=DEFAULT_STATE, catholic_municipality=True):
    """The type of a day (a date): WORKDAY, SATURDAY or SUNDAY (a Sunday or a holiday)."""

    return _type_of(day, holidays_of(state, day.year, catholic_municipality))


def day_types(days, state=DEFAULT_STATE, catholic_municipality=True):
    """The type of each day of a list of dates, as {day: type}. The holidays of a year are worked out once."""

    holidays = {}
    found = {}
    for day in days:
        if day.year not in holidays:
            holidays[day.year] = holidays_of(state, day.year, catholic_municipality)
        found[day] = _type_of(day, holidays[day.year])

    return found


def season(day):
    """The season of a day (a date) as the standard load profiles have them."""

    month, number = day.month, day.day

    if month in (11, 12, 1, 2) or (month == 3 and number <= 20):
        return WINTER
    if month in (6, 7, 8) or (month == 5 and number >= 15) or (month == 9 and number <= 14):
        return SUMMER

    return TRANSITION