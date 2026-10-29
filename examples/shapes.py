"""Simple daily patterns for the synthetic example data (invented, not real data)."""

import math


def day_shape(hour):
    """A simple daily pattern between 0.4 and 1.0 (low at night)."""

    return round(0.7 + 0.3 * math.sin((hour - 9) / 24 * 2 * math.pi), 4)


def sun_shape(hour):
    """Sunshine: zero at night, a bell curve around noon."""

    value = math.sin((hour - 6) / 12 * math.pi)
    return round(max(value, 0.0), 4)