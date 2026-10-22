"""Upload of time series files: automatic layout detection and import settings."""

from dataclasses import astuple, replace

import streamlit as st

from backend.timeseries_import import (
    FILE_TYPES,
    ImportOptions,
    TimeSeriesFileError,
    read_table,
)

UPLOAD_TYPES = FILE_TYPES

AUTO = "Automatic"

DELIMITER_CHOICES = {
    AUTO: None,
    "Semicolon ( ; )": ";",
    "Comma ( , )": ",",
    "Tab": "\t",
    "Pipe ( | )": "|",
}
DECIMAL_CHOICES = {
    AUTO: None,
    "Comma (12,5)": ",",
    "Point (12.5)": ".",
}
ENCODING_CHOICES = {
    AUTO: None,
    "UTF-8": "utf-8",
    "Windows-1252 (Western Europe)": "cp1252",
    "UTF-16": "utf-16",
}

DELIMITER_NAMES = {";": "semicolon", ",": "comma", "\t": "tab", "|": "pipe"}
DECIMAL_NAMES = {",": "comma", ".": "point"}


@st.cache_data(show_spinner=False)
def _read(content, filename, options):
    return read_table(content, filename, ImportOptions(*options))


def _read_or_none(content, filename, options):
    try:
        return _read(content, filename, astuple(options))
    except TimeSeriesFileError as error:
        st.error(str(error))
        return None


def _choose(label, choices, key):
    return choices[st.selectbox(label, list(choices), key=key)]


def _detected_text(table):
    used = table.used

    parts = []
    if table.kind == "csv":
        parts.append(f"separator: {DELIMITER_NAMES.get(used.delimiter, used.delimiter)}")
    else:
        parts.append(f"sheet: {used.sheet}")
    if used.decimal:
        parts.append(f"decimal: {DECIMAL_NAMES[used.decimal]}")
    parts.append(
        "no column names" if used.header_line == 0
        else f"column names in line {used.header_line}"
    )
    parts.append(f"data from line {used.first_data_line}")
    parts.append(f"{len(table.df)} rows, {len(table.df.columns)} columns")

    return " | ".join(parts)


def read_uploaded_table(uploaded_file, key):
    """Read an uploaded CSV or Excel file and show what was detected.

    The user can correct the settings. Returns the table as a DataFrame
    (numbers and dates already converted) or None if the file cannot be read.
    """

    content = uploaded_file.getvalue()
    name = uploaded_file.name

    # new settings for a new file
    token = f"{key}_{abs(hash((name, content))) % 10**8}"

    detected = _read_or_none(content, name, ImportOptions())
    if detected is None:
        return None

    with st.expander("Import settings"):
        st.caption(
            "The layout of the file is detected automatically. "
            "Change a setting only if the preview is wrong."
        )

        if detected.kind == "csv":
            delimiter = _choose("Column separator", DELIMITER_CHOICES, f"{token}_delimiter")
            decimal = _choose("Decimal sign", DECIMAL_CHOICES, f"{token}_decimal")
            encoding = _choose("Character encoding", ENCODING_CHOICES, f"{token}_encoding")
            sheet = None
        else:
            sheet = None
            if len(detected.sheets) > 1:
                choice = st.selectbox(
                    "Sheet", [AUTO] + detected.sheets, key=f"{token}_sheet"
                )
                sheet = None if choice == AUTO else choice
            delimiter = encoding = None
            decimal = _choose("Decimal sign (numbers stored as text)", DECIMAL_CHOICES, f"{token}_decimal")

        chosen = ImportOptions(
            encoding=encoding, delimiter=delimiter, decimal=decimal, sheet=sheet
        )
        table = _read_or_none(content, name, chosen)
        if table is None:
            return None

        # the line numbers depend on the choices above, so they come last
        header_line = st.number_input(
            "Line with the column names (0 = none)",
            min_value=0, step=1, value=table.used.header_line,
            key=f"{token}_header_{table.used.header_line}",
        )
        first_line = st.number_input(
            "First line with data",
            min_value=1, step=1, value=table.used.first_data_line,
            key=f"{token}_first_{table.used.first_data_line}",
        )

        overrides = {}
        if header_line != table.used.header_line:
            overrides["header_line"] = int(header_line)
        if first_line != table.used.first_data_line:
            overrides["first_data_line"] = int(first_line)

        if overrides:
            table = _read_or_none(content, name, replace(chosen, **overrides))
            if table is None:
                return None

        st.dataframe(table.df.head(8), hide_index=True)

    st.caption("Read as: " + _detected_text(table))

    for level, text in table.messages:
        if level == "warning":
            st.warning(text)
        elif not text.startswith("Decimal sign"):
            st.caption(text)

    return table.df