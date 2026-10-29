"""The NiceGUI interface of the Energy System Web Tool (work in progress).

It works on scenarios of layout 2 (scenario_v2.py), through service_v2.py, and shows
a ScenarioResult (results.py). This file only builds the pages.
"""

import logging

from nicegui import events, run, ui

from backend import service_v2
from backend.component_specs import INFO
from backend.service import ScenarioError
from backend.system_templates import SYSTEM_TEMPLATES, components_by_group
from frontend_nicegui.draft import (
    DEFAULT_NAME,
    MAX_NAME_LENGTH,
    MAX_STEPS,
    MIN_STEPS,
    START_HINT,
    STEPS_HINT,
    ScenarioDraft,
    parse_start,
    parse_steps,
)
from frontend_nicegui.markers import slug
from frontend_nicegui.result_view import headline_cards, solver_text
from frontend_nicegui.scenario_view import (
    ScenarioFileError,
    component_rows,
    describe_period,
    load_scenario,
    series_rows,
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


TYPING_DELAY_MS = 300           # wait until the typing pauses, so that "24" does not check "2" first


def is_valid(parse, value):
    """True if the parser accepts the value (for the validation of an input field)."""

    try:
        parse(value)
    except ValueError:
        return False
    return True


def build_builder():
    """Build a scenario: its name and period, its components, and the live system check.

    Returns the ScenarioDraft that the page keeps up to date.
    """

    draft = ScenarioDraft()
    boxes = {}

    @ui.refreshable
    def period_text():
        ui.label(f"Period: {describe_period(draft.scenario())}").mark("draft-period")

    @ui.refreshable
    def overview():
        if len(draft) == 0:
            ui.label("Nothing selected yet. Choose a template or tick components.").classes(
                "text-grey").mark("selection-empty")
            return

        with ui.card().classes("w-full"):
            ui.label(draft.name).classes("text-xl font-semibold").mark("draft-title")
            count = len(draft)
            ui.label(f"{count} component{'s' if count != 1 else ''}").classes("text-grey").mark(
                "selection-count")
            ui.table(columns=COMPONENT_COLUMNS, rows=component_rows(draft.scenario())).props(
                "dense flat").classes("w-full").mark("draft-components")

        show_findings(draft.findings(), title="System check of your scenario", marker="draft-findings")

    def set_name(event):
        try:
            draft.name = event.value
        except ValueError:
            return
        overview.refresh()

    def set_start(event):
        try:
            draft.start = event.value
        except ValueError:
            return                   # the field shows the reason; the draft keeps the last good date
        period_text.refresh()
        overview.refresh()

    def set_steps(event):
        try:
            draft.steps = event.value
        except ValueError:
            return
        period_text.refresh()
        overview.refresh()

    def show_selection_in_boxes():
        for key, box in boxes.items():
            box.value = draft.is_selected(key)
        overview.refresh()

    def on_tick(key, event):
        # also called when a template sets a box; then nothing is left to do
        if draft.is_selected(key) != event.value:
            draft.set(key, event.value)
            overview.refresh()

    def use_template(name):
        draft.apply_template(name)
        show_selection_in_boxes()

    def clear_selection():
        draft.clear()
        show_selection_in_boxes()

    with ui.card().classes("w-full"):
        ui.label("Your scenario").classes("text-xl font-semibold")

        ui.input("Name", value=draft.name, placeholder=DEFAULT_NAME, on_change=set_name).props(
            f"outlined dense maxlength={MAX_NAME_LENGTH} debounce={TYPING_DELAY_MS}").classes("w-full").mark("draft-name")

        with ui.row().classes("w-full items-start gap-4"):
            with ui.input(
                "Start date", value=draft.start.isoformat(), on_change=set_start,
                validation={START_HINT: lambda value: is_valid(parse_start, value)},
            ).props(f"outlined dense debounce={TYPING_DELAY_MS}").classes("w-48").mark("draft-start") as start_input:
                with ui.menu().props("no-parent-event") as menu:
                    with ui.date().bind_value(start_input):
                        with ui.row().classes("justify-end"):
                            ui.button("Close", on_click=menu.close).props("flat")
                with start_input.add_slot("append"):
                    ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")

            steps_input = ui.number(
                "Hourly steps", value=draft.steps, min=MIN_STEPS, max=MAX_STEPS, precision=0,
                format="%d", on_change=set_steps,
                validation={STEPS_HINT: lambda value: is_valid(parse_steps, value)},
            ).props(f"outlined dense debounce={TYPING_DELAY_MS}").classes("w-40").mark("draft-steps")

            for label, steps in (("1 day", 24), ("1 week", 168), ("1 year", 8760)):
                ui.button(label, on_click=lambda _, n=steps: setattr(steps_input, "value", n)).props(
                    "outline dense no-caps").mark(f"steps-{steps}")

        period_text()
        ui.label("The model works in hourly steps: 24 steps are one day, 8,760 are a year.").classes(
            "text-grey text-sm")

    with ui.card().classes("w-full"):
        ui.label("Build a scenario").classes("text-xl font-semibold")
        ui.label("Start from a template, or tick the components of your energy system.")
        ui.label(
            "Work in progress: the forms for the settings of each component and the upload of "
            "time series come next. Until then you can see below what is still missing, and "
            "open a complete scenario file further down."
        ).classes("text-grey text-sm")

        with ui.row().classes("w-full gap-2"):
            for name in SYSTEM_TEMPLATES:
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
                            INFO[key].label,
                            on_change=lambda event, k=key: on_tick(k, event),
                        ).mark(f"component-{key}")

    overview()

    return draft


def show_findings(findings, title="System check", marker="findings"):
    """The result of the system check: errors, warnings, or 'ready'."""

    errors = [f for f in findings if f.level == "error"]

    with ui.card().classes("w-full").mark(marker):
        ui.label(title).classes("text-xl font-semibold")

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

        build_builder()

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