"""Write the same data in 1024 different file layouts and read it back.

The values must come back exactly. This protects against the worst kind of
mistake: a decimal comma that is read as thousands separator (12,5 -> 125).
"""

import datetime
import itertools

from backend.timeseries_import import read_table

# (load, pv) per row. Real data never has only "x,xxx"-like values in a file.
VALUES = [(12.5, 0.0), (0.125, 1234.5), (7.0, 0.5), (100.25, 2.0), (1234.5, 0.375), (33.0, 12.5)]

DELIMITERS = [";", ",", "\t", "|"]
DECIMALS = [".", ","]
THOUSANDS = [False, True]
ENCODINGS = ["utf-8", "utf-8-sig", "cp1252", "utf-16"]
HEADERS = [True, False]
METADATA = [False, True]
DATE_FORMATS = ["%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", None]
NEWLINES = ["\n", "\r\n"]


def stamps():
    first = datetime.datetime(2021, 3, 14, 0)
    return [first + datetime.timedelta(hours=i) for i in range(len(VALUES))]


def number_text(value, decimal, thousands):
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    whole, _, fraction = text.partition(".")

    if thousands and len(whole) > 3:
        group = "." if decimal == "," else ","
        whole = f"{int(whole):,}".replace(",", group)

    return whole + (decimal + fraction if fraction else "")


def build_file(delimiter, decimal, thousands, encoding, header, metadata, date_format, newline):
    lines = []

    if metadata:
        lines += ["Lastgang Firma Mueller GmbH", f"Zaehlpunkt{delimiter}DE0001", ""]

    columns = (["Zeit"] if date_format else []) + ["Last", "PV"]
    if header:
        lines.append(delimiter.join(columns))

    for stamp, row in zip(stamps(), VALUES):
        cells = [stamp.strftime(date_format)] if date_format else []
        for value in row:
            text = number_text(value, decimal, thousands)
            cells.append(f'"{text}"' if delimiter in text else text)
        lines.append(delimiter.join(cells))

    return (newline.join(lines) + newline).encode(encoding)


def test_values_survive_every_file_layout():
    layouts = itertools.product(
        DELIMITERS, DECIMALS, THOUSANDS, ENCODINGS, HEADERS, METADATA, DATE_FORMATS
    )

    expected = [[row[0] for row in VALUES], [row[1] for row in VALUES]]
    failures = []
    checked = 0

    for index, layout in enumerate(layouts):
        newline = NEWLINES[index % 2]
        checked += 1

        try:
            table = read_table(build_file(*layout, newline), "data.csv")
            numbers = [
                table.df[column].tolist() for column in table.df.columns
                if str(table.df[column].dtype) == "float64"
            ][-2:]
            ok = numbers == expected

            date_format = layout[-1]
            if date_format:
                first = table.df.iloc[:, 0]
                ok = ok and str(first.dtype).startswith("datetime") and first.iloc[0] == stamps()[0]
        except Exception as error:      # noqa: BLE001 - collect every failure
            ok = False
            layout = layout + (repr(error)[:80],)

        if not ok:
            failures.append(layout)

    assert checked == 1024
    assert failures == [], f"{len(failures)} layouts failed, first: {failures[:3]}"
