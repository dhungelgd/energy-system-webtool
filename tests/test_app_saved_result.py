"""Save a result in the real app and open it again (no browser)."""

import json
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from backend.results import ScenarioResult  # noqa: E402
from tests.helpers import needs_cbc  # noqa: E402

pytestmark = needs_cbc

ENTRY = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


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


def run_in_the_app():
    """Choose 'Electricity only', upload a year file, press Run Optimization."""

    app = AppTest.from_file(ENTRY, default_timeout=180)
    app.run()
    app.sidebar.button(key="template_Electricity only").click().run()

    uploader = next(u for u in app.sidebar.file_uploader if u.key == "shared_ts_csv")
    uploader.set_value(("jahr.csv", year_file(), "text/csv")).run()

    next(b for b in app.button if b.label == "Run Optimization").click().run()
    return app


def fresh_app():
    app = AppTest.from_file(ENTRY, default_timeout=180)
    app.run()
    return app


def open_file(app, name, content):
    uploader = next(u for u in app.file_uploader if u.key == "saved_result")
    uploader.set_value((name, content, "application/octet-stream")).run()
    return app


def download_buttons(app):
    return [element.proto.label for element in app.get("download_button")]


def headline(app):
    return [(metric.label, metric.value) for metric in app.metric]


@pytest.fixture(scope="module")
def journey():
    app = run_in_the_app()
    assert not app.exception
    return {
        "app": app,
        "saved": app.session_state["run_output"]["result_json"],
        "headline": headline(app),
        "tabs": [tab.label for tab in app.tabs],
    }


# ---------------------------------------------------------------------------
# saving
# ---------------------------------------------------------------------------

def test_a_run_offers_to_save_the_result(journey):
    assert "Save result (JSON)" in download_buttons(journey["app"])
    assert "Download results (Excel)" in download_buttons(journey["app"])


def test_the_saved_file_holds_the_shown_run(journey):
    result = ScenarioResult.model_validate_json(journey["saved"])
    shown = journey["app"].session_state["run_output"]

    assert result.objective == pytest.approx(float(shown["objective"]))
    assert result.horizon_hours == 8760
    assert result.buses["electricity"].flows.n_steps == 8760
    assert result.solver.termination == "optimal"


# ---------------------------------------------------------------------------
# opening
# ---------------------------------------------------------------------------

def test_a_saved_result_opens_in_a_new_session(journey):
    app = open_file(fresh_app(), "energy_system_result.json", journey["saved"].encode())

    assert not app.exception
    assert any("Showing the saved result" in info.value for info in app.info)


def test_the_opened_result_shows_the_same_figures_as_the_run(journey):
    app = open_file(fresh_app(), "result.json", journey["saved"].encode())

    assert headline(app) == journey["headline"]

    # the run page also has the input tabs; the results tabs start at "System graph"
    run_tabs = journey["tabs"][journey["tabs"].index("System graph"):]
    assert [tab.label for tab in app.tabs] == [t for t in run_tabs if t != "System graph"]


def test_an_opened_result_does_not_offer_to_save_itself_again(journey):
    app = open_file(fresh_app(), "result.json", journey["saved"].encode())

    assert download_buttons(app) == ["Download results (Excel)"]


def test_the_system_graph_is_the_one_thing_that_is_not_saved(journey):
    app = open_file(fresh_app(), "result.json", journey["saved"].encode())

    assert "System graph" not in [tab.label for tab in app.tabs]


def test_removing_the_file_shows_the_current_run_again():
    app = run_in_the_app()
    shown = headline(app)
    saved = app.session_state["run_output"]["result_json"].encode()

    open_file(app, "result.json", saved)
    assert any("Showing the saved result" in info.value for info in app.info)

    next(u for u in app.file_uploader if u.key == "saved_result").set_value(None).run()

    assert not any("Showing the saved result" in info.value for info in app.info)
    assert headline(app) == shown


# ---------------------------------------------------------------------------
# files that cannot be shown: a message, never a crash
# ---------------------------------------------------------------------------

def test_a_file_that_is_not_a_result_is_explained():
    app = open_file(fresh_app(), "other.json", json.dumps({"hello": 1}).encode())

    assert not app.exception
    assert any("not a result saved by this tool" in error.value for error in app.error)


def test_a_file_that_is_not_json_is_explained():
    app = open_file(fresh_app(), "notes.json", b"this is not json")

    assert not app.exception
    assert any("not a result saved by this tool" in error.value for error in app.error)


def test_a_result_without_the_hourly_flows_says_so(journey):
    light = json.loads(journey["saved"])
    for bus in light["buses"].values():
        bus["flows"] = None

    app = open_file(fresh_app(), "light.json", json.dumps(light).encode())

    assert not app.exception
    assert any("without the hourly flows" in error.value for error in app.error)


def test_a_result_from_a_newer_version_is_explained(journey):
    newer = json.loads(journey["saved"])
    newer["schema_version"] = 99

    app = open_file(fresh_app(), "newer.json", json.dumps(newer).encode())

    assert not app.exception
    assert any("newer version" in error.value for error in app.error)