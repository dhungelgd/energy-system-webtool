"""The area of the load profile: load a file, answer what the file does not say, and see what was read and what is wrong
with it. The reading itself is in backend/load_profile.py and the state of one file in profile_session.py; this file
only builds the page."""

import logging
from datetime import timedelta

from nicegui import events, run, ui

from backend.load_profile import UnitText, profile_text
from backend.timeseries_import import StepText
from frontend_nicegui.profile_session import ProfileSession
from frontend_nicegui.series_widgets import ACCEPT

logger = logging.getLogger(__name__)

UNIT_ORDER = ("kW", "kWh", "W", "Wh", "MW", "MWh")                  # the units to choose from
NOTICE_ICONS = {"warning": ("warning", "warning"), "info": ("info", "primary")}


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
    """The refreshable view of the area. It is drawn again when a file is loaded, answered or removed."""

    async def read(session):
        state.profile_reading = True
        view.refresh()
        try:
            await run.io_bound(session.read)
        except Exception:  # noqa: BLE001 - the page must stay alive whatever happens
            logger.exception("The load profile could not be read")
            session.failed = True
            session.profile = None
            session.error = None
        finally:
            state.profile_reading = False
        view.refresh()

    async def receive(event: events.UploadEventArguments):
        content = await event.file.read()
        name = event.file.name
        state.profile = ProfileSession(content, name)
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
        elif session.failed:
            ui.label(tr("profile.unexpected")).classes("text-negative").mark("profile-failed")
        elif session.error is not None:
            ui.label(profile_text(session.error, tr)).classes("text-negative").mark("profile-error")
        elif session.profile is not None:
            if session.ready:
                summary_card(session.profile)
            questions_card(session)
            notes_card(session.profile)

    return view