"""The holidays of the German states, the types of day and the seasons of the standard load profiles."""

from datetime import date, timedelta

import pytest

from backend import holidays_de
from backend.holidays_de import (
    ALL_STATES,
    DAY_TYPES,
    SATURDAY,
    SEASONS,
    STATES,
    SUMMER,
    SUNDAY,
    TRANSITION,
    WINTER,
    WORKDAY,
    day_type,
    day_types,
    easter,
    holidays_of,
    repentance_day,
    season,
)


def days_of(state, year, **kwargs):
    return sorted(holidays_of(state, year, **kwargs))


# ---------------------------------------------------------------------------
# Easter and the days that follow it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("year, expected", [
    (2000, date(2000, 4, 23)), (2019, date(2019, 4, 21)), (2021, date(2021, 4, 4)), (2023, date(2023, 4, 9)),
    (2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28)),
    (2038, date(2038, 4, 25)), (2100, date(2100, 3, 28)),
])
def test_easter_is_found_for_known_years(year, expected):
    assert easter(year) == expected and easter(year).weekday() == 6


def test_the_days_around_easter_follow_from_it():
    found = holidays_of("BW", 2026)

    assert found[date(2026, 4, 3)] == "good_friday" and found[date(2026, 4, 6)] == "easter_monday"
    assert found[date(2026, 5, 14)] == "ascension" and found[date(2026, 5, 25)] == "whit_monday"
    assert found[date(2026, 6, 4)] == "corpus_christi"
    assert all(day.weekday() == (4 if name == "good_friday" else 0 if name in ("easter_monday", "whit_monday") else 3 if name in ("ascension", "corpus_christi") else day.weekday())
               for day, name in found.items())


@pytest.mark.parametrize("year, expected", [(2023, date(2023, 11, 22)), (2024, date(2024, 11, 20)), (2025, date(2025, 11, 19)),
                                            (2026, date(2026, 11, 18)), (2027, date(2027, 11, 17))])
def test_the_day_of_repentance_is_the_wednesday_before_november_23(year, expected):
    assert repentance_day(year) == expected and expected.weekday() == 2 and expected < date(year, 11, 23)


@pytest.mark.parametrize("year", [2022, 2033])
def test_when_the_23rd_of_november_is_a_wednesday_the_day_of_repentance_is_the_wednesday_before_it(year):
    assert date(year, 11, 23).weekday() == 2

    assert repentance_day(year) == date(year, 11, 16)


# ---------------------------------------------------------------------------
# the states: the number of holidays in 2026 as the sources count them (also those on a weekend)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("state, count", [
    ("BE", 10), ("HE", 10), ("MV", 11), ("TH", 11), ("SH", 10), ("BY", 13), ("NW", 11), ("BW", 12), ("SL", 12), ("HH", 10),
    ("HB", 10), ("NI", 10), ("SN", 11), ("RP", 11), ("ST", 11),
])
def test_the_number_of_holidays_in_2026_is_that_of_the_sources(state, count):
    assert len(holidays_of(state, 2026)) == count


def test_brandenburg_has_easter_and_whit_sunday_too_which_are_sundays_anyway():
    found = holidays_of("BB", 2026)

    assert found[date(2026, 4, 5)] == "easter_sunday" and found[date(2026, 5, 24)] == "whit_sunday"
    assert len(found) == 12 and len([d for d in found if d.weekday() != 6]) == 10


def test_every_state_has_the_nine_holidays_of_the_whole_country():
    for state in STATES:
        names = set(holidays_of(state, 2026).values())
        assert {"new_year", "good_friday", "easter_monday", "labour_day", "ascension", "whit_monday", "german_unity",
                "christmas_1", "christmas_2"} <= names


def test_the_states_are_sixteen_and_the_default_is_bavaria():
    assert len(STATES) == 16 == len(ALL_STATES) and holidays_de.DEFAULT_STATE == "BY" and "BY" in STATES


