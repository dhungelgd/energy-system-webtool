"""The NiceGUI interface of the Energy System Web Tool (work in progress).

It works on scenarios of layout 2 (scenario_v2.py), through service_v2.py, and shows
a ScenarioResult (results.py). This file only builds the pages.

The page is drawn from a PageState (page_state.py). When the visitor changes the
language, the whole page is drawn again from that state: what was typed, the scenario
that is being built, the opened file and the result stay. The language comes from the
link (?lang=de), else from the browser, else English.
"""

import logging

from nicegui import events, run, ui

from backend import service_v2
from backend.findings import finding_text
from backend.i18n import LANGUAGES, Msg, choose_language
from backend.service import ScenarioError
from backend.system_templates import SYSTEM_TEMPLATES, components_by_group
from frontend_nicegui.board import (
    BOARD,
    COLUMN_TEXTS,
    COLUMNS,
    LANE_COLORS,
    LANES,
    STYLE,
    addable,
    finding_keys,
    findings_by_component,
    problem_texts,
    tile_detail,
    tile_problem_text,
    tile_state,
)
from frontend_nicegui.calendar import locale_prop
from frontend_nicegui.draft import (
    MAX_NAME_LENGTH,
    MAX_STEPS,
    MAX_YEAR,
    MIN_STEPS,
    MIN_YEAR,
    parse_start,
    parse_steps,
)
from frontend_nicegui.form_view import TYPING_DELAY_MS, render_component_form
from frontend_nicegui.forms import has_form
from frontend_nicegui.markers import slug
from frontend_nicegui.names import component_label, display_name, fix_label, group_label, template_label
from frontend_nicegui.page_state import PageState
from frontend_nicegui.result_tabs import render_result_tabs
from frontend_nicegui.result_terms import bus_label
from frontend_nicegui.result_view import (
    format_elapsed,
    headline_cards,
    period_caption,
    run_failure,
    solver_label,
    solver_text,
)
from frontend_nicegui.scenario_view import component_rows, describe_period, series_rows
from frontend_nicegui.status import COLORS, ICONS, badge_of, draft_status, run_hint, status_text

TITLE = "Energy System Web Tool"

NO_COMPONENT = "none"               # the panel of the drawer when no component is open
STATE_ICONS = {"ok": ("check_circle", "positive"), "warning": ("warning", "warning"), "error": ("error", "negative")}

logger = logging.getLogger(__name__)


def component_columns(tr):
    return [
        {"name": "component", "label": tr("table.component"), "field": "component", "align": "left"},
        {"name": "type", "label": tr("table.type"), "field": "type", "align": "left"},
        {"name": "mode", "label": tr("table.mode"), "field": "mode", "align": "left"},
        {"name": "size", "label": tr("table.size"), "field": "size", "align": "left"},
    ]


def series_columns(tr):
    return [
        {"name": "series", "label": tr("table.series"), "field": "series", "align": "left"},
        {"name": "unit", "label": tr("table.unit"), "field": "unit", "align": "left"},
        {"name": "used_by", "label": tr("table.used_by"), "field": "used_by", "align": "left"},
        {"name": "values", "label": tr("table.values"), "field": "values"},
        {"name": "empty", "label": tr("table.empty"), "field": "empty"},
        {"name": "min", "label": tr("table.min"), "field": "min"},
        {"name": "max", "label": tr("table.max"), "field": "max"},
    ]


async def solve(scenario):
    """Run the optimization in another process.

    A solve takes seconds to minutes. The web server serves all visitors from
    one process, so a solve inside it would freeze every page until it is done.
    """

    return await run.cpu_bound(service_v2.run, scenario)


async def execute(scenario):
    """Run a scenario in the background. Gives (result, None), or (None, why it failed as a Msg).

    A problem that the optimization reports is explained to the visitor; anything else is logged for the
    developers and only called unexpected on the page (the details stay hidden).
    """

    try:
        return await solve(scenario), None

    except ScenarioError as error:
        return None, run_failure(error)

    except Exception:  # noqa: BLE001 - the page must stay alive whatever happens
        logger.exception("The optimization stopped unexpectedly")
        return None, Msg("run.unexpected")


