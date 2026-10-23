"""The NiceGUI interface of the Energy System Web Tool (work in progress).

It uses the same backend as the Streamlit interface: scenario.py, service.py
and results.py. This file only builds the pages.
"""

from nicegui import ui

TITLE = "Energy System Web Tool"


@ui.page("/")
def home_page():
    with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-4"):
        ui.label(TITLE).classes("text-3xl font-bold")
        ui.label("Version with the NiceGUI interface (work in progress).")


def run_server(port=8080, reload=False):
    """Start the web server (blocks until it is stopped)."""

    ui.run(title=TITLE, port=port, reload=reload, show=False)