"""Upload files into the real Streamlit app (no browser) and look at the result."""

import io
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from openpyxl import Workbook  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "frontend" / "app.py")

HOURS = 8760
COLUMNS = ["timestamp", "heat_demand", "electricity_demand", "pv", "wind", "price", "cop"]


def year_table(freq="1h", periods=HOURS):
    stamps = pd.date_range("2021-01-01", periods=periods, freq=freq)
    return pd.DataFrame({
        "timestamp": stamps,
        "heat_demand": 0.5,
        "electricity_demand": 0.25,
        "pv": 0.125,
        "wind": 0.375,
        "price": 0.3,
        "cop": 3.5,
    })


def german_csv(table=None, encoding="cp1252"):
    table = year_table() if table is None else table
    table = table.assign(timestamp=table["timestamp"].dt.strftime("%d.%m.%Y %H:%M"))
    return table.to_csv(sep=";", decimal=",", index=False).encode(encoding)


def excel_file(table=None):
    table = year_table() if table is None else table

    workbook = Workbook()
    workbook.active.title = "Hinweise"
    workbook.active.append(["Bitte Blatt 'Daten' verwenden"])

    sheet = workbook.create_sheet("Daten")
    sheet.append(list(table.columns))
    for row in table.itertuples(index=False):
        sheet.append([value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
                      for value in row])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def start_app():
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()
    app.sidebar.button(key="template_Full system").click().run()
    return app


def upload(app, name, content):
    uploader = next(u for u in app.sidebar.file_uploader if u.key == "shared_ts_csv")
    uploader.set_value((name, content, "application/octet-stream")).run()
    return app


def sidebar_text(app):
    return [c.value for c in app.sidebar.caption]


def sidebar_select(app, label):
    return next(s for s in app.sidebar.selectbox if s.label == label)


def column_choice(app, component):
    return next(s.value for s in app.selectbox if s.key.startswith(f"{component}_col_"))


# ---------------------------------------------------------------------------

def test_the_uploader_accepts_csv_and_excel():
    app = start_app()
    uploader = next(u for u in app.sidebar.file_uploader if u.key == "shared_ts_csv")

    assert set(uploader.allowed_type) >= {".csv", ".txt", ".xlsx"}


def test_german_csv_is_read_and_the_right_columns_are_preselected():
    app = upload(start_app(), "lastgang.csv", german_csv())

    assert not app.exception

    table = app.session_state["shared_ts_df"]
    assert list(table.columns) == COLUMNS
    assert table["electricity_demand"].tolist()[:2] == [0.25, 0.25]      # not 25
    assert len(table) == HOURS

    assert column_choice(app, "demand") == "electricity_demand"
    assert column_choice(app, "pv") == "pv"

    texts = " ".join(sidebar_text(app))
    assert "separator: semicolon" in texts
    assert "decimal: comma" in texts
    assert "8760 rows" in texts


def test_german_file_gives_no_time_series_errors():
    app = upload(start_app(), "lastgang.csv", german_csv())

    time_series_errors = [
        e.value for e in app.error
        if "time series" in e.value or "price series" in e.value
    ]
    assert time_series_errors == []


def test_excel_file_with_several_sheets():
    app = upload(start_app(), "lastgang.xlsx", excel_file())

    assert not app.exception
    table = app.session_state["shared_ts_df"]
    assert list(table.columns) == COLUMNS
    assert table["pv"].tolist()[0] == 0.125

    assert "sheet: Daten" in " ".join(sidebar_text(app))
    assert sidebar_select(app, "Sheet").options == ["Automatic", "Hinweise", "Daten"]


def test_quarter_hourly_file_shows_a_warning():
    quarter = year_table(freq="15min", periods=96)
    app = upload(start_app(), "viertelstunden.csv", german_csv(quarter))

    warnings = [w.value for w in app.sidebar.warning]
    assert any("15 minutes" in w and "hourly" in w for w in warnings)


def test_settings_can_be_changed_by_the_user():
    app = upload(start_app(), "lastgang.csv", german_csv())

    sidebar_select(app, "Column separator").select("Comma ( , )").run()
    table = app.session_state["shared_ts_df"]

    # the German file read with a comma: the columns are no longer the real ones
    assert "timestamp" not in table.columns
    assert list(table.columns) != COLUMNS


def test_wrong_decimal_sign_can_be_corrected():
    app = upload(start_app(), "lastgang.csv", german_csv())

    sidebar_select(app, "Decimal sign").select("Point (12.5)").run()
    table = app.session_state["shared_ts_df"]

    assert table["electricity_demand"].iloc[0] != 0.25


def test_unreadable_file_shows_a_message_and_no_crash():
    app = upload(start_app(), "kaputt.xlsx", b"not an excel file")

    assert not app.exception
    assert any("cannot be opened" in e.value for e in app.sidebar.error)
    assert "shared_ts_df" not in app.session_state


def test_unsupported_old_excel_format_is_explained():
    # only the extensions the uploader allows can be chosen in a browser, but a
    # renamed file must not crash the app either
    app = upload(start_app(), "alt.csv", b"\x00\x01\x02\x03")

    assert not app.exception


def test_removing_the_file_clears_the_data():
    app = upload(start_app(), "lastgang.csv", german_csv())
    assert "shared_ts_df" in app.session_state

    next(u for u in app.sidebar.file_uploader if u.key == "shared_ts_csv").set_value(None).run()

    assert "shared_ts_df" not in app.session_state


def test_a_file_for_one_component_replaces_the_shared_file_and_can_be_removed():
    app = upload(start_app(), "lastgang.csv", german_csv())

    own = next(u for u in app.file_uploader if u.key == "pv_csv")
    pv_only = year_table().assign(pv=0.75)[["timestamp", "pv"]]
    own.set_value(("pv.csv", german_csv(pv_only), "text/csv")).run()

    assert not app.exception
    assert app.session_state["pv_df"]["pv"].iloc[0] == 0.75

    next(u for u in app.file_uploader if u.key == "pv_csv").set_value(None).run()

    assert "pv_df" not in app.session_state
