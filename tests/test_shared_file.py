"""One file for the whole session: the file of the load profile page is also the file of the optimization."""

import pandas as pd
import pytest

from backend.timeseries_import import ImportOptions
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.profile_session import ProfileSession
from frontend_nicegui.series_bulk import BulkSession
from frontend_nicegui.shared_file import bulk_from_profile, is_the_file_of
from tests.test_load_profile import kw, render, starts, workbook_of_sheets


def several_columns(unit="kwh", step="60min"):
    lines = [f"time,temperatur_aussen_c,strom_niedrig_{unit},strom_hoch_{unit}"]
    lines += [f"2026-01-0{day} {hour:02d}:00,1.5,0.3,{0.8 + hour / 100}" for day in (1, 2, 3) for hour in range(24)]

    return ("\n".join(lines) + "\n").encode()


def ready(content, name="a.csv", **choices):
    session = ProfileSession(content, name)
    if choices:
        session.decide(**choices)
    session.read()

    return session


def test_the_file_of_the_optimization_is_the_same_bytes_and_name_as_the_file_of_the_load_profile_page():
    profile = ready(several_columns(), "zeitreihen.csv", value_column="strom_hoch_kwh")

    bulk = bulk_from_profile(profile)

    assert isinstance(bulk, BulkSession) and bulk.filename == "zeitreihen.csv" and bulk.master.content is profile.content
    assert bulk.readable and bulk.columns() == ["temperatur_aussen_c", "strom_niedrig_kwh", "strom_hoch_kwh"]
    assert is_the_file_of(bulk, profile)


def test_the_column_that_was_analysed_is_the_preferred_demand_and_its_unit_gives_the_answer_for_the_hours():
    energy = bulk_from_profile(ready(several_columns("kwh"), value_column="strom_hoch_kwh"))
    power = bulk_from_profile(ready(several_columns("kw"), value_column="strom_hoch_kw"))

    assert energy.preferred == {"demand": "strom_hoch_kwh"} and energy.master.aggregate == "sum"       # kWh in each step: the sum
    assert power.preferred == {"demand": "strom_hoch_kw"} and power.master.aggregate == "mean"          # kW: the mean


def test_a_profile_that_is_not_ready_gives_the_file_without_a_preferred_column_and_without_an_answer_for_the_hours():
    profile = ProfileSession(several_columns(), "a.csv")
    profile.read()
    assert not profile.ready

    bulk = bulk_from_profile(profile)

    assert bulk.readable and bulk.preferred == {} and bulk.master.aggregate is None


def test_a_column_of_shares_has_a_preferred_demand_but_no_answer_for_the_hours():
    lines = ["time,anteil"] + [f"2026-01-0{day} {hour:02d}:00,{1 / 72}" for day in (1, 2, 3) for hour in range(24)]
    profile = ready(("\n".join(lines) + "\n").encode(), energy_kwh=7200.0)

    bulk = bulk_from_profile(profile)

    assert profile.ready and profile.profile.unit == "share"
    assert bulk.preferred == {"demand": "anteil"} and bulk.master.aggregate is None


def test_the_sheet_and_the_settings_of_the_import_come_with_the_file_and_the_lines_stay():
    content = workbook_of_sheets()
    profile = ProfileSession(content, "jahre.xlsx")
    profile.file.change(sheet="2022", first_data_line=12)
    profile.layout_changed()
    profile.read()

    bulk = bulk_from_profile(profile)

    assert bulk.master.table.used.sheet == "2022" and bulk.master.options.sheet == "2022"
    assert bulk.master.options.first_data_line == 12 and len(bulk.master.table.df) == 182           # the lines were not detected again
    assert bulk.period().start.isoformat() == "2022-02-05T02:30:00"


def test_with_everything_automatic_the_optimization_reads_the_file_with_everything_automatic():
    profile = ready(several_columns())

    bulk = bulk_from_profile(profile)

    assert bulk.master.options == ImportOptions() and profile.file.options == ImportOptions()


def test_the_file_of_another_session_or_none_is_not_the_file_of_the_profile():
    profile = ready(several_columns())
    other = bulk_from_profile(ready(several_columns()))

    assert not is_the_file_of(other, profile) and not is_the_file_of(None, profile) and not is_the_file_of(other, None)


