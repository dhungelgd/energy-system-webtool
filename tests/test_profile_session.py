"""A load profile file that is being prepared: what the visitor decided, and what is read with it."""

import pytest

from backend.load_profile import ProfileFileError
from backend.timeseries_import import TimeSeriesFileError
from frontend_nicegui.profile_session import ProfileSession
from tests.test_load_profile import codes, kw, render, starts, workshop


def session_of(text, name="Lastgang.csv"):
    return ProfileSession(text.encode("utf-8"), name)


def a_day(header="Zeitstempel;Leistung kW", first="2024-02-05 00:00", last="2024-02-06 23:45", **kwargs):
    index = starts(first, last)

    return render(index, kw(index), header=header, **kwargs), index


def test_a_new_session_holds_the_file_and_has_read_nothing():
    session = session_of("a;b\n")

    assert session.filename == "Lastgang.csv" and session.choices == {} and session.profile is None
    assert session.error is None and not session.failed and not session.ready


def test_a_file_that_says_everything_is_ready_after_one_reading_without_any_decision():
    text, index = a_day()
    session = session_of(text)

    session.read()

    assert session.ready and session.error is None and session.choices == {}
    assert len(session.profile.power_kw) == len(index)


def test_a_file_that_does_not_say_its_unit_is_read_again_with_the_decision():
    text, _ = a_day(header="Zeit;Wert")
    session = session_of(text)
    session.read()
    assert not session.ready and session.profile.needs == ["unit"]

    session.decide(unit="kWh")
    session.read()

    assert session.ready and session.profile.unit == "kWh" and session.choices == {"unit": "kWh"}


