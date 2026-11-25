"""The area of the load profile: load a file, answer what the file does not say, and see what the profile says: the key
figures, the typical days, the duration curve, the months, the heat map, the seasons, the peaks and a few observations, and
what was read and what is wrong with it.
The reading is in backend/load_profile.py, the analysis in backend/load_analysis.py, the state of one file in
profile_session.py and the charts in analysis_charts.py; this file only builds the page."""

import logging
from datetime import timedelta

from nicegui import events, run, ui

from backend.holidays_de import DEFAULT_STATE
from backend.load_analysis import analysis_text
from backend.load_profile import UnitText, profile_text
from backend.timeseries_import import StepText
from frontend_nicegui.analysis_charts import (
    duration_figure,
    heatmap_figure,
    monthly_figure,
    seasonal_figure,
    typical_days_figure,
    weekday_figure,
)
from frontend_nicegui.analysis_view import (
    ALL_YEARS,
    CAP_MAX_SHARE,
    CAP_MIN_SHARE,
    cap_items,
    cap_limit,
    day_counts_text,
    kpi_items,
    near_peak_text,
    peak_rows,
    state_options,
    year_options,
)
from frontend_nicegui.chart_style import as_chart
from frontend_nicegui.profile_session import ProfileSession
from frontend_nicegui.series_widgets import ACCEPT

logger = logging.getLogger(__name__)

UNIT_ORDER = ("kW", "kWh", "W", "Wh", "MW", "MWh")                  # the units to choose from
NOTICE_ICONS = {"warning": ("warning", "warning"), "info": ("info", "primary")}
OVERVIEW, PATTERNS, PEAKS, QUALITY = "overview", "patterns", "peaks", "quality"         # the tabs of the analysis
PEAK_COLUMNS = {                                                                          # the columns of the table of peaks
    "rank": "analysis.peaks.col.rank", "date": "analysis.peaks.col.date", "time": "analysis.peaks.col.time",
    "power": "analysis.peaks.col.power", "daytype": "analysis.peaks.col.daytype", "season": "analysis.peaks.col.season",
}


def facts(profile, tr):
    """What was read, as (key, label, value) for the cards: the period, the time step, how many values, how many are
    missing, the energy and the highest power."""

    power = profile.power_kw
    shown = tr("profile.stamp_format")
    last_end = power.index[-1] + timedelta(minutes=profile.step_minutes)

    return [
        ("period", tr("profile.summary.period"),
         tr("profile.summary.period_value", start=power.index[0].strftime(shown), end=last_end.strftime(shown))),
        ("step", tr("profile.summary.step"), StepText(profile.step_minutes).render(tr)),
        ("values", tr("profile.summary.values"), tr.integer(len(power))),
        ("missing", tr("profile.summary.missing"), f"{tr.number(round(100 * profile.missing_share(), 1))} %"),
        ("energy", tr("profile.summary.energy"), f"{tr.integer(int(round(profile.energy_kwh())))} kWh"),
        ("peak", tr("profile.summary.peak"), f"{tr.number(round(profile.peak_kw(), 1))} kW"),
    ]