def test_a_quarter_hour_file_in_energy_units_gives_the_sum_of_the_hours_and_the_energy_of_the_profile_is_the_sum_of_its_values():
    index = starts("2024-02-05 00:00", "2024-02-06 23:45")
    values = kw(index)
    profile = ready(render(index, values, header="Zeitstempel;Verbrauch kWh").encode(), "viertel.csv")

    bulk = bulk_from_profile(profile)

    assert profile.ready and profile.profile.unit == "kWh" and bulk.master.aggregate == "sum"
    assert profile.profile.energy_kwh() == pytest.approx(values.sum())


def test_the_same_name_or_the_same_bytes_are_not_the_same_file_only_the_very_file_of_the_session_is():
    content = several_columns()
    profile = ready(content, "zeitreihen.csv")
    same_name = BulkSession(several_columns("kw"), "zeitreihen.csv")                  # another file with the same name
    same_bytes = BulkSession(bytes(bytearray(content)), "anders.csv")                  # the same bytes, uploaded again

    assert not is_the_file_of(same_name, profile) and not is_the_file_of(same_bytes, profile)
    assert is_the_file_of(bulk_from_profile(profile), profile)


# ---------------------------------------------------------------------------
# a file with the date and the time of day in two columns (as the grid operators write it)
# ---------------------------------------------------------------------------

def two_column_file(header="Wirkleistung kW", value=lambda t: 20 + t.hour + 0.5):
    index = pd.date_range("2024-02-05 00:00", "2024-02-06 23:45", freq="15min")
    lines = [f"Datum;Uhrzeit;{header}"] + [f"{t:%d.%m.%Y};{t:%H:%M};{str(value(t)).replace('.', ',')}" for t in index]

    return ("\n".join(lines) + "\n").encode(), index


def absolute_demand_draft():
    draft = ScenarioDraft(steps=48)
    draft.set("demand", True)
    draft.component("demand").blocks["demand"]["profile_type"] = "absolute"

    return draft


def test_a_file_with_the_date_and_the_time_of_day_in_two_columns_is_read_in_the_same_way_by_both_pages():
    content, index = two_column_file()
    profile = ready(content, "netz.csv")

    bulk = bulk_from_profile(profile)

    assert profile.ready and profile.profile.step_minutes == 15 and profile.profile.rows == len(index)
    assert bulk.readable and bulk.master.table.time.step_minutes == 15 and bulk.columns() == ["Wirkleistung kW"]
    assert bulk.period().start == pd.Timestamp("2024-02-05 00:00").to_pydatetime() and bulk.period().hours == 48


def test_the_hourly_demand_of_the_optimization_from_a_power_in_kw_has_the_energy_of_the_profile():
    content, _ = two_column_file()
    profile = ready(content, "netz.csv")
    bulk, draft = bulk_from_profile(profile), absolute_demand_draft()
    components = BulkSession.components_with_series(draft)
    bulk.update(components)

    data, problem = bulk.results(components, draft.start)["demand"]

    assert problem is None and bulk.master.aggregate == "mean" and len(data.values) == 48
    assert sum(data.values) == pytest.approx(profile.profile.energy_kwh())                # the mean of the hours, in kW: kWh per hour


def test_the_hourly_demand_of_the_optimization_from_energy_in_kwh_per_step_has_the_energy_of_the_profile():
    content, _ = two_column_file("Verbrauch kWh", value=lambda t: 2 + t.hour / 10)
    profile = ready(content, "netz.csv")
    bulk, draft = bulk_from_profile(profile), absolute_demand_draft()
    components = BulkSession.components_with_series(draft)
    bulk.update(components)

    data, problem = bulk.results(components, draft.start)["demand"]

    assert problem is None and profile.profile.unit == "kWh" and bulk.master.aggregate == "sum" and len(data.values) == 48
    assert sum(data.values) == pytest.approx(profile.profile.energy_kwh())                # the sum of the quarter-hours of each hour


def test_a_file_whose_dates_repeat_and_have_no_time_of_day_gives_no_division_by_zero_but_a_warning_and_rows_as_hours():
    lines = ["Datum;Last"] + [f"05.02.2024;{value},5" for value in range(10)]
    bulk = BulkSession(("\n".join(lines) + "\n").encode(), "datum.csv")
    draft = ScenarioDraft(steps=10)
    draft.set("demand", True)
    components = BulkSession.components_with_series(draft)
    bulk.update(components)

    results = bulk.results(components, draft.start)

    assert bulk.master.table.time is None and bulk.master.table.messages[0].code == "time_unusable"
    assert results["demand"][1] is None and len(results["demand"][0].values) == 10                 # the rows are taken as hours