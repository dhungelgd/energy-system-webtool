"""The Scenario model must accept everything the real user interface produces."""

import io
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import frontend.ui_inputs as ui_inputs  # noqa: E402
from backend.scenario import Scenario  # noqa: E402
from backend.system_check import check_system  # noqa: E402
from frontend.ui_defaults import TECH_DEFAULTS  # noqa: E402
from frontend.ui_registry import UI_REGISTRY  # noqa: E402
from frontend.ui_templates import TEMPLATES  # noqa: E402

ENTRY = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


def default_settings(component):
    """The values the UI shows for a component when nothing was changed."""

    defaults = TECH_DEFAULTS.get(component, {})
    values = {}

    for field in UI_REGISTRY[component].get("inputs", []):
        if field["type"] == "number":
            values[field["key"]] = defaults.get(field["key"], field.get("default", 0.0))
        elif field["type"] == "selectbox":
            values[field["key"]] = defaults.get(field["key"], field["options"][0])

    return values


@pytest.mark.parametrize("component", list(UI_REGISTRY))
def test_default_settings_of_every_component_are_accepted(component):
    scenario = Scenario(
        components=[component],
        settings={component: default_settings(component)},
    )

    assert scenario.settings[component] == default_settings(component)


def test_every_component_of_the_ui_is_known_to_the_backend():
    from backend.scenario import COMPONENTS

    assert set(UI_REGISTRY) <= set(COMPONENTS)


def year_file():
    stamps = pd.date_range("2021-01-01", periods=8760, freq="1h")
    table = pd.DataFrame({
        "timestamp": stamps.strftime("%d.%m.%Y %H:%M"),
        "heat_demand": 0.5,
        "electricity_demand": 0.25,
        "pv": 0.125,
        "wind": 0.375,
        "price": 0.3,
        "cop": 3.5,
    })
    return table.to_csv(sep=";", decimal=",", index=False).encode("cp1252")


@pytest.fixture
def spy(monkeypatch):
    """Records what build_ui() returns on every run of the app."""

    recorded = {}
    original = ui_inputs.build_ui

    def build_ui_and_record():
        result = original()
        recorded["inputs"] = result
        return result

    monkeypatch.setattr(ui_inputs, "build_ui", build_ui_and_record)
    return recorded


@pytest.mark.parametrize("template", list(TEMPLATES))
def test_what_the_app_builds_for_every_template_is_a_valid_scenario(spy, template):
    app = AppTest.from_file(ENTRY, default_timeout=120)
    app.run()
    app.sidebar.button(key=f"template_{template}").click().run()

    assert not app.exception

    scenario = Scenario.from_inputs(*spy["inputs"], name=template)

    assert scenario.components == spy["inputs"][0]
    assert scenario.time.steps == 8760


def test_a_scenario_with_an_uploaded_file_survives_json_and_gives_the_same_check(spy):
    app = AppTest.from_file(ENTRY, default_timeout=120)
    app.run()
    app.sidebar.button(key="template_Full system").click().run()

    uploader = next(u for u in app.sidebar.file_uploader if u.key == "shared_ts_csv")
    uploader.set_value(("jahr.csv", year_file(), "text/csv")).run()

    selected, tech_inputs, input_data, solver = spy["inputs"]
    scenario = Scenario.from_inputs(selected, tech_inputs, input_data, solver, name="Jahr")

    # the column names the user chose are part of the settings
    assert tech_inputs["demand"]["electricity_demand"] == "electricity_demand"
    assert scenario.series["electricity_demand"][0] == 0.25

    again = Scenario.model_validate_json(scenario.model_dump_json())
    assert again == scenario

    def messages(inputs):
        return [(f.level, f.message) for f in check_system(*inputs[:3])]

    assert messages(again.to_inputs()) == messages((selected, tech_inputs, input_data))
