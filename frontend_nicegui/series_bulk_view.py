"""The card 'All time series from one file' on the page (NiceGUI).

What happens with the file and the columns is decided in series_bulk.py (no NiceGUI there); this file only turns it
into the card of the system view. The file can be uploaded at any time, also before any component is chosen, and it
stays until the visitor removes it or uploads another: it shows what the file holds (the period and a row for each
column with what it looks like), offers to add the components that the columns look like and to take the period of
the file, and, for the components that there are, a row with a column to choose and what it gives. The button gives
every assigned component its series, as often as it is pressed: what was taken over is marked, and a component that
is added later takes its column from the same file. The upload of a single series in the settings of a component stays.
"""

from nicegui import events, ui

from backend.series_input import PRICE_UNITS
from backend.timeseries_import import import_text
from frontend_nicegui.draft import MAX_STEPS
from frontend_nicegui.names import component_label, display_name
from frontend_nicegui.series_bulk import BulkSession
from frontend_nicegui.series_session import START_FILE, START_SCENARIO
from frontend_nicegui.series_widgets import ACCEPT, notice_line, preview_block, settings_box, sheet_select

NO_COLUMN = "__none__"                      # the choice 'no column' in a selection (the columns are texts too)


def render_bulk(state, tr, on_series_change, on_components, on_period):
    """The card, as a refreshable that is also given to the state of the page (the settings of a component draw it
    again after a series was taken over there).

    `on_series_change()` is called when something changed that the forms and the check show (the file, an
    assignment, series that were taken over). `on_components(keys)` adds components to the draft, and
    `on_period(start, hours)` sets the period of the scenario (`start` is an ISO date, or None to keep it).
    """

    draft = state.draft

    def changed():
        card.refresh()
        on_series_change()

    # ----- the file ----------------------------------------------------------

    async def receive(event: events.UploadEventArguments):
        content = await event.file.read()
        name = event.file.name
        event.sender.reset()                    # ready for the next file
        state.bulk = BulkSession(content, name)
        state.bulk_done = None
        changed()

    def remove_file():
        state.bulk = None
        changed()

    def decide(name, value):
        """A choice for the whole file (the unit of a price, how the hours are made, which part is used)."""

        setattr(state.bulk.master, name, value)
        changed()

    def choose(key, value):
        state.bulk.choose(key, None if value == NO_COLUMN else value)
        changed()

    def use(components):
        session = state.bulk
        done = session.apply(draft, components)
        for key in done:                         # a file that was being prepared for such a component is out of date now
            state.uploads.pop(key, None)
            state.series_wanted.discard(key)
        state.bulk_done = (len(done), session.filename)
        changed()

    def take_period(period):
        on_period(period.start.date().isoformat() if period.start is not None else None, period.hours)
        card.refresh()

    # ----- what the file holds -----------------------------------------------

    def overview(session):
        """The period of the file, a row for each column, and what can be done with that."""

        period = session.period()

        ui.label(tr("bulk.overview.heading")).classes("text-lg font-semibold")
        if period.start is not None:
            ui.label(tr(
                "bulk.overview.period", start=f"{period.start:%Y-%m-%d %H:%M}", end=f"{period.end:%Y-%m-%d %H:%M}",
                hours=tr.integer(period.hours),
            )).mark("series-bulk-period-info")
        else:
            ui.label(tr("bulk.overview.length", hours=tr.integer(period.hours))).mark("series-bulk-period-info")

        rows = [{
            "column": row["column"], "values": tr.integer(row["values"]),
            "kind": component_label(tr, row["kind"]) if row["kind"] is not None else tr("bulk.kind.unknown"),
        } for row in session.overview()]
        ui.table(
            columns=[
                {"name": "column", "label": tr("bulk.col.column"), "field": "column", "align": "left"},
                {"name": "values", "label": tr("bulk.col.values"), "field": "values", "align": "right"},
                {"name": "kind", "label": tr("bulk.col.kind"), "field": "kind", "align": "left"},
            ],
            rows=rows, row_key="column",
        ).props("dense flat").classes("w-full").mark("series-bulk-columns")

        with ui.row().classes("items-center gap-3"):
            period_action(session, period)
            suggested = session.suggested_components(draft)
            if suggested:
                names = ", ".join(component_label(tr, key) for key in suggested)
                ui.button(
                    tr.plural("bulk.add", len(suggested), names=names), icon="add", on_click=lambda: on_components(suggested),
                ).props("outline no-caps").mark("series-bulk-add-components")

    def period_action(session, period):
        """Take the period of the file for the scenario: a button, or a word why not (it is the same already, or too long)."""

        if period.hours > MAX_STEPS:
            ui.label(tr("bulk.period.too_long", hours=tr.integer(period.hours), max=tr.integer(MAX_STEPS))).classes(
                "text-grey text-sm").mark("series-bulk-period-note")
        elif draft.steps == period.hours and (period.start is None or draft.start == period.start.date()):
            ui.label(tr("bulk.period.same")).classes("text-grey text-sm").mark("series-bulk-period-note")
        elif period.start is not None:
            ui.button(
                tr("bulk.period.use", start=period.start.date().isoformat(), hours=tr.integer(period.hours)),
                icon="event", on_click=lambda: take_period(period),
            ).props("outline no-caps").mark("series-bulk-period")
        else:
            ui.button(
                tr("bulk.period.use_length", hours=tr.integer(period.hours)), icon="event",
                on_click=lambda: take_period(period),
            ).props("outline no-caps").mark("series-bulk-period")

    # ----- the assignment ----------------------------------------------------

    def row(component, session, result):
        key = component.template
        column = session.mapping.get(key)
        name = display_name(component, tr)

        with ui.row().classes("w-full items-start gap-4"):
            ui.label(name).classes("font-medium w-56 q-pt-sm")
            ui.select(
                {NO_COLUMN: tr("bulk.map.none"), **{c: c for c in session.columns()}},
                value=NO_COLUMN if column is None else column, label=tr("bulk.map.column", name=name),
                on_change=lambda event, k=key: choose(k, event.value),
            ).classes("w-72").mark(f"series-bulk-map-{key}")

            with ui.column().classes("gap-0 q-pt-sm").mark(f"series-bulk-status-{key}"):
                if result is None:
                    ui.label(tr("bulk.status.none")).classes("text-grey text-sm")
                    return
                if session.is_used(key, column, draft):
                    with ui.row().classes("items-center gap-1 no-wrap"):
                        ui.icon("check_circle", color="positive")
                        ui.label(tr("bulk.status.used"))
                    return
                data, problem = result
                if problem is not None:
                    ui.label(import_text(problem, tr)).classes("text-negative text-sm")
                    return
                with ui.row().classes("items-center gap-1 no-wrap"):
                    ui.icon("check_circle", color="positive")
                    ui.label(tr("bulk.status.ok", count=tr.integer(len(data.values))))
                for notice in session.notices(component, column):
                    if notice.level == "warning":
                        notice_line(notice, tr)

    def whole_file_choices(session, components):
        """The choices that are for the file as a whole: only those that the assigned columns need."""

        assigned = [component.template for component, _ in session.assigned(components)]
        master = session.master

        if "grid" in assigned:
            ui.select(
                list(PRICE_UNITS), value=master.price_unit, label=tr("series.price_unit"),
                on_change=lambda event: decide("price_unit", event.value),
            ).classes("w-72").mark("series-price-unit-bulk")

        if session.needs_aggregate(components):
            ui.label(tr("series.aggregate.label")).classes("font-medium")
            ui.radio(
                {"mean": tr("series.aggregate.mean"), "sum": tr("series.aggregate.sum")},
                value=master.aggregate, on_change=lambda event: decide("aggregate", event.value),
            ).mark("series-aggregate-bulk")

        if master.has_dates():
            choice = master.start_choice_for(draft.start)
            if choice == START_FILE and master.start_choice is None:
                ui.label(tr("series.start.not_covered", start=draft.start.isoformat())).classes(
                    "text-grey text-sm").mark("series-start-note-bulk")
            else:
                ui.label(tr("series.start.label")).classes("font-medium")
                ui.radio(
                    {START_SCENARIO: tr("series.start.scenario", start=draft.start.isoformat()),
                     START_FILE: tr("series.start.file")},
                    value=choice, on_change=lambda event: decide("start_choice", event.value),
                ).mark("series-start-bulk")

    def assignment(session, components):
        """A row for each component that has a time series, the choices for the file, and the button."""

        ui.label(tr("bulk.map.heading")).classes("text-lg font-semibold")
        results = session.results(components, draft.start)
        for component in components:
            row(component, session, results.get(component.template))

        whole_file_choices(session, components)
        settings_box(session.master, tr, "bulk", card.refresh)

        pending = session.pending(components, draft)
        with ui.row().classes("gap-2 items-center"):
            if session.usable(components, draft):
                ui.button(
                    tr.plural("bulk.use", len(pending)), on_click=lambda: use(components),
                ).props("no-caps").mark("series-bulk-use")
            elif not results:
                ui.label(tr("bulk.nothing")).classes("text-grey").mark("series-bulk-nothing")
            elif not pending:
                ui.label(tr("bulk.all_used")).classes("text-grey").mark("series-bulk-all-used")

    def prepare(session, components):
        session.update(components)

        with ui.card().props("flat bordered").classes("w-full").mark("series-bulk-prepare"):
            ui.label(tr("series.file", name=session.filename)).classes("font-medium")

            if not session.readable:
                ui.label(import_text(session.error, tr)).classes("text-negative").mark("series-bulk-error")
                ui.button(tr("bulk.remove"), on_click=remove_file).props("flat dense no-caps").mark("series-bulk-remove")
                return

            sheet_select(session.master, tr, "bulk", card.refresh)
            overview(session)
            preview_block(session.master, tr, "bulk")
            for notice in session.master.table.messages:
                notice_line(notice, tr)

            if components:
                assignment(session, components)
            else:
                ui.label(tr("bulk.no_components")).classes("text-grey").mark("series-bulk-empty")
                settings_box(session.master, tr, "bulk", card.refresh)

            ui.button(tr("bulk.remove"), on_click=remove_file).props("flat dense no-caps").mark("series-bulk-remove")

    # ----- the card ----------------------------------------------------------

    @ui.refreshable
    def card():
        components = BulkSession.components_with_series(draft)

        with ui.card().classes("w-full").mark("series-bulk"):
            ui.label(tr("bulk.heading")).classes("text-xl font-semibold")
            ui.label(tr("bulk.intro"))

            if state.bulk_done is not None:
                count, file = state.bulk_done
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.icon("check_circle", color="positive")
                    ui.label(tr.plural("bulk.done", count, file=file)).mark("series-bulk-done")

            ui.upload(
                label=tr("bulk.upload"), on_upload=receive, auto_upload=True, max_files=1,
            ).props(f"accept={ACCEPT} flat bordered").classes("w-full").mark("series-bulk-upload")

            if state.bulk is not None:
                prepare(state.bulk, components)

    card()
    state.bulk_card = card

    return card