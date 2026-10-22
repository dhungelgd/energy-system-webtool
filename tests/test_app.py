"""Start the real Streamlit app without a browser and look at the inputs."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "frontend" / "app.py")


@pytest.fixture(scope="module")
def full_system_app():
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    app.sidebar.button(key="template_Full system").click().run()
    return app


def number_input(app, key):
    for widget in list(app.number_input) + list(app.sidebar.number_input):
        if widget.key == key:
            return widget
    raise AssertionError(f"input '{key}' is not shown")


def test_app_starts_without_errors(full_system_app):
    assert not full_system_app.exception


@pytest.mark.parametrize("key, expected", [
    ("battery_c_rate", 0.5),
    ("battery_loss_rate", 0.001),
    ("heat_storage_c_rate", 0.25),
    ("heat_storage_loss_rate", 0.001),
    ("grid_feedin_feedin_tariff", 0.078),
    ("grid_variable_costs", 0.3),
])
def test_default_values_shown_to_the_user(full_system_app, key, expected):
    assert number_input(full_system_app, key).value == expected


@pytest.mark.parametrize("key, unit", [
    ("battery_capacity", "kWh"),
    ("battery_capex", "kWh"),
    ("heat_storage_capacity", "kWh"),
    ("pv_capacity", "kW)"),
])
def test_units_in_the_labels(full_system_app, key, unit):
    assert unit in number_input(full_system_app, key).label