def test_a_decision_that_cannot_be_used_is_refused_and_changes_nothing():
    session = session_of(a_day()[0])
    session.decide(unit="kW")

    for bad in (0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            session.decide(energy_kwh=bad)
    with pytest.raises(ValueError):
        session.decide(stamp_at="middle")
    with pytest.raises(ValueError):
        session.decide(colour="red")

    assert session.choices == {"unit": "kW"}


def test_a_decision_can_be_taken_back_with_none():
    session = session_of(a_day()[0])
    session.decide(unit="kW", stamp_at="end")

    session.decide(stamp_at=None)

    assert session.choices == {"unit": "kW"}


def test_a_new_column_makes_the_unit_and_the_energy_of_the_old_one_invalid_but_the_start_or_end_stays():
    session = session_of(a_day()[0])
    session.decide(value_column="A", unit="kWh", energy_kwh=100.0, stamp_at="end")

    session.decide(value_column="B")
    assert session.choices == {"value_column": "B", "stamp_at": "end"}

    session.decide(value_column="B", unit="kW")                  # the same column: nothing is dropped
    session.decide(value_column="B")
    assert session.choices == {"value_column": "B", "unit": "kW", "stamp_at": "end"}

    session.decide(value_column="C", unit="W")                   # a new column with its own unit in the same answer
    assert session.choices == {"value_column": "C", "unit": "W", "stamp_at": "end"}


def test_only_what_was_decided_is_passed_on_so_that_a_doubt_of_the_reader_stays_open():
    text, _ = a_day(first="2024-02-05 08:00", last="2024-02-06 16:45")
    session = session_of(text)
    session.read()
    assert "stamp_assumed" in codes(session.profile)

    session.decide(unit="kW")                                    # an answer to another question
    session.read()
    assert "stamp_assumed" in codes(session.profile)

    session.decide(stamp_at="end")
    session.read()
    assert "stamp_assumed" not in codes(session.profile) and session.profile.stamp_at == "end"


def test_a_file_that_cannot_be_read_gives_its_error_and_no_profile():
    no_time = session_of("Name;kW\na;1\nb;2\nc;3\nd;4\n")
    empty = ProfileSession(b"", "leer.csv")

    no_time.read()
    empty.read()

    assert isinstance(no_time.error, ProfileFileError) and no_time.error.code == "no_time" and no_time.profile is None
    assert isinstance(empty.error, TimeSeriesFileError) and empty.profile is None and not empty.ready


def test_reading_again_forgets_an_error_and_a_failure():
    text, _ = a_day()
    session = session_of(text)
    session.error, session.failed = ProfileFileError("no_time"), True

    session.read()

    assert session.error is None and not session.failed and session.ready


def test_a_column_of_shares_asks_for_the_energy_and_is_ready_with_it():
    text, _ = workshop(hours=240)
    session = session_of(text, "workshop.csv")
    session.read()
    assert session.profile.needs == ["energy"] and not session.ready

    session.decide(energy_kwh=5000.0)
    session.read()

    assert session.ready and session.profile.energy_kwh() == pytest.approx(5000.0)


# ---------------------------------------------------------------------------
# the analysis
# ---------------------------------------------------------------------------

def two_years():
    index = starts("2022-01-01 00:00", "2023-12-31 23:00", freq="60min")

    return render(index, kw(index), step="60min", header="Zeit;Last kW"), index


def test_a_file_that_is_ready_is_analysed_with_the_choices_that_nothing_has_changed_yet():
    text, _ = a_day()
    session = session_of(text)

    session.read()

    assert session.analysis is not None and not session.analysis_failed
    assert session.analysis.options.state == "BY" and session.analysis.options.catholic_municipality is True
    assert session.analysis.options.year is None and session.analysis_choices == {"year": None}
    assert session.analysis.kpis.energy_kwh == pytest.approx(session.profile.energy_kwh())


def test_a_file_of_more_than_a_year_is_analysed_for_the_latest_whole_year_and_the_years_are_listed():
    text, _ = two_years()
    session = session_of(text)

    session.read()

    assert session.years() == [(2022, 365), (2023, 365)] and session.analysis.year == 2023
    assert session.analysis_choices["year"] == 2023 and session.analysis.kpis.values == 8760


def test_the_whole_profile_can_be_chosen_and_then_the_analysis_covers_all_of_it():
    text, _ = two_years()
    session = session_of(text)
    session.read()

    session.choose_analysis(year=None)
    session.analyse()

    assert session.analysis.year is None and session.analysis.kpis.values == 2 * 8760


def test_another_year_can_be_chosen_and_a_year_that_the_profile_does_not_have_is_refused_and_changes_nothing():
    text, _ = two_years()
    session = session_of(text)
    session.read()

    session.choose_analysis(year=2022)
    session.analyse()
    assert session.analysis.year == 2022 and session.analysis.kpis.start.year == 2022

    with pytest.raises(ValueError, match="no values in 2021"):
        session.choose_analysis(year=2021)
    assert session.analysis_choices["year"] == 2022


def test_the_state_of_the_holidays_changes_the_analysis():
    index = starts("2023-01-02 00:00", "2023-01-15 23:45")                       # the 6th of January 2023 is a Friday
    session = session_of(render(index, kw(index)))
    session.read()
    assert session.analysis.day_type_days["workday"] == 9                        # Bavaria has the 6th of January

    session.choose_analysis(state="NW")
    session.analyse()

    assert session.analysis.day_type_days["workday"] == 10 and session.analysis.options.state == "NW"


def test_mary_s_assumption_can_be_switched_off_for_a_municipality_that_is_mainly_protestant():
    index = starts("2023-08-14 00:00", "2023-08-20 23:45")
    session = session_of(render(index, kw(index)))
    session.read()
    assert session.analysis.day_type_days["workday"] == 4

    session.choose_analysis(catholic_municipality=False)
    session.analyse()

    assert session.analysis.day_type_days["workday"] == 5


def test_a_choice_that_cannot_be_used_is_refused_and_changes_nothing():
    session = session_of(a_day()[0])
    session.read()
    session.choose_analysis(state="NW")

    with pytest.raises(ValueError):
        session.choose_analysis(state="XX")
    with pytest.raises(ValueError, match="unknown choice"):
        session.choose_analysis(colour="red")

    assert session.analysis_choices["state"] == "NW"


def test_the_choices_of_the_analysis_stay_when_the_file_is_read_again_with_another_answer():
    text, _ = two_years()
    session = session_of(text)
    session.read()
    session.choose_analysis(state="SN", year=None)

    session.decide(stamp_at="start")
    session.read()

    assert session.analysis_choices["state"] == "SN" and session.analysis_choices["year"] is None
    assert session.analysis.options.state == "SN" and session.analysis.kpis.values == 2 * 8760


def test_a_file_that_is_not_ready_or_cannot_be_read_has_no_analysis_and_no_years():
    unsure = session_of(a_day(header="Zeit;Wert")[0])
    broken = session_of("Name;kW\na;1\nb;2\nc;3\nd;4\n")

    unsure.read()
    broken.read()

    assert unsure.analysis is None and unsure.years() == [] and not unsure.analysis_failed
    assert broken.analysis is None and broken.years() == []


def test_an_analysis_that_has_nothing_to_work_on_is_said_to_have_failed(monkeypatch):
    from frontend_nicegui import profile_session

    session = session_of(a_day()[0])

    def nothing(*args, **kwargs):
        raise ValueError("the profile has no values")

    monkeypatch.setattr(profile_session, "analyze", nothing)
    session.read()

    assert session.ready and session.analysis is None and session.analysis_failed is True


def test_analysing_again_forgets_a_failure():
    session = session_of(a_day()[0])
    session.read()
    session.analysis_failed, session.analysis = True, None

    session.analyse()

    assert session.analysis is not None and not session.analysis_failed