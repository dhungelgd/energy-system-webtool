import pytest

from backend.price_units import price_series_in_eur_per_kwh


def test_eur_per_kwh_is_unchanged():
    assert price_series_in_eur_per_kwh([0.3, 0.1], "€/kWh") == [0.3, 0.1]


def test_ct_per_kwh_is_converted():
    assert price_series_in_eur_per_kwh([30], "ct/kWh") == pytest.approx([0.30])


def test_eur_per_mwh_is_converted():
    assert price_series_in_eur_per_kwh([100], "€/MWh") == pytest.approx([0.10])


def test_unknown_unit_raises():
    with pytest.raises(ValueError, match="Unknown price unit"):
        price_series_in_eur_per_kwh([1], "dollar")