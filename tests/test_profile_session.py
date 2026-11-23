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