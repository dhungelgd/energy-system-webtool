"""Tests for the time-series helper used by the model."""

import pytest

from backend.oemof_components import align_timeseries
from tests.helpers import timeindex


def test_exact_length_is_kept():
    result = align_timeseries([1, 2, 3], timeindex(3), "x")
    assert list(result) == [1.0, 2.0, 3.0]
    assert list(result.index) == list(timeindex(3))


def test_longer_series_is_cut():
    result = align_timeseries([1, 2, 3, 4, 5], timeindex(3), "x")
    assert list(result) == [1.0, 2.0, 3.0]


def test_shorter_series_raises_with_name():
    with pytest.raises(ValueError, match=r"\[PV\].*2 values.*needs 3"):
        align_timeseries([1, 2], timeindex(3), "PV")


def test_nan_raises():
    with pytest.raises(ValueError, match="empty values"):
        align_timeseries([1, float("nan"), 3], timeindex(3), "x")


def test_text_raises():
    with pytest.raises(ValueError, match="non-numeric"):
        align_timeseries([1, "abc", 3], timeindex(3), "x")


def test_numbers_given_as_text_are_accepted():
    result = align_timeseries(["1.5", "2"], timeindex(2), "x")
    assert list(result) == [1.5, 2.0]