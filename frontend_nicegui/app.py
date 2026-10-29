"""The NiceGUI interface of the Energy System Web Tool (work in progress).

It works on scenarios of layout 2 (scenario_v2.py), through service_v2.py, and shows
a ScenarioResult (results.py). This file only builds the pages.
"""

import logging

from nicegui import events, run, ui

from backend import service_v2
from backend.service import ScenarioError
from frontend.ui_registry import UI_REGISTRY
from frontend_nicegui.result_view import headline_cards, solver_text
from frontend_nicegui.scenario_view import (
    ScenarioFileError,
    component_rows,
    describe_period,
    load_scenario,
    series_rows,
)
from frontend_nicegui.selection import (
    ComponentSelection,
    components_by_group,
    slug,
    template_names,
)

TITLE = "Energy System Web Tool"

logger = logging.getLogger(__name__)

COMPONENT_COLUMNS = [
    {"name": "component", "label": "Component", "field": "component", "align": "left"},
    {"name": "type", "label": "Type", "field": "type", "align": "left"},
    {"name": "mode", "label": "Mode", "field": "mode", "align": "left"},
    {"name": "size", "label": "Size", "field": "size", "align": "left"},
]

SERIES_COLUMNS = [
    {"name": "series", "label": "Time series", "field": "series", "align": "left"},
    {"name": "unit", "label": "Unit", "field": "unit", "align": "left"},
    {"name": "used_by", "label": "Used by", "field": "used_by", "align": "left"},
    {"name": "values", "label": "Values", "field": "values"},
    {"name": "empty", "label": "Empty", "field": "empty"},
    {"name": "min", "label": "Smallest", "field": "min"},
    {"name": "max", "label": "Largest", "field": "max"},
]


async def solve(scenario):
    """Run the optimization in another process.

    A solve takes seconds to minutes. The web server serves all visitors from
    one process, so a solve inside it would freeze every page until it is done.
    """

    return await run.cpu_bound(service_v2.run, scenario)


def show_result(result):
    """The headline figures of a result."""

    ui.label("Results").classes("text-xl font-semibold")

    with ui.row().classes("w-full gap-4"):
        for card in headline_cards(result):
            with ui.card().classes("min-w-[11rem]").mark("headline"):
                ui.label(card["label"]).classes("text-grey text-sm")
                ui.label(card["value"]).classes("text-xl font-semibold")
                if card["help"]:
                    ui.tooltip(card["help"]).classes("text-body2")

    ui.label(solver_text(result)).classes("text-grey").mark("solver")


def show_run(scenario):
    """The button that starts the optimization, and the place for its result."""

    with ui.card().classes("w-full"):
        ui.label("Run the optimization").classes("text-xl font-semibold")
        ui.label(
            "The optimization runs in the background, so the page stays usable. "
            "A full year can take from a few seconds up to a minute."
        )

        with ui.row().classes("items-center gap-4"):
            button = ui.button("Run optimization", icon="play_arrow").mark("run")
            spinner = ui.spinner(size="lg")
            spinner.visible = False
            status = ui.label("")

    results = ui.column().classes("w-full gap-4").mark("results")

    async def start():
        button.disable()
        spinner.visible = True
        status.text = "Running the optimization..."
        results.clear()

        try:
            result = await solve(scenario)

        except ScenarioError as error:
            with results:
                ui.label(f"The optimization could not be completed: {error}").classes(
                    "text-negative").mark("run-error")

        except Exception:  # noqa: BLE001 - the page must stay alive whatever happens
            logger.exception("The optimization stopped unexpectedly")
            with results:
                ui.label(
                    "The optimization stopped unexpectedly. Please try again; "
                    "if it happens again, tell the developers."
                ).classes("text-negative").mark("run-error")

        else:
            with results:
                show_result(result)

        finally:
            spinner.visible = False
            status.text = ""
            button.enable()

    button.on_click(start)


def build_picker():
    """Choose the components of an energy system: a template, or tick them by group.

    Returns the ComponentSelection that the page keeps up to date.
    """

    selection = ComponentSelection()
    boxes = {}

    @ui.refreshable
    def summary():
        if len(selection) == 0:
            ui.label("Nothing selected yet. Choose a template or tick components.").classes(
                "text-grey").mark("selection-empty")
            return

        count = len(selection)
        ui.label(f"{count} component{'s' if count != 1 else ''} selected").classes(
            "font-semibold").mark("selection-count")

        for group, chosen in selection.selected_by_group():
            with ui.row().classes("items-center gap-2"):
                ui.label(group).classes("text-grey min-w-[8rem]")
                for key, label in chosen:
                    ui.chip(label).props("dense").mark(f"chosen-{key}")

    def show_selection_in_boxes():
        for key, box in boxes.items():
            box.value = selection.is_selected(key)
        summary.refresh()

    def on_tick(key, event):
        # also called when a template sets a box; then nothing is left to do
        if selection.is_selected(key) != event.value:
            selection.set(key, event.value)
            summary.refresh()

    def use_template(name):
        selection.apply_template(name)
        show_selection_in_boxes()

    def clear_selection():
        selection.clear()
        show_selection_in_boxes()

    with ui.card().classes("w-full"):
        ui.label("Build a scenario").classes("text-xl font-semibold")
        ui.label("Start from a template, or tick the components of your energy system.")

        with ui.row().classes("w-full gap-2"):
            for name in template_names():
                ui.button(name, on_click=lambda _, n=name: use_template(n)).props(
                    "outline dense no-caps").mark(f"template-{slug(name)}")
            ui.button("Clear selection", on_click=lambda _: clear_selection()).props(
                "flat dense no-caps").mark("clear-selection")

        with ui.row().classes("w-full gap-8"):
            for group, keys in components_by_group().items():
                with ui.column().classes("gap-0"):
                    ui.label(group).classes("font-semibold")
                    for key in keys:
                        boxes[key] = ui.checkbox(
                            UI_REGISTRY[key]["label"],
                            on_change=lambda event, k=key: on_tick(k, event),
                        ).mark(f"component-{key}")

        ui.separator()
        summary()

    return selection


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

    findings = service_v2.check(scenario)
    show_findings(findings)

    if not any(f.level == "error" for f in findings):
        show_run(scenario)


@ui.page("/")
def home_page():

    with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-4"):
        ui.label(TITLE).classes("text-3xl font-bold")
        ui.label("Version with the NiceGUI interface (work in progress).")

        build_picker()

        with ui.card().classes("w-full"):
            ui.label("Open a scenario file").classes("text-xl font-semibold")
            ui.label(
                "Or open a scenario that was saved earlier. A scenario file (JSON) "
                "holds the components, settings and time series of one energy system. "
                "Examples are in the folder examples/scenarios_v2."
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

    # the recommended way to start the processes of run.cpu_bound; the same on
    # every system (Windows and macOS always use it)
    run.process_pool_start_method = "spawn"

    ui.run(title=TITLE, port=port, reload=reload, show=False)