@pytest.mark.parametrize("name, states", [
    ("epiphany", {"BW", "BY", "ST"}),
    ("corpus_christi", {"BW", "BY", "HE", "NW", "RP", "SL"}),
    ("all_saints", {"BW", "BY", "NW", "RP", "SL"}),
    ("reformation", {"BB", "HB", "HH", "MV", "NI", "SN", "ST", "SH", "TH"}),
    ("womens_day", {"BE", "MV"}),
    ("world_childrens_day", {"TH"}),
    ("repentance", {"SN"}),
    ("assumption", {"BY", "SL"}),
])
def test_a_holiday_of_some_states_is_in_exactly_those_states(name, states):
    assert {state for state in STATES if name in holidays_of(state, 2026).values()} == states


# ---------------------------------------------------------------------------
# what changed over the years
# ---------------------------------------------------------------------------

def test_the_womens_day_came_to_berlin_in_2019_and_to_mecklenburg_vorpommern_in_2023():
    assert date(2018, 3, 8) not in holidays_of("BE", 2018) and date(2019, 3, 8) in holidays_of("BE", 2019)
    assert date(2022, 3, 8) not in holidays_of("MV", 2022) and date(2023, 3, 8) in holidays_of("MV", 2023)


def test_the_reformation_day_came_to_four_northern_states_in_2018_and_was_free_everywhere_in_2017():
    for state in ("HB", "HH", "NI", "SH"):
        assert date(2016, 10, 31) not in holidays_of(state, 2016) and date(2018, 10, 31) in holidays_of(state, 2018)
    assert all(date(2017, 10, 31) in holidays_of(state, 2017) for state in STATES)
    assert date(2017, 10, 31) not in holidays_of("BY", 2018) and date(2018, 10, 31) not in holidays_of("BY", 2018)


def test_the_world_childrens_day_came_to_thuringia_in_2019():
    assert date(2018, 9, 20) not in holidays_of("TH", 2018) and date(2019, 9, 20) in holidays_of("TH", 2019)


def test_berlin_had_the_8th_of_may_in_2020_and_2025_only_and_will_have_the_17th_of_june_in_2028():
    assert holidays_of("BE", 2020)[date(2020, 5, 8)] == "liberation_day" and holidays_of("BE", 2025)[date(2025, 5, 8)] == "liberation_day"
    assert date(2026, 5, 8) not in holidays_of("BE", 2026) and date(2024, 5, 8) not in holidays_of("BE", 2024)
    assert holidays_of("BE", 2028)[date(2028, 6, 17)] == "uprising_day"
    assert date(2025, 5, 8) not in holidays_of("BY", 2025)


def test_the_assumption_in_bavaria_can_be_left_out_for_a_municipality_that_is_mainly_protestant():
    assert date(2026, 8, 15) in holidays_of("BY", 2026) and date(2026, 8, 15) not in holidays_of("BY", 2026, catholic_municipality=False)
    assert date(2026, 8, 15) in holidays_of("SL", 2026, catholic_municipality=False)             # it counts for Bavaria only


def test_a_state_or_a_year_that_is_not_known_is_refused():
    with pytest.raises(ValueError, match="unknown state 'XX'"):
        holidays_of("XX", 2026)
    with pytest.raises(ValueError):
        holidays_of("BY", 1900)
    with pytest.raises(ValueError):
        holidays_of("BY", 2101)


# ---------------------------------------------------------------------------
# the types of day
# ---------------------------------------------------------------------------

def test_a_year_in_bavaria_has_248_workdays_52_saturdays_and_65_sundays_and_holidays():
    # 2023 begins and ends on a Sunday (53 Sundays); 12 holidays are on a weekday, none on a Saturday
    types = day_types([date(2023, 1, 1) + timedelta(days=i) for i in range(365)], "BY")

    counts = {kind: sum(1 for value in types.values() if value == kind) for kind in DAY_TYPES}

    assert counts == {WORKDAY: 248, SATURDAY: 52, SUNDAY: 65}


