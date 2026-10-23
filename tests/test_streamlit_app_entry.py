"""The entry file in the repository root (used locally and on Streamlit Community Cloud)."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ENTRY = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


def test_root_entry_file_starts_the_app():
    app = AppTest.from_file(ENTRY, default_timeout=120)
    app.run()
    app.sidebar.button(key="template_Full system").click().run()

    assert not app.exception
    assert not any("not installed" in error.value for error in app.error)
    assert any(widget.key == "battery_c_rate" for widget in app.number_input)
