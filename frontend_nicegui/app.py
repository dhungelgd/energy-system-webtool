"""The NiceGUI interface of the Energy System Web Tool (work in progress).

It uses the same backend as the Streamlit interface: scenario.py, service.py
and results.py. This file only builds the pages.
"""

from nicegui import events, ui

from backend.service import check
from frontend_nicegui.scenario_view import (
    ScenarioFileError,
    component_labels,
    component_rows,
    describe_period,
    load_scenario,
    series_rows,
)

TITLE = "Energy System Web Tool"

COMPONENT_COLUMNS = [
    {"name": "component", "label": "Component", "field": "component", "align": "left"},
    {"name": "mode", "label": "Mode", "field": "mode", "align": "left"},
    {"name": "size", "label": "Size", "field": "size", "align": "left"},
]

SERIES_COLUMNS = [
    {"name": "series", "label": "Time series", "field": "series", "align": "left"},
    {"name": "values", "label": "Values", "field": "values"},
    {"name": "empty", "label": "Empty", "field": "empty"},
    {"name": "min", "label": "Smallest", "field": "min"},
    {"name": "max", "label": "Largest", "field": "max"},
]


def show_findings(findings):
    """The result of the system check: errors, warnings, or 'ready'."""

    errors = [f for f in findings if f.level == "error"]

    with ui.card().classes("w-full").mark("findings"):
        ui.label("System check").classes("text-xl font-semibold")

        if not findings:
            with ui.row().classes("items-center gap-2"):
                ui.icon("check_circle", color="positive")
                ui.label("System check passed. Ready to optimize.")
            return

        for finding in findings:
            icon, color = ("error", "negative") if finding.level == "error" else ("warning", "warning")
            with ui.row().classes("items-start gap-2 no-wrap"):
                ui.icon(icon, color=color)
                ui.label(finding.message)

        if errors:
            ui.label("Fix the errors above before the optimization can start.").classes("text-negative")
        else:
            ui.label("There are warnings but no errors. The optimization can be started.")


def show_scenario(scenario, file_name):
    """Everything about a scenario that was opened."""

    with ui.card().classes("w-full"):
        ui.label(scenario.name).classes("text-xl font-semibold").mark("scenario-name")
        ui.label(f"File: {file_name}").classes("text-grey")
        ui.label(f"Period: {describe_period(scenario)}")
        ui.label(f"Solver: {scenario.solver.name}")

        ui.label("Components").classes("font-semibold mt-2")
        ui.table(columns=COMPONENT_COLUMNS, rows=component_rows(scenario)).props("dense flat").classes("w-full").mark("components")

        if scenario.series:
            ui.label("Time series").classes("font-semibold mt-2")
            ui.table(columns=SERIES_COLUMNS, rows=series_rows(scenario)).props("dense flat").classes("w-full").mark("series")

    show_findings(check(scenario, labels=component_labels()))


@ui.page("/")
def home_page():

    with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-4"):
        ui.label(TITLE).classes("text-3xl font-bold")
        ui.label("Version with the NiceGUI interface (work in progress).")

        with ui.card().classes("w-full"):
            ui.label("1. Open a scenario").classes("text-xl font-semibold")
            ui.label(
                "A scenario file (JSON) holds the components, settings and time "
                "series of one energy system. Examples are in the folder examples/scenarios."
            )

            async def open_file(event: events.UploadEventArguments):
                content = await event.file.read()
                event.sender.reset()            # ready for the next file
                details.clear()

                with details:
                    try:
                        scenario = load_scenario(content)
                    except ScenarioFileError as error:
                        ui.label(str(error)).classes("text-negative").mark("file-error")
                        return

                    show_scenario(scenario, event.file.name)

            ui.upload(
                label="Choose a scenario file (JSON)",
                on_upload=open_file,
                auto_upload=True,
                max_files=1,
            ).props("accept=.json flat bordered").classes("w-full").mark("upload")

        details = ui.column().classes("w-full gap-4")


def run_server(port=8080, reload=False):
    """Start the web server (blocks until it is stopped)."""

    ui.run(title=TITLE, port=port, reload=reload, show=False)