def test_the_holidays_of_a_state_are_sundays_for_the_types_of_day():
    assert day_type(date(2023, 1, 6), "BY") == SUNDAY and day_type(date(2023, 1, 6), "NW") == WORKDAY
    assert day_type(date(2023, 11, 1), "NW") == SUNDAY and day_type(date(2023, 11, 1), "NI") == WORKDAY
    assert day_type(date(2023, 11, 22), "SN") == SUNDAY and day_type(date(2023, 11, 22), "BY") == WORKDAY
    assert day_type(date(2023, 3, 8), "MV") == SUNDAY and day_type(date(2022, 3, 8), "MV") == WORKDAY


def test_a_holiday_on_a_saturday_is_a_sunday():
    assert date(2026, 10, 3).weekday() == 5 and day_type(date(2026, 10, 3), "BY") == SUNDAY


def test_the_24th_and_the_31st_of_december_are_saturdays_if_they_fall_on_a_workday():
    assert day_type(date(2024, 12, 24), "BY") == SATURDAY and day_type(date(2024, 12, 31), "BY") == SATURDAY      # Tuesdays
    assert day_type(date(2025, 12, 24), "BY") == SATURDAY                                                         # a Wednesday
    assert day_type(date(2023, 12, 24), "BY") == SUNDAY and day_type(date(2023, 12, 31), "BY") == SUNDAY          # Sundays
    assert day_type(date(2022, 12, 24), "BY") == SATURDAY and day_type(date(2022, 12, 31), "BY") == SATURDAY      # Saturdays
    assert day_type(date(2024, 12, 25), "BY") == SUNDAY and day_type(date(2024, 12, 23), "BY") == WORKDAY


@pytest.mark.parametrize("day, expected", [
    (date(2023, 2, 6), WORKDAY), (date(2023, 2, 11), SATURDAY), (date(2023, 2, 12), SUNDAY), (date(2023, 4, 7), SUNDAY),
    (date(2023, 4, 10), SUNDAY), (date(2023, 4, 11), WORKDAY),
])
def test_the_type_of_a_day_in_bavaria(day, expected):
    assert day_type(day, "BY") == expected


def test_the_types_of_a_list_of_days_are_those_of_each_day_and_the_holidays_of_a_year_are_worked_out_once(monkeypatch):
    calls = []
    original = holidays_de.holidays_of
    monkeypatch.setattr(holidays_de, "holidays_of", lambda *args, **kwargs: calls.append(args) or original(*args, **kwargs))
    days = [date(2023, 12, 20) + timedelta(days=i) for i in range(30)]               # two years

    types = day_types(days, "BY")
    worked_out = len(calls)

    assert worked_out == 2                                                            # once for 2023 and once for 2024
    assert types == {day: day_type(day, "BY") for day in days}


# ---------------------------------------------------------------------------
# the seasons
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("day, expected", [
    (date(2023, 1, 1), WINTER), (date(2023, 3, 20), WINTER), (date(2023, 3, 21), TRANSITION), (date(2023, 5, 14), TRANSITION),
    (date(2023, 5, 15), SUMMER), (date(2023, 7, 1), SUMMER), (date(2023, 9, 14), SUMMER), (date(2023, 9, 15), TRANSITION),
    (date(2023, 10, 31), TRANSITION), (date(2023, 11, 1), WINTER), (date(2023, 12, 31), WINTER),
])
def test_the_seasons_begin_and_end_on_the_days_of_the_standard_load_profiles(day, expected):
    assert season(day) == expected


def test_a_year_has_140_winter_days_123_summer_days_and_102_days_in_between():
    days = [date(2023, 1, 1) + timedelta(days=i) for i in range(365)]

    counts = {kind: sum(1 for day in days if season(day) == kind) for kind in SEASONS}

    assert counts == {WINTER: 140, SUMMER: 123, TRANSITION: 102} and sum(counts.values()) == 365