def is_valid(parse, value):
    """True if the parser accepts the value (for the validation of an input field)."""

    try:
        parse(value)
    except ValueError:
        return False
    return True


def show_result(result, tr, key="file"):
    """A result: the headline figures, the note for a period shorter than a year, the solver, and the tabs.

    `key` ('draft' or 'file') makes the markers of two results on a page different.
    """

    ui.label(tr("result.heading")).classes("text-xl font-semibold")

    with ui.row().classes("w-full gap-4"):
        for card in headline_cards(result, tr):
            with ui.card().classes("min-w-[11rem]").mark("headline"):
                ui.label(card["label"]).classes("text-grey text-sm")
                ui.label(card["value"]).classes("text-xl font-semibold")
                if card["help"]:
                    ui.tooltip(card["help"]).classes("text-body2")

    caption = period_caption(result, tr)
    if caption is not None:
        ui.label(caption).classes("text-grey text-sm").mark(f"{key}-period-note")

    ui.label(solver_text(result, tr)).classes("text-grey").mark("solver")

    render_result_tabs(result, tr, key)


def show_findings(findings, tr, title_key="findings.title", marker="findings", on_fix=None, on_goto=None, names=None):
    """The result of the system check: errors, warnings, or 'ready'.

    With `on_fix`, a finding that proposes a repair gets a button for each: `on_fix(keys)` is called with
    the components that it adds. With `on_goto`, a finding about a component gets a button that opens it:
    `on_goto(key)`; `names` maps the name of a component to its key. A scenario that was opened from a file
    cannot be changed, so it gets none of them.
    """

    errors = [f for f in findings if f.level == "error"]

    with ui.card().classes("w-full").mark(marker):
        ui.label(tr(title_key)).classes("text-xl font-semibold")

        if not findings:
            with ui.row().classes("items-center gap-2"):
                ui.icon("check_circle", color="positive")
                ui.label(tr("findings.passed"))
            return

        for index, finding in enumerate(findings):
            icon, color = ("error", "negative") if finding.level == "error" else ("warning", "warning")
            with ui.column().classes("gap-1"):
                with ui.row().classes("items-start gap-2 no-wrap"):
                    ui.icon(icon, color=color)
                    ui.label(finding_text(finding, tr))

                if on_fix is not None and finding.fixes:
                    with ui.row().classes("gap-2 ml-8"):
                        for option, keys in enumerate(finding.fixes):
                            ui.button(
                                fix_label(tr, keys), icon="add", on_click=lambda _, k=keys: on_fix(k),
                            ).props("outline dense no-caps").mark(f"fix-{index}-{option}")

        if on_goto is not None:
            for index, finding in enumerate(findings):
                keys = sorted(finding_keys(finding, names or {}))
                if keys:
                    with ui.row().classes("gap-2 ml-8"):
                        for key in keys:
                            ui.button(
                                tr("findings.goto", name=component_label(tr, key)), icon="arrow_forward",
                                on_click=lambda _, k=key: on_goto(k),
                            ).props("flat dense no-caps").mark(f"goto-{index}-{key}")

        if on_fix is not None and any(finding.fixes for finding in findings):
            ui.label(tr("findings.fix_note")).classes("text-grey text-sm").mark("fix-note")

        if errors:
            ui.label(tr("findings.fix_errors")).classes("text-negative")
        else:
            ui.label(tr("findings.warnings_only"))


@ui.page("/")
def home_page():
    request = ui.context.client.request
    state = PageState(choose_language(request.query_params.get("lang"), request.headers.get("accept-language")))
    boxes = {}                      # the checkboxes of the page that is drawn now
    shown = {"results": None}       # what the block of the results of the draft shows now (see sync_results)
    chrome = {"findings": (0, 0), "list": [], "tabs": None, "badge": None, "panels": None, "sheet": None}
    # what the top bar, the tabs, the board and the drawer show of the check (see update_chrome)

    # ----- the language ----------------------------------------------------

    def switch_language(event):
        if state.running or event.value == state.language:
            return                  # the switch is blocked during a run; a run belongs to one page
        state.language = event.value
        content.refresh()
        settings.refresh()          # the side sheet is not part of the content
        header_left.refresh()
        header_status.refresh()
        header_lang.refresh()

    # ----- your scenario: name and period ----------------------------------

    @ui.refreshable
    def period_text():
        tr = state.tr
        period = describe_period(state.draft.scenario(), tr)
        ui.label(tr("scenario.period", period=period)).mark("draft-period")

    def set_name(event):
        try:
            state.draft.name = event.value
        except ValueError:
            return
        overview.refresh()

    def set_start(event):
        try:
            state.draft.start = event.value
        except ValueError:
            return                   # the field shows the reason; the draft keeps the last good date
        period_text.refresh()
        overview.refresh()

    def set_steps(event):
        try:
            state.draft.steps = event.value
        except ValueError:
            return
        period_text.refresh()
        overview.refresh()

    def scenario_card():
        tr, draft = state.tr, state.draft

        with ui.card().classes("w-full"):
            ui.label(tr("scenario.heading")).classes("text-xl font-semibold")

            with ui.row().classes("w-full items-start gap-4"):
                start_hint = tr("hint.start", first=MIN_YEAR, last=MAX_YEAR)
                with ui.input(
                    tr("scenario.start"), value=draft.start.isoformat(), on_change=set_start,
                    validation={start_hint: lambda value: is_valid(parse_start, value)},
                ).props(f"outlined dense debounce={TYPING_DELAY_MS}").classes("w-48").mark("draft-start") as start_input:
                    with ui.menu().props("no-parent-event") as menu:
                        with ui.date().bind_value(start_input).mark("draft-calendar") as calendar:
                            with ui.row().classes("justify-end"):
                                ui.button(tr("common.close"), on_click=menu.close).props("flat")
                        if locale_prop(state.language):
                            calendar.props(locale_prop(state.language))
                    with start_input.add_slot("append"):
                        ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")

                steps_hint = tr("hint.steps", min=MIN_STEPS, max=tr.integer(MAX_STEPS))
                steps_input = ui.number(
                    tr("scenario.steps"), value=draft.steps, min=MIN_STEPS, max=MAX_STEPS, precision=0,
                    format="%d", on_change=set_steps,
                    validation={steps_hint: lambda value: is_valid(parse_steps, value)},
                ).props(f"outlined dense debounce={TYPING_DELAY_MS}").classes("w-40").mark("draft-steps")

                for label_key, steps in (("steps.day", 24), ("steps.week", 168), ("steps.year", 8760)):
                    ui.button(tr(label_key), on_click=lambda _, n=steps: setattr(steps_input, "value", n)).props(
                        "outline dense no-caps").mark(f"steps-{steps}")

            period_text()
            ui.label(tr("scenario.period_hint", year=tr.integer(8760))).classes("text-grey text-sm")

    # ----- build a scenario: the components and the live check -------------

    @ui.refreshable
    def overview():
        tr, draft = state.tr, state.draft

        if len(draft) == 0:
            ui.label(tr("builder.empty")).classes("text-grey").mark("selection-empty")
            update_chrome([])
            sync_results()
            return

        scenario = draft.scenario(tr("scenario.default_name"))

        with ui.card().classes("w-full"):
            ui.label(scenario.name).classes("text-xl font-semibold").mark("draft-title")
            ui.label(tr.plural("builder.count", len(draft))).classes("text-grey").mark("selection-count")
            ui.table(columns=component_columns(tr), rows=component_rows(scenario, tr)).props(
                "dense flat").classes("w-full").mark("draft-components")

        findings = service_v2.check(scenario)
        show_findings(
            findings, tr, "findings.title_draft", "draft-findings", on_fix=add_components, on_goto=goto,
            names={component.name: component.template for component in draft.components()},
        )
        update_chrome(findings)
        sync_results()

    def running_clock(running, marker):
        """'Running the optimization... 1:12' next to the spinner, counting up while the run goes on."""

        tr = state.tr

        def text():
            return tr("run.running_for", time=format_elapsed(state.elapsed()))

        label = ui.label(text() if running else "").mark(marker)
        if running:
            ui.timer(1.0, lambda: label.set_text(text()))

    # ----- the top bar: name, status, run, language -------------------------

    def current_status():
        errors, warnings = chrome["findings"]
        return draft_status(
            has_components=len(state.draft) > 0, errors=errors, warnings=warnings,
            running=state.running, outdated=state.draft_changed_since_run(),
        )

    def show_view(name):
        state.view = name
        tabs = chrome["tabs"]
        if tabs is not None and not tabs.is_deleted:
            tabs.set_value(name)

    def update_chrome(findings):
        """Tell the top bar and the badge of the Check tab what the check found."""

        errors = sum(1 for finding in findings if finding.level == "error")
        chrome["findings"] = (errors, len(findings) - errors)
        chrome["list"] = list(findings)
        header_status.refresh()
        board.refresh()
        component_problems.refresh()

        badge = chrome["badge"]
        if badge is not None and not badge.is_deleted:
            count, color = badge_of(current_status())
            badge.set_text(str(count))
            badge.props(f"color={color}")
            badge.set_visibility(count > 0)

    @ui.refreshable
    def header_left():
        tr = state.tr

        ui.icon("bolt", color="primary").classes("text-3xl")
        ui.label(tr("app.title")).classes("text-lg font-bold").mark("app-title")
        ui.input(
            tr("scenario.name"), value=state.draft.name, placeholder=tr("scenario.default_name"), on_change=set_name,
        ).props(f"outlined dense maxlength={MAX_NAME_LENGTH} debounce={TYPING_DELAY_MS}").classes(
            "w-72 ml-4").mark("draft-name")

    @ui.refreshable
    def header_status():
        """The status chip (it opens the check), the spinner while a run goes on, and the Run button."""

        tr = state.tr
        status = current_status()

        def text():
            return status_text(status, tr, format_elapsed(state.elapsed()))

        chip = ui.button(text(), icon=ICONS[status.kind], on_click=lambda: show_view("check")).props(
            f"outline no-caps dense color={COLORS[status.kind]}").mark("status")
        chip.tooltip(tr("status.open_check"))
        if status.kind == "running":
            ui.timer(1.0, lambda: chip.set_text(text()))

        spinner = ui.spinner(size="sm")
        spinner.visible = state.running_draft

        button = ui.button(tr("run.button"), icon="play_arrow", on_click=start_draft).props("no-caps color=primary").mark(
            "draft-run")
        button.set_enabled(status.can_run)
        hint = run_hint(status, tr)
        if hint:
            button.tooltip(hint)

    @ui.refreshable
    def header_lang():
        toggle = ui.toggle(LANGUAGES, value=state.language, on_change=switch_language).props("dense no-caps").mark(
            "language")
        state.language_toggle = toggle            # a run blocks it and frees it again (start_draft, start)

    def results_wanted():
        """What the block of the results should show: is there a draft, and was it changed since the run."""

        return len(state.draft) > 0, state.draft_changed_since_run()

    @ui.refreshable
    def draft_results():
        """What came out of the last run of the draft, below its card. A result belongs to the scenario as it
        was run: if the draft was changed since, it stays but says so. This block is drawn on its own, so that a
        change in a form does not send the charts to the browser again."""

        tr = state.tr
        shown["results"] = wanted = results_wanted()
        run = state.draft_run

        if run is None or not wanted[0]:
            with ui.column().classes("w-full gap-2").mark("draft-results-empty"):
                ui.label(tr("results.empty_title")).classes("text-xl font-semibold")
                ui.label(tr("results.empty_press"))
                ui.label(tr("run.intro")).classes("text-grey")
            return

        changed = wanted[1]

        with ui.column().classes("w-full gap-4").mark("draft-results"):
            if run.error is None and run.result is None:
                ui.label(tr("results.running")).classes("text-grey").mark("draft-running")
            elif run.error is not None:
                if not changed:                                   # the error of an earlier version is not news
                    ui.label(tr.message(run.error)).classes("text-negative").mark("draft-run-error")
            elif run.result is not None:
                if changed:
                    with ui.row().classes("items-start gap-2 no-wrap"):
                        ui.icon("warning", color="warning")
                        ui.label(tr("run.outdated")).mark("draft-outdated")
                show_result(run.result, tr, "draft")

    def sync_results():
        """Draw the results again only if what they show has changed (the draft was changed since the run)."""

        if results_wanted() != shown["results"]:
            draft_results.refresh()

    async def start_draft():
        started = state.start_draft_run(tr_default_name())
        if started is None:
            return

        if state.language_toggle is not None:
            state.language_toggle.disable()
        overview.refresh()
        draft_results.refresh()         # the result of the run before is gone
        run_panel.refresh()             # one run at a time: the button of the opened file is blocked too
        header_status.refresh()
        show_view("results")            # the visitor sees that something is going on, and then the result

        result, failure = await execute(started.scenario)

        state.finish_draft_run(started, result=result, error=failure)

        if state.language_toggle is not None and not state.language_toggle.is_deleted:
            state.language_toggle.enable()
        overview.refresh()
        draft_results.refresh()
        run_panel.refresh()
        header_status.refresh()

    def tr_default_name():
        return state.tr("scenario.default_name")

    # ----- the board and the drawer ------------------------------------------

    def select(key):
        """Open a component in the side sheet (None closes it)."""

        state.selected = key
        panels = chrome["panels"]
        if panels is not None and not panels.is_deleted:
            panels.set_value(key or NO_COMPONENT)
        sheet = chrome["sheet"]
        if sheet is not None and not sheet.is_deleted:
            sheet.set_value(key is not None)
        board.refresh()

    def sheet_changed(event):
        """The visitor closed the side sheet (a click outside it on a small screen): no component is open now."""

        if not event.value and state.selected is not None:
            select(None)

    def goto(key):
        """From a finding of the check to the settings of its component."""

        select(key)
        show_view("system")

    def add_component(key):
        state.draft.set(key, True)
        state.selected = key                # a new component is opened to be set up
        show_selection_in_boxes()

    def remove_component(key):
        state.draft.set(key, False)         # (settings() closes the drawer when its component is gone)
        show_selection_in_boxes()

    def draw_tile(component, found):
        tr = state.tr
        key = component.template
        icon, color, tint = STYLE[key]
        tile_kind = tile_state(found)
        problem = tile_problem_text(found, tr)
        symbol, symbol_color = STATE_ICONS[tile_kind]

        with ui.card().tight().props(f"flat bordered data-state={tile_kind}").classes(
                "w-full cursor-pointer q-pa-sm gap-1").style(
                "outline: 2px solid #0B6E6E" if key == state.selected else "") as card:
            with ui.row().classes("items-center no-wrap w-full gap-2"):
                with ui.element("div").style(
                        f"background:{tint};border-radius:8px;width:28px;height:28px;flex:none;display:flex;"
                        "align-items:center;justify-content:center"):
                    ui.icon(icon).style(f"color:{color};font-size:18px")
                ui.label(display_name(component, tr)).classes("font-semibold flex-grow")
                ui.icon(symbol, color=symbol_color).props("size=18px")
            ui.label(tile_detail(component, tr)).classes("text-grey text-sm")
            if problem:
                ui.label(problem).classes("text-xs " + ("text-negative" if tile_kind == "error" else "text-warning"))
                ui.tooltip("\n".join(text for _, text in problem_texts(found, tr))).style("white-space: pre-line")
        card.on("click", lambda _, k=key: select(k)).mark(f"tile-{key}")

    def draw_add_button(lane, column, keys):
        tr = state.tr

        with ui.button(tr("board.add"), icon="add").props("outline no-caps dense").classes("w-full text-grey-8").mark(
                f"add-{lane}-{column}"):
            with ui.menu():
                for key in keys:
                    ui.menu_item(component_label(tr, key), on_click=lambda _, k=key: add_component(k)).mark(f"add-{key}")

    @ui.refreshable
    def board():
        """The lanes (electricity, heat, gas) with a tile for each component and an Add button where more fits."""

        tr = state.tr
        components = state.draft.components()
        by_key = {component.template: component for component in components}
        problems = findings_by_component(chrome["list"], components)
        columns = "84px repeat(4, minmax(0, 1fr))"

        ui.label(tr("board.title")).classes("text-xl font-semibold")
        ui.label(tr("board.hint")).classes("text-grey")

        with ui.element("div").classes("w-full overflow-x-auto"):
            with ui.column().classes("gap-3").style("min-width: 760px"):
                with ui.grid(columns=columns).classes("w-full gap-4 q-px-md"):
                    ui.label()
                    for column in COLUMNS:
                        ui.label(tr(COLUMN_TEXTS[column])).classes("text-xs font-semibold text-grey").style(
                            "text-transform: uppercase").mark(f"column-{column}")

                for lane in LANES:
                    with ui.card().props("flat bordered").classes("w-full").mark(f"lane-{lane}"):
                        with ui.grid(columns=columns).classes("w-full gap-4 items-start"):
                            with ui.row().classes("items-center no-wrap gap-2 q-pt-xs"):
                                ui.element("span").style(
                                    f"width:10px;height:10px;border-radius:50%;background:{LANE_COLORS[lane]}")
                                ui.label(bus_label(tr, lane)).classes("font-semibold")
                            for column in COLUMNS:
                                with ui.column().classes("w-full gap-2"):
                                    for key in BOARD[lane][column]:
                                        if key in by_key:
                                            draw_tile(by_key[key], problems[key])
                                    free = addable(lane, column, by_key)
                                    if free:
                                        draw_add_button(lane, column, free)

    @ui.refreshable
    def component_problems(key):
        """What the check says about one component, at the top of its settings."""

        tr = state.tr
        found = findings_by_component(chrome["list"], state.draft.components()).get(key, [])
        if not found:
            return

        with ui.card().props("flat bordered").classes("w-full gap-1").mark(f"problems-{key}"):
            ui.label(tr("drawer.problems")).classes("font-semibold")
            for level, text in problem_texts(found, tr):
                symbol, symbol_color = ("error", "negative") if level == "error" else ("warning", "warning")
                with ui.row().classes("items-start gap-2 no-wrap"):
                    ui.icon(symbol, color=symbol_color)
                    ui.label(text)

    @ui.refreshable
    def settings():
        """The side sheet: the settings of the component that is open. Every component has its panel, and the browser
        shows only the one that is open (the others stay in the page, so that nothing typed is lost). The sheet is
        at the edge of the window with a height of its own, so a long form scrolls in it and not in the page."""

        tr = state.tr
        state.drop_stale_uploads()
        components = state.draft.components()
        if state.selected not in {component.template for component in components}:
            state.selected = None

        with ui.tab_panels(value=state.selected or NO_COMPONENT).classes("w-full bg-transparent").mark("drawer") as panels:
            with ui.tab_panel(NO_COMPONENT).classes("q-pa-none").mark("drawer-empty"):
                pass                                    # nothing is open: the side sheet is closed

            for component in components:
                if not has_form(component):
                    continue
                key = component.template
                with ui.tab_panel(key).classes("q-pa-none gap-2").mark(f"drawer-{key}"):
                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button(
                            tr("drawer.remove"), icon="delete_outline", on_click=lambda _, k=key: remove_component(k),
                        ).props("flat dense no-caps color=negative").mark(f"drawer-remove-{key}")
                        ui.button(icon="close", on_click=lambda: select(None)).props("flat round dense").mark(
                            "drawer-close").tooltip(tr("common.close"))
                    component_problems(key)
                    render_component_form(component, tr, on_change=overview.refresh, state=state)
        chrome["panels"] = panels

        sheet = chrome["sheet"]
        if sheet is not None and not sheet.is_deleted:
            sheet.set_value(state.selected is not None)         # open while a component is open

    def show_selection_in_boxes():
        for key, box in boxes.items():
            box.value = state.draft.is_selected(key)
        settings.refresh()
        overview.refresh()

    def add_components(keys):
        """The repair of a finding: add the missing components (with their standard settings)."""

        for key in keys:
            state.draft.set(key, True)
        show_selection_in_boxes()

    def on_tick(key, event):
        # also called when a template sets a box; then nothing is left to do
        if state.draft.is_selected(key) != event.value:
            state.draft.set(key, event.value)
            settings.refresh()
            overview.refresh()

    def use_template(name):
        state.draft.apply_template(name)
        show_selection_in_boxes()           # the board shows what is missing; a click on a tile opens a component

    def clear_selection():
        state.draft.clear()                 # (settings() closes the drawer: its component is gone)
        state.draft_run = None          # whoever starts again does not want the result of the old system
        show_selection_in_boxes()      # (the empty overview draws the results again: they are gone with the run)

    def builder_card():
        tr, draft = state.tr, state.draft
        boxes.clear()

        # open while nothing is chosen; the board is the way to add and open components after that
        with ui.expansion(tr("builder.heading"), icon="tune", value=len(draft) == 0).props("dense").classes(
                "w-full bg-white rounded-borders").style("border: 1px solid #DDE3EA").mark("builder"):
            ui.label(tr("builder.intro"))

            with ui.row().classes("w-full gap-2"):
                for name in SYSTEM_TEMPLATES:
                    ui.button(template_label(tr, name), on_click=lambda _, n=name: use_template(n)).props(
                        "outline dense no-caps").mark(f"template-{slug(name)}")
                ui.button(tr("builder.clear"), on_click=lambda _: clear_selection()).props(
                    "flat dense no-caps").mark("clear-selection")

            with ui.row().classes("w-full gap-8"):
                for group, keys in components_by_group().items():
                    with ui.column().classes("gap-0"):
                        ui.label(group_label(tr, group)).classes("font-semibold")
                        for key in keys:
                            boxes[key] = ui.checkbox(
                                component_label(tr, key), value=draft.is_selected(key),
                                on_change=lambda event, k=key: on_tick(k, event),
                            ).mark(f"component-{key}")

    # ----- open a scenario file and run it ---------------------------------

    @ui.refreshable
    def run_panel():
        tr = state.tr

        with ui.card().classes("w-full"):
            ui.label(tr("run.heading")).classes("text-xl font-semibold")
            ui.label(tr("run.intro"))

            with ui.row().classes("items-center gap-4"):
                here = state.running and not state.running_draft          # the run of the opened file
                button = ui.button(tr("run.button"), icon="play_arrow", on_click=start).mark("run")
                button.set_enabled(not state.running)
                spinner = ui.spinner(size="lg")
                spinner.visible = here
                running_clock(here, "run-clock")

        with ui.column().classes("w-full gap-4").mark("results"):
            if state.run_error is not None:
                ui.label(tr.message(state.run_error)).classes("text-negative").mark("run-error")
            elif state.result is not None:
                show_result(state.result, tr)

    async def start():
        started = state.start_run()
        if started is None:
            return

        if state.language_toggle is not None:
            state.language_toggle.disable()
        run_panel.refresh()
        overview.refresh()              # one run at a time: the button of the draft is blocked too

        result, failure = await execute(started.scenario)

        state.finish_run(started, result=result, error=failure)

        if state.language_toggle is not None and not state.language_toggle.is_deleted:
            state.language_toggle.enable()
        run_panel.refresh()
        overview.refresh()

    def open_card():
        tr = state.tr

        with ui.card().classes("w-full"):
            ui.label(tr("open.heading")).classes("text-xl font-semibold")
            ui.label(tr("open.intro"))

            async def open_file(event: events.UploadEventArguments):
                content = await event.file.read()
                event.sender.reset()            # ready for the next file
                state.open_file(content, event.file.name)
                details.refresh()

            ui.upload(
                label=tr("open.upload"),
                on_upload=open_file,
                auto_upload=True,
                max_files=1,
            ).props("accept=.json flat bordered").classes("w-full").mark("upload")

    @ui.refreshable
    def details():
        tr = state.tr

        if state.file_error is not None:
            ui.label(tr.message(state.file_error)).classes("text-negative").mark("file-error")
            return

        if state.opened is None:
            return

        scenario = state.opened.scenario

        with ui.card().classes("w-full"):
            ui.label(scenario.name).classes("text-xl font-semibold").mark("scenario-name")
            ui.label(tr("opened.file", name=state.opened.file_name)).classes("text-grey")
            ui.label(tr("scenario.period", period=describe_period(scenario, tr)))
            ui.label(tr("opened.solver", name=solver_label(scenario.solver.name)))

            ui.label(tr("opened.components")).classes("font-semibold mt-2")
            ui.table(columns=component_columns(tr), rows=component_rows(scenario, tr)).props(
                "dense flat").classes("w-full").mark("components")

            if scenario.series:
                ui.label(tr("opened.series")).classes("font-semibold mt-2")
                ui.table(columns=series_columns(tr), rows=series_rows(scenario, tr)).props(
                    "dense flat").classes("w-full").mark("series")

        findings = service_v2.check(scenario)
        show_findings(findings, tr)

        if not any(f.level == "error" for f in findings):
            run_panel()

    # ----- the page --------------------------------------------------------

    def system_view():
        """Everything that describes the system: the period, the board of components, a file to open. (The settings
        of the component that is open are in the side sheet.)"""

        ui.label(state.tr("app.subtitle")).classes("text-grey")

        scenario_card()
        builder_card()

        with ui.column().classes("w-full gap-3"):
            board()

        open_card()
        details()

    @ui.refreshable
    def content():
        tr = state.tr

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
            with ui.tabs(value=state.view, on_change=lambda event: setattr(state, "view", event.value)).classes(
                    "w-full").mark("views") as tabs:
                ui.tab("system", tr("view.system")).mark("view-system")
                with ui.tab("check", tr("view.check")).mark("view-check"):
                    badge = ui.badge("0").props("floating").mark("check-badge")
                    badge.set_visibility(False)
                ui.tab("results", tr("view.results")).mark("view-results")
            chrome["tabs"], chrome["badge"] = tabs, badge

            with ui.tab_panels(tabs, value=state.view).classes("w-full"):
                with ui.tab_panel("system"):
                    system_view()
                with ui.tab_panel("check"):
                    overview()              # what was built and what the check finds
                with ui.tab_panel("results"):
                    draft_results()

    with ui.header().classes("bg-white text-dark items-center gap-4 no-wrap q-px-md").props("bordered"):
        header_left()
        ui.space()
        header_status()
        header_lang()

    # the side sheet on the right: closed until a component is open. On a window wider than 1500 px it makes room
    # for itself (the page gets narrower); on a narrower one it lies over the page, and a click outside closes it
    with ui.right_drawer(value=False, fixed=True, bordered=True).props("width=460 breakpoint=1500").classes("q-pa-md").mark(
            "drawer-sheet") as sheet:
        chrome["sheet"] = sheet
        settings()
    sheet.on_value_change(sheet_changed)

    content()


def run_server(port=8080, reload=False):
    """Start the web server (blocks until it is stopped)."""

    # the recommended way to start the processes of run.cpu_bound; the same on
    # every system (Windows and macOS always use it)
    run.process_pool_start_method = "spawn"

    ui.run(title=TITLE, port=port, reload=reload, show=False)