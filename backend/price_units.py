# Units in which an electricity price time series can be uploaded.
# Factor = value in EUR/kWh for 1 unit of the uploaded value.
# (Spot market data is often given in EUR/MWh, German tariffs in ct/kWh.)

PRICE_UNIT_FACTORS = {
    "€/kWh": 1.0,
    "ct/kWh": 0.01,
    "€/MWh": 0.001,
}

DEFAULT_PRICE_UNIT = "€/kWh"


def price_series_in_eur_per_kwh(values, unit):
    """Convert an uploaded price series to EUR/kWh."""

    if unit not in PRICE_UNIT_FACTORS:
        raise ValueError(
            f"Unknown price unit '{unit}'. Allowed: {', '.join(PRICE_UNIT_FACTORS)}"
        )

    factor = PRICE_UNIT_FACTORS[unit]
    return [float(v) * factor for v in values]