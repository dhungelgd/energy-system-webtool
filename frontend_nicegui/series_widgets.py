"""The parts of the upload of a time series that the card of a component and the card for a file with all the
series have in common: the sheet, the settings of the import, what the import found, and the preview.

Each part is drawn for an `UploadSession` (series_session.py). `suffix` ends the markers ('series-sheet-pv' for the
component pv, 'series-sheet-bulk' for the file with all series), `refresh` draws the page again after the file was
read again with other settings.
"""

from nicegui import ui

from backend.timeseries_import import import_text

ACCEPT = ".csv,.txt,.tsv,.xlsx,.xlsm"           # the files that can be chosen
AUTO = "auto"                                   # the choice "detect it" (the import takes None)

DELIMITERS = {
    ";": "series.settings.delimiter.semicolon",
    ",": "series.settings.delimiter.comma",
    "\t": "series.settings.delimiter.tab",
    "|": "series.settings.delimiter.pipe",
}
DECIMALS = {",": "series.settings.decimal.comma", ".": "series.settings.decimal.point"}
ENCODINGS = {
    "utf-8": "series.settings.encoding.utf8",
    "cp1252": "series.settings.encoding.cp1252",
    "utf-16": "series.settings.encoding.utf16",
}


def reread(session, refresh, **change):
    """Read the file again with other settings and draw the page again."""

    session.change(**change)
    refresh()


def sheet_select(session, tr, suffix, refresh):
    """The choice of the sheet of an Excel file (nothing for a file that has one sheet)."""

    if len(session.sheets()) > 1:
        ui.select(
            session.sheets(), value=session.table.used.sheet, label=tr("series.sheet"),
            on_change=lambda event: reread(session, refresh, sheet=event.value),
        ).classes("w-full").mark(f"series-sheet-{suffix}")


def preview_block(session, tr, suffix):
    """The first rows of the file."""

    columns, rows = session.preview(tr)
    ui.label(tr(
        "series.preview", rows=tr.integer(len(session.table.df)), columns=tr.integer(len(session.table.df.columns)),
    )).classes("text-grey text-sm")
    ui.table(columns=columns, rows=rows).props("dense flat").classes("w-full").mark(f"series-preview-{suffix}")


def notice_line(notice, tr):
    """What the import found, as a line: a warning with an icon, anything else in grey."""

    if notice.code == "decimal_sign":
        return                                  # only worth a word when the program was not sure
    if notice.level == "warning":
        with ui.row().classes("items-start gap-2 no-wrap"):
            ui.icon("warning", color="warning")
            ui.label(import_text(notice, tr))
    else:
        ui.label(import_text(notice, tr)).classes("text-grey text-sm")


def _choose(session, tr, name, choices, label_key, current, marker, refresh):
    """A selection of an import setting with 'Automatic' first; None (detect it) is the same as AUTO."""

    options = {AUTO: tr("series.settings.auto"), **{value: tr(text) for value, text in choices.items()}}
    ui.select(
        options, value=AUTO if current is None else current, label=tr(label_key),
        on_change=lambda event: reread(session, refresh, **{name: None if event.value == AUTO else event.value}),
    ).classes("w-full").mark(marker)


def settings_box(session, tr, suffix, refresh):
    """The box with the import settings (delimiter, decimal sign, encoding, the lines of the header and the data)."""

    def line_changed(name, event):
        used = getattr(session.table.used, name)
        if event.value is not None and int(event.value) != used:
            reread(session, refresh, **{name: int(event.value)})

    with ui.expansion(
        tr("series.settings.heading"), value=session.settings_open,
        on_value_change=lambda event: setattr(session, "settings_open", event.value),
    ).classes("w-full"):
        ui.label(tr("series.settings.caption")).classes("text-grey text-sm")
        options, used = session.options, session.table.used

        if session.table.kind == "csv":
            _choose(session, tr, "delimiter", DELIMITERS, "series.settings.delimiter", options.delimiter,
                    f"series-delimiter-{suffix}", refresh)
            _choose(session, tr, "decimal", DECIMALS, "series.settings.decimal", options.decimal,
                    f"series-decimal-{suffix}", refresh)
            _choose(session, tr, "encoding", ENCODINGS, "series.settings.encoding", options.encoding,
                    f"series-encoding-{suffix}", refresh)
        else:
            _choose(session, tr, "decimal", DECIMALS, "series.settings.decimal", options.decimal,
                    f"series-decimal-{suffix}", refresh)

        for name, label_key, low in (("header_line", "series.settings.header", 0),
                                     ("first_data_line", "series.settings.first_line", 1)):
            ui.number(
                tr(label_key), value=getattr(used, name), min=low, precision=0, format="%d",
                on_change=lambda event, n=name: line_changed(n, event),
            ).props("outlined dense debounce=500").classes("w-full").mark(f"series-{name.replace('_', '-')}-{suffix}")