def make_profile_view(state):
    """The refreshable view of the area. It is drawn again when a file is loaded, answered or removed, and when a choice of
    the analysis is changed."""

    async def work(session, job):
        """Run `job` (reading or analysing) in a thread; if it breaks in a way that was not foreseen, tell it and go on."""

        try:
            await run.io_bound(job)
        except Exception:  # noqa: BLE001 - the page must stay alive whatever happens
            logger.exception("The load profile could not be read")
            session.failed = True
            session.profile = None
            session.error = None
            session.analysis = None

    async def read(session):
        state.profile_reading = True
        view.refresh()
        try:
            await work(session, session.read)
        finally:
            state.profile_reading = False
        view.refresh()

    async def reanalyse(session, **choices):
        try:
            session.choose_analysis(**choices)
        except ValueError:
            return
        state.profile_analysing = True
        view.refresh()
        try:
            await work(session, session.analyse)
        finally:
            state.profile_analysing = False
        view.refresh()

    async def receive(event: events.UploadEventArguments):
        content = await event.file.read()
        name = event.file.name
        state.profile = ProfileSession(content, name)
        state.profile_tab = OVERVIEW
        await read(state.profile)

    def remove():
        state.profile = None
        view.refresh()

    def upload_card(session):
        tr = state.tr

        with ui.card().classes("w-full gap-3"):
            if session is not None:
                with ui.row().classes("items-center gap-3"):
                    ui.icon("description", color="primary")
                    ui.label(tr("profile.file", name=session.filename)).classes("font-semibold").mark("profile-file")
                    ui.button(tr("profile.another"), on_click=remove).props("flat no-caps dense").mark("profile-remove")
                return

            ui.upload(label=tr("profile.upload"), on_upload=receive, auto_upload=True, max_files=1).props(
                f"accept={ACCEPT} flat bordered").classes("w-full").mark("profile-upload")

    def questions_card(session):
        """What the file does not say, and the settings that can be changed. Only what the visitor touches is a decision."""

        tr, profile = state.tr, session.profile
        touched = {}

        def touch(name):
            return lambda event: touched.__setitem__(name, event.value)

        async def apply():
            wanted = {"value_column": "value_column", "unit": "unit", "energy": "energy_kwh"}
            missing = [need for need in profile.needs if wanted[need] not in touched]
            if missing:
                ui.notify(tr("profile.ask.incomplete"), type="warning")
                return
            energy = touched.get("energy_kwh")
            if "energy_kwh" in touched and not (energy is not None and energy > 0):
                ui.notify(tr("profile.ask.energy_invalid"), type="warning")
                return

            session.decide(**touched)
            await read(session)

        with ui.card().classes("w-full gap-3").mark("profile-settings"):
            ui.label(tr("profile.ask.title")).classes("text-xl font-semibold")
            if profile.needs:
                ui.label(tr("profile.ask.hint")).classes("text-warning").mark("profile-ask-hint")

            with ui.row().classes("w-full items-start gap-4"):
                if len(profile.candidates) > 1:
                    ui.select(
                        [c.name for c in profile.candidates], value=profile.value_column, label=tr("profile.ask.column"),
                        on_change=touch("value_column"),
                    ).props("outlined dense").classes("min-w-[16rem]").mark("profile-ask-column")

                if profile.value_column is not None and profile.unit != "share":
                    ui.select(
                        {unit: UnitText(unit).render(tr) for unit in UNIT_ORDER}, value=profile.unit,
                        label=tr("profile.ask.unit"), on_change=touch("unit"),
                    ).props("outlined dense").classes("min-w-[22rem]").mark("profile-ask-unit")

                if profile.unit == "share":
                    ui.number(
                        tr("profile.ask.energy"), value=session.choices.get("energy_kwh"), min=0, on_change=touch("energy_kwh"),
                    ).props("outlined dense").classes("min-w-[22rem]").mark("profile-ask-energy")

                if profile.value_column is not None:
                    with ui.column().classes("gap-1"):
                        ui.label(tr("profile.ask.stamp")).classes("text-sm text-grey")
                        ui.toggle(
                            {"start": tr("profile.ask.stamp.start"), "end": tr("profile.ask.stamp.end")},
                            value=profile.stamp_at, on_change=touch("stamp_at"),
                        ).props("dense no-caps").mark("profile-ask-stamp")

            if profile.preview:
                ui.label(tr(
                    "profile.ask.preview", power=tr.integer(int(round(profile.preview["as_power_kwh"]))),
                    energy=tr.integer(int(round(profile.preview["as_energy_kwh"]))))).classes("text-grey text-sm").mark(
                    "profile-ask-preview")

            ui.button(tr("profile.ask.apply"), on_click=apply).props("no-caps color=primary").mark("profile-ask-apply")

    def summary_card(profile):
        tr = state.tr

        with ui.row().classes("w-full gap-4").mark("profile-summary"):
            for key, label, value in facts(profile, tr):
                with ui.card().classes("min-w-[11rem]").mark(f"profile-fact-{key}"):
                    ui.label(label).classes("text-grey text-sm")
                    ui.label(value).classes("text-lg font-semibold")

    def notes_card(profile):
        tr = state.tr

        with ui.card().classes("w-full gap-2").mark("profile-notes"):
            ui.label(tr("profile.notes.title")).classes("text-xl font-semibold")
            for notice in profile.notices:
                icon, color = NOTICE_ICONS.get(notice[0], NOTICE_ICONS["info"])
                with ui.row().classes("items-start gap-2 no-wrap").mark(f"profile-note-{getattr(notice, 'code', 'import')}"):
                    ui.icon(icon, color=color)
                    ui.label(profile_text(notice, tr))

    # ----- the analysis -------------------------------------------------------

    def settings_row(session):
        """The choices that the analysis depends on: whose holidays count, and which period."""

        tr = state.tr
        choices = session.analysis_choices
        chosen_state = choices.get("state", DEFAULT_STATE)
        years = year_options(session.years(), tr)

        async def choose_state(event):
            if event.value != chosen_state:
                await reanalyse(session, state=event.value)

        async def choose_catholic(event):
            if event.value != choices.get("catholic_municipality", True):
                await reanalyse(session, catholic_municipality=event.value)

        async def choose_year(event):
            year = None if event.value == ALL_YEARS else int(event.value)
            if year != choices.get("year"):
                await reanalyse(session, year=year)

        with ui.row().classes("w-full items-center gap-4").mark("analysis-settings"):
            ui.select(
                state_options(tr), value=chosen_state, label=tr("analysis.settings.state"), on_change=choose_state,
            ).props("outlined dense").classes("min-w-[16rem]").mark("analysis-state")
            if chosen_state == "BY":
                ui.checkbox(
                    tr("analysis.settings.catholic"), value=choices.get("catholic_municipality", True), on_change=choose_catholic,
                ).mark("analysis-catholic")
            if years:
                current = choices.get("year")
                ui.select(
                    years, value=ALL_YEARS if current is None else str(current), label=tr("analysis.settings.period"),
                    on_change=choose_year,
                ).props("outlined dense").classes("min-w-[12rem]").mark("analysis-year")

        ui.label(tr("analysis.settings.hint")).classes("text-grey text-sm").mark("analysis-settings-hint")

    def kpi_cards(analysis):
        tr = state.tr

        with ui.row().classes("w-full gap-4").mark("analysis-kpis"):
            for item in kpi_items(analysis, tr):
                with ui.card().classes("flex-1 gap-1").style("min-width: 12rem").mark(f"analysis-kpi-{item['key']}"):
                    ui.label(item["label"]).classes("text-grey text-sm")
                    ui.label(item["value"]).classes("text-xl font-semibold")
                    if item["sub"]:
                        ui.label(item["sub"]).classes("text-grey text-xs")
                    ui.tooltip(item["help"]).classes("text-body2")

    def chart_card(marker, title, hint, figure, name, none_text=None, wide=False):
        with ui.card().classes("w-full gap-2" if wide else "flex-1 gap-2").style("min-width: 26rem").mark(f"analysis-card-{marker}"):
            ui.label(title).classes("text-xl font-semibold")
            ui.label(hint).classes("text-grey text-sm")
            if figure is None:
                ui.label(none_text).classes("text-grey").mark(f"analysis-{marker}-none")
            else:
                ui.plotly(as_chart(figure, name)).classes("w-full").mark(f"analysis-{marker}")

    def hints_card(analysis):
        tr = state.tr

        with ui.card().classes("flex-1 gap-3").style("min-width: 22rem").mark("analysis-hints"):
            ui.label(tr("analysis.hints.title")).classes("text-xl font-semibold")
            for hint in analysis.hints:
                with ui.row().classes("items-start gap-2 no-wrap").mark(f"analysis-hint-{hint.code}"):
                    ui.icon("lightbulb", color="primary")
                    ui.label(analysis_text(hint, tr))

    def overview(analysis):
        tr = state.tr

        with ui.row().classes("w-full gap-6 items-stretch"):
            chart_card("typical", tr("analysis.chart.typical_title"), tr("analysis.chart.typical_hint"),
                       typical_days_figure(analysis, tr), "typical-days", tr("analysis.chart.typical_none"))
            chart_card("duration", tr("analysis.chart.duration_title"), tr("analysis.chart.duration_hint"),
                       duration_figure(analysis, tr), "duration-curve")
        with ui.row().classes("w-full gap-6 items-stretch"):
            chart_card("monthly", tr("analysis.chart.monthly_title"), tr("analysis.chart.monthly_hint"),
                       monthly_figure(analysis, tr), "months")
            hints_card(analysis)

    def patterns(analysis):
        """How the load goes over the period, the seasons and the weekdays. The heat map is heavy, so this is built only while
        its tab is open."""

        tr = state.tr

        chart_card("heatmap", tr("analysis.chart.heatmap_title"), tr("analysis.chart.heatmap_hint"),
                   heatmap_figure(analysis, tr), "heatmap", wide=True)
        chart_card("seasonal", tr("analysis.chart.seasonal_title"), tr("analysis.chart.seasonal_hint"),
                   seasonal_figure(analysis, tr), "seasonal-days", tr("analysis.chart.seasonal_none"), wide=True)
        ui.label(day_counts_text(analysis, tr)).classes("text-grey text-sm").mark("analysis-day-counts")
        chart_card("weekday", tr("analysis.chart.weekday_title"), tr("analysis.chart.weekday_hint"),
                   weekday_figure(analysis, tr), "weekdays", wide=True)

    def peaks(analysis):
        """The highest peaks, how rare the highest values are, and what is above a limit that the visitor chooses."""

        tr = state.tr

        @ui.refreshable
        def capping_view():
            share = state.profile_cap_share
            ui.plotly(as_chart(duration_figure(analysis, tr, limit_kw=cap_limit(analysis, share)), "duration-capped")).classes(
                "w-full").mark("analysis-cap-chart")
            with ui.row().classes("w-full gap-4").mark("analysis-cap-items"):
                for item in cap_items(analysis, share, tr):
                    with ui.card().classes("flex-1 gap-1").style("min-width: 12rem").mark(f"analysis-cap-{item['key']}"):
                        ui.label(item["label"]).classes("text-grey text-sm")
                        ui.label(item["value"]).classes("text-lg font-semibold")

        def change_share(event):
            state.profile_cap_share = int(event.value)
            capping_view.refresh()

        columns = [{"name": name, "label": tr(key), "field": name, "align": "left"} for name, key in PEAK_COLUMNS.items()]

        with ui.card().classes("w-full gap-2").mark("analysis-card-peaks"):
            ui.label(tr("analysis.peaks.table_title")).classes("text-xl font-semibold")
            ui.label(tr("analysis.peaks.table_hint")).classes("text-grey text-sm")
            ui.table(columns=columns, rows=peak_rows(analysis, tr), row_key="rank").props("flat dense").classes("w-full").mark(
                "analysis-peaks-table")
            ui.label(near_peak_text(analysis, tr)).classes("text-grey").mark("analysis-peaks-near")

        with ui.card().classes("w-full gap-2").mark("analysis-card-cap"):
            ui.label(tr("analysis.peaks.cap_title")).classes("text-xl font-semibold")
            ui.label(tr("analysis.peaks.cap_hint")).classes("text-grey text-sm")
            ui.label(tr("analysis.peaks.cap_slider")).classes("text-sm")
            ui.slider(min=CAP_MIN_SHARE, max=CAP_MAX_SHARE, step=1, value=state.profile_cap_share, on_change=change_share).props(
                "label-always").classes("w-full").mark("analysis-cap-slider")
            capping_view()
            ui.label(tr("analysis.peaks.cap_note")).classes("text-grey text-sm").mark("analysis-cap-note")

    def quality(session):
        """What was read, the details of the file that can be changed, and the notes of the check."""

        summary_card(session.profile)
        questions_card(session)
        notes_card(session.profile)

    def analysis_block(session):
        tr = state.tr
        settings_row(session)

        if session.analysis is None:
            ui.label(tr("analysis.error")).classes("text-negative").mark("analysis-error")
            quality(session)
            return

        kpi_cards(session.analysis)
        warnings = sum(1 for notice in session.profile.notices if notice[0] == "warning")

        def switch_tab(event):
            opening_patterns = event.value == PATTERNS and state.profile_tab != PATTERNS
            state.profile_tab = event.value
            if opening_patterns:
                view.refresh()                          # the patterns are built now, not before

        with ui.tabs(value=state.profile_tab, on_change=switch_tab).classes("w-full").mark("analysis-tabs") as tabs:
            ui.tab(OVERVIEW, tr("analysis.tab.overview")).mark("analysis-tab-overview")
            ui.tab(PATTERNS, tr("analysis.tab.patterns")).mark("analysis-tab-patterns")
            ui.tab(PEAKS, tr("analysis.tab.peaks")).mark("analysis-tab-peaks")
            with ui.tab(QUALITY, tr("analysis.tab.quality")).mark("analysis-tab-quality"):
                if warnings:
                    ui.badge(str(warnings)).props("color=warning floating").mark("analysis-quality-badge")

        with ui.tab_panels(tabs, value=state.profile_tab).classes("w-full gap-4"):
            with ui.tab_panel(OVERVIEW).classes("gap-4").mark("analysis-panel-overview"):
                overview(session.analysis)
            with ui.tab_panel(PATTERNS).classes("gap-4").mark("analysis-panel-patterns"):
                if state.profile_tab == PATTERNS:
                    patterns(session.analysis)
            with ui.tab_panel(PEAKS).classes("gap-4").mark("analysis-panel-peaks"):
                peaks(session.analysis)
            with ui.tab_panel(QUALITY).classes("gap-4").mark("analysis-panel-quality"):
                quality(session)

    @ui.refreshable
    def view():
        tr = state.tr
        session = state.profile

        ui.label(tr("profile.page.title")).classes("text-h4 text-weight-bold").mark("profile-title")
        ui.label(tr("profile.page.intro")).classes("text-grey-8").mark("profile-intro")

        upload_card(session)
        if session is None:
            return

        if state.profile_reading:
            with ui.row().classes("items-center gap-3").mark("profile-reading"):
                ui.spinner()
                ui.label(tr("profile.reading"))
        elif state.profile_analysing:
            with ui.row().classes("items-center gap-3").mark("profile-analysing"):
                ui.spinner()
                ui.label(tr("analysis.analysing"))
        elif session.failed:
            ui.label(tr("profile.unexpected")).classes("text-negative").mark("profile-failed")
        elif session.error is not None:
            ui.label(profile_text(session.error, tr)).classes("text-negative").mark("profile-error")
        elif session.profile is not None:
            if session.ready:
                analysis_block(session)
            else:
                questions_card(session)
                notes_card(session.profile)

    return view