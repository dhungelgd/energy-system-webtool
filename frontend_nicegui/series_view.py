"""The time series of a component on the page (NiceGUI).

What happens with a file is decided in series_session.py (no NiceGUI there); this file only turns it
into the section "Time series" of the card of a component:

- a component that can also use a constant (the grid price, the COP) first asks: a constant or a
  time series;
- the series that is used now is summarized, and can be taken away;
- a file is chosen with an upload; then it is prepared: the sheet and the column, a preview, what
  the import found, which part of the file is used, the unit of a price, how a time step shorter
  than an hour is converted, and the import settings in a box that opens. The series is only used
  when the visitor says so, and the button is only there when it can be made.
"""

from nicegui import events, ui

from backend.series_input import PRICE_UNITS, has_series, is_optional, summarize
from backend.timeseries_import import import_text
from frontend_nicegui.series_bulk import BulkSession
from frontend_nicegui.series_session import START_FILE, START_SCENARIO, UploadSession
from frontend_nicegui.series_widgets import ACCEPT, notice_line, preview_block, settings_box, sheet_select


def render_series(component, state, tr, on_series_change):
    """The section 'Time series' of the card of a component. `on_series_change` is called when a series
    was used or taken away (the form and the check have to follow)."""

    key = component.id
    draft = state.draft

    def changed():
        section.refresh()
        on_series_change()
        state.refresh_bulk()                    # the card for the file with all the series shows what was taken over

    # ----- the choice between a constant and a series ------------------------

    def choose_mode(event):
        if event.value == "constant":
            draft.clear_series(key)
            state.uploads.pop(key, None)
            state.series_wanted.discard(key)
            changed()
        else:
            state.series_wanted.add(key)
            section.refresh()

    # ----- the series that is used -------------------------------------------

    def remove():
        draft.clear_series(key)
        state.uploads.pop(key, None)
        state.series_wanted.discard(key)
        changed()

    def summary(data):
        numbers = summarize(data)

        with ui.column().classes("gap-0").mark(f"series-summary-{key}"):
            if numbers.count > numbers.empty:
                ui.label(tr(
                    "series.summary", count=tr.integer(numbers.count), minimum=tr.number(numbers.minimum),
                    maximum=tr.number(numbers.maximum), total=tr.number(numbers.total),
                ))
            if numbers.empty:
                ui.label(tr.plural("series.summary_empty", numbers.empty)).classes("text-negative")
            if data.source is not None and data.source.file:
                ui.label(tr("series.source", file=data.source.file, column=data.source.column)).classes(
                    "text-grey text-sm")
            ui.button(tr("series.remove"), on_click=remove).props("flat dense no-caps").mark(f"series-remove-{key}")

    # ----- a file that is being prepared -------------------------------------

    async def receive(event: events.UploadEventArguments):
        content = await event.file.read()
        name = event.file.name
        event.sender.reset()                    # ready for the next file
        state.uploads[key] = UploadSession(content, name)
        section.refresh()

    def cancel():
        state.uploads.pop(key, None)
        section.refresh()

    def use(session):
        try:
            data = session.build(component, draft.start)
        except Exception:                       # noqa: BLE001 - the button is only there when it can be made
            section.refresh()
            return

        draft.set_series(key, data)
        state.uploads.pop(key, None)
        state.series_wanted.discard(key)
        changed()

    def decide(session, name, value):
        setattr(session, name, value)
        section.refresh()

    def prepare(session):
        with ui.card().classes("w-full").mark(f"series-prepare-{key}"):
            ui.label(tr("series.file", name=session.filename)).classes("font-medium")

            if not session.readable:
                ui.label(import_text(session.error, tr)).classes("text-negative").mark(f"series-error-{key}")
                ui.button(tr("series.cancel"), on_click=cancel).props("flat dense no-caps").mark(f"series-cancel-{key}")
                return

            sheet_select(session, tr, key, section.refresh)

            if session.columns():
                ui.select(
                    session.columns(), value=session.column, label=tr("series.column"),
                    on_change=lambda event: decide(session, "column", event.value),
                ).classes("w-full").mark(f"series-column-{key}")

            preview_block(session, tr, key)

            for notice in session.notices(component):
                notice_line(notice, tr)

            if session.has_dates():
                choice = session.start_choice_for(draft.start)
                if choice == START_FILE and session.start_choice is None:
                    # the file does not include the start of the scenario: there is nothing to choose
                    ui.label(tr("series.start.not_covered", start=draft.start.isoformat())).classes(
                        "text-grey text-sm").mark(f"series-start-note-{key}")
                else:
                    options = {
                        START_SCENARIO: tr("series.start.scenario", start=draft.start.isoformat()),
                        START_FILE: tr("series.start.file"),
                    }
                    ui.label(tr("series.start.label")).classes("font-medium")
                    ui.radio(
                        options, value=choice, on_change=lambda event: decide(session, "start_choice", event.value),
                    ).mark(f"series-start-{key}")

            if component.template == "grid":
                ui.select(
                    list(PRICE_UNITS), value=session.price_unit, label=tr("series.price_unit"),
                    on_change=lambda event: setattr(session, "price_unit", event.value),
                ).classes("w-full").mark(f"series-price-unit-{key}")

            if session.needs_aggregate(component):
                ui.label(tr("series.aggregate.label")).classes("font-medium")
                ui.radio(
                    {"mean": tr("series.aggregate.mean"), "sum": tr("series.aggregate.sum")},
                    value=session.aggregate, on_change=lambda event: decide(session, "aggregate", event.value),
                ).mark(f"series-aggregate-{key}")

            settings_box(session, tr, key, section.refresh)

            problem = session.problem(component, draft.start)
            if problem is not None:
                ui.label(import_text(problem, tr)).classes("text-negative").mark(f"series-problem-{key}")

            with ui.row().classes("gap-2"):
                if problem is None:
                    ui.button(tr("series.use"), on_click=lambda: use(session)).props("no-caps").mark(f"series-use-{key}")
                ui.button(tr("series.cancel"), on_click=cancel).props("flat no-caps").mark(f"series-cancel-{key}")

    # ----- a column of the file with all the series that fits ------------------

    def use_from_file():
        session = state.bulk
        if session is None or not session.apply(draft, [component]):
            section.refresh()
            return

        state.uploads.pop(key, None)
        state.series_wanted.discard(key)
        state.bulk_done = (1, session.filename)
        changed()

    def file_hint():
        """If the file with all the series has a column for this component that is not taken over yet: say so, and a
        button that takes it over."""

        session = state.bulk
        if session is None or not session.readable:
            return

        session.update(BulkSession.components_with_series(draft))
        column = session.mapping.get(component.template)
        if column is None or session.is_used(component.template, column, draft):
            return

        problem = session.results([component], draft.start)[component.template][1]
        with ui.row().classes("items-center gap-2").mark(f"series-bulk-hint-{key}"):
            ui.icon("lightbulb", color="primary")
            ui.label(tr("series.bulk_hint", file=session.filename, column=column))
            if problem is None:
                ui.button(tr("series.bulk_use", column=column), on_click=use_from_file).props(
                    "outline dense no-caps").mark(f"series-bulk-hint-use-{key}")
            else:
                ui.label(import_text(problem, tr)).classes("text-negative text-sm").mark(f"series-bulk-hint-problem-{key}")

    # ----- the section -------------------------------------------------------

    @ui.refreshable
    def section():
        ui.separator()
        ui.label(tr("series.heading")).classes("font-semibold")
        ui.label(tr(f"series.help.{key}")).classes("text-grey text-sm")

        if is_optional(component):
            mode = "series" if draft.uses_series(key) or key in state.series_wanted else "constant"
            ui.radio(
                {"constant": tr.own("series.mode.constant", key), "series": tr("series.mode.series")},
                value=mode, on_change=choose_mode,
            ).props("inline").mark(f"series-mode-{key}")
            if mode == "constant":
                return

        data = draft.series_of(key)
        if data is not None:
            summary(data)
        else:
            ui.label(tr("series.state.waiting" if is_optional(component) else "series.state.none")).classes(
                "text-grey").mark(f"series-state-{key}")

        file_hint()

        ui.upload(
            label=tr("series.upload"), on_upload=receive, auto_upload=True, max_files=1,
        ).props(f"accept={ACCEPT} flat bordered").classes("w-full").mark(f"series-upload-{key}")

        session = state.uploads.get(key)
        if session is not None:
            prepare(session)

    if has_series(component):
        section()