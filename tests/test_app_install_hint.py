"""A friendly message instead of 'No module named backend' when the project is not installed."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "frontend" / "app.py")


def test_missing_installation_is_explained(monkeypatch):
    # makes "import backend" fail, as in an environment without "pip install -e ."
    monkeypatch.setitem(sys.modules, "backend", None)

    app = AppTest.from_file(APP, default_timeout=60)
    app.run()

    assert not app.exception
    assert any("pip install -e ." in error.value for error in app.error)


def test_no_message_when_the_project_is_installed():
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()

    assert not app.exception
    assert not any("pip install" in error.value for error in app.error)
