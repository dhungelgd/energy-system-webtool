"""Creates the example scenarios in examples/scenarios (synthetic data only).

Run it from the repository folder:

    python -m examples.make_examples

The example files are checked by the tests, so they stay in line with the code.
They contain invented numbers only. Never put real data of a company here: a
scenario file contains the time series that were used.
"""

import math
from pathlib import Path

from backend.scenario import Scenario

FOLDER = Path(__file__).resolve().parent / "scenarios"


def day_shape(hour):
    """A simple daily pattern between 0.4 and 1.0 (low at night)."""

    return round(0.7 + 0.3 * math.sin((hour - 9) / 24 * 2 * math.pi), 4)


def sun_shape(hour):
    """Sunshine: zero at night, a bell curve around noon."""

    value = math.sin((hour - 6) / 12 * math.pi)
    return round(max(value, 0.0), 4)


def grid_only_24h():
    """10 kW from the grid for one day at 0.30 EUR/kWh: costs 72 EUR."""

    return Scenario(
        name="Grid only, 24 hours",
        components=["demand", "grid"],
        settings={
            "demand": {"electricity_demand": "demand", "scaling_factor": 10.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
        },
        time={"steps": 24},
        series={"electricity_demand": [1.0] * 24},
    )


def pv_battery_week():
    """A week in June with a fixed PV plant (30 kW) and a fixed battery (40 kWh).

    Fixed sizes on purpose: in invest mode the full-year investment cost would
    be compared with the energy costs of one week only, and nothing would be
    built. Invest mode needs a full year of data.
    """

    hours = range(168)

    return Scenario(
        name="PV and battery, one week in June",
        components=["demand", "grid", "grid_feedin", "pv", "battery"],
        settings={
            "demand": {"electricity_demand": "demand", "scaling_factor": 20.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
            "grid_feedin": {"feedin_tariff": 0.078},
            "pv": {"mode": "fixed", "capacity": 30.0, "pv": "pv"},
            "battery": {
                "mode": "fixed", "capacity": 40.0,
                "efficiency_charge": 0.95, "efficiency_discharge": 0.95,
                "loss_rate": 0.001, "c_rate": 0.5,
            },
        },
        time={"start": "2021-06-01T00:00:00", "steps": 168},
        series={
            "electricity_demand": [day_shape(h % 24) for h in hours],
            "pv": [round(sun_shape(h % 24) * (0.6 + 0.4 * ((h // 24) % 3) / 2), 4) for h in hours],
        },
    )


def with_problems_24h():
    """On purpose not ready: a demand series that is too short, and a PV plant
    whose surplus cannot be exported. Shows how the system check reports it."""

    return Scenario(
        name="With problems, 24 hours",
        components=["demand", "grid", "pv"],
        settings={
            "demand": {"electricity_demand": "demand", "scaling_factor": 10.0},
            "grid": {"price_mode": "constant", "variable_costs": 0.30},
            "pv": {"mode": "fixed", "capacity": 5.0, "pv": "pv"},
        },
        time={"steps": 24},
        series={
            "electricity_demand": [1.0] * 10,
            "pv": [sun_shape(h) for h in range(24)],
        },
    )


EXAMPLES = {
    "grid_only_24h": grid_only_24h,
    "pv_battery_week": pv_battery_week,
    "with_problems_24h": with_problems_24h,
}


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)

    for name, build in EXAMPLES.items():
        path = FOLDER / f"{name}.json"
        build().save(path)
        print(f"{path.name:24s} {path.stat().st_size / 1000:6.1f} KB")


if __name__ == "__main__":
    main()