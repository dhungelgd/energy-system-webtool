"""Time series for the components: from a file column to the series of a component, and in the draft."""

import math
import random
from datetime import datetime, timedelta

import pytest

from backend import service_v2
from backend.i18n import Translator
from backend.scenario_convert import scenario_to_v1
from backend.scenario_v2 import SeriesData
from backend.series_input import (
    AGGREGATES,
    PRICE_UNITS,
    Aggregate,
    aggregate_for,
    covers,
    has_series,
    is_hourly,
    is_optional,
    needs_choice,
    numeric_columns,
    series_data,
    series_notices,
    slot_of,
    start_row,
    summarize,
)
from backend.templates import new_component
from backend.timeseries_import import TimeSeriesFileError, import_text, read_table
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.forms import set_value
from tests.helpers import needs_cbc

DE = Translator("de")


def table_of(values, name="Wert", stamps=True, start="2021-01-01 00:00", minutes=60):
    """A table as the importer reads it: a time column (optional) and one column of numbers."""

    rows = ["Zeit;" + name if stamps else name]
    first = datetime.fromisoformat(start)
    for i, value in enumerate(values):
        text = "" if value is None else str(value)
        moment = first + timedelta(minutes=minutes) * i
        rows.append(f"{moment:%Y-%m-%d %H:%M};{text}" if stamps else text)
    return read_table(("\n".join(rows) + "\n").encode(), "daten.csv")


def draft_of(template, steps=24):
    draft = ScenarioDraft(steps=steps)
    draft.apply_template(template)
    return draft


def give(draft, key, values, **options):
    table = table_of(values)
    data = series_data(table, "Wert", draft.component(key), filename="daten.csv", **options)
    draft.set_series(key, data)
    return data


# ---------------------------------------------------------------------------
# which component has a time series
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template, block, field, series_id", [
    ("demand", "demand", "series", "electricity_demand"),
    ("heat_demand", "demand", "series", "heat_demand"),
    ("pv", "profile", "series", "pv_profile"),
    ("wind", "profile", "series", "wind_profile"),
    ("grid", "costs", "variable_costs_series", "grid_price"),
    ("heat_pump", "conversion", "outputs.heat.ratio_series", "cop_profile"),
])
def test_where_a_component_keeps_its_time_series(template, block, field, series_id):
    slot = slot_of(new_component(template))

    assert (slot.block, slot.field, slot.series_id) == (block, field, series_id)
    assert has_series(new_component(template))


@pytest.mark.parametrize("template", ["grid_feedin", "gas_import", "gas_boiler", "heating_rod", "chp", "battery", "heat_storage"])
def test_the_other_components_have_no_time_series(template):
    assert slot_of(new_component(template)) is None and not has_series(new_component(template))


def test_only_the_grid_and_the_heat_pump_can_use_a_constant_instead():
    assert [t for t in ("demand", "heat_demand", "pv", "wind", "grid", "heat_pump") if is_optional(new_component(t))] == [
        "grid", "heat_pump"]


# ---------------------------------------------------------------------------
# the file
# ---------------------------------------------------------------------------

def test_the_numeric_columns_are_the_ones_with_numbers():
    table = read_table(b"Zeit;Name;Last;PV\n2021-01-01 00:00;a;1;0.5\n2021-01-01 01:00;b;2;0.7\n", "x.csv")

    assert numeric_columns(table) == ["Last", "PV"]


def test_a_file_with_a_time_step_other_than_an_hour_is_not_hourly():
    assert is_hourly(table_of([1, 2, 3]))
    assert not is_hourly(table_of([1, 2, 3], minutes=15))
    assert is_hourly(table_of([1, 2, 3], stamps=False))                  # no dates: taken as hourly


def test_the_start_of_the_scenario_is_found_in_the_file():
    table = table_of(range(48), start="2021-03-01 00:00")

    assert covers(table, datetime(2021, 3, 1, 0, 0)) and covers(table, datetime(2021, 3, 2, 23, 0))
    assert not covers(table, datetime(2021, 2, 28, 23, 0)) and not covers(table, datetime(2021, 3, 3, 0, 0))
    assert not covers(table_of([1, 2], stamps=False), datetime(2021, 3, 1))
    assert start_row(table, datetime(2021, 3, 1, 0, 0)) == 0
    assert start_row(table, datetime(2021, 3, 2, 0, 0)) == 24
    assert start_row(table, datetime(2021, 3, 1, 5, 30)) == 6             # the first row at or after it


def test_a_start_outside_the_file_is_an_error_with_a_sentence():
    table = table_of(range(48), start="2021-03-01 00:00")

    with pytest.raises(TimeSeriesFileError) as raised:
        start_row(table, datetime(2022, 1, 1))

    error = raised.value
    assert error.code == "start_outside"
    assert str(error) == "The start 01.01.2022 00:00 is outside the file (01.03.2021 00:00 to 02.03.2021 23:00)."
    assert import_text(error, DE) == "Der Start 01.01.2022 00:00 liegt außerhalb der Datei (01.03.2021 00:00 bis 02.03.2021 23:00)."


def test_a_file_without_dates_cannot_be_cut_at_a_start():
    with pytest.raises(TimeSeriesFileError) as raised:
        start_row(table_of([1, 2, 3], stamps=False), datetime(2021, 1, 1))

    assert raised.value.code == "no_time_column"
    assert import_text(raised.value, DE).startswith("Die Datei hat keine Datumsspalte")


def test_dates_with_a_time_zone_work_too():
    content = b"Zeit;Wert\n2021-01-01T00:00:00+01:00;1\n2021-01-01T01:00:00+01:00;2\n2021-01-01T02:00:00+01:00;3\n"
    table = read_table(content, "x.csv")

    assert covers(table, datetime(2021, 1, 1, 1, 0)) and start_row(table, datetime(2021, 1, 1, 1, 0)) == 1


# ---------------------------------------------------------------------------
# from a column to a series
# ---------------------------------------------------------------------------

def test_the_values_of_a_column_become_the_series_of_a_component():
    data = series_data(table_of([1.5, 2.5, None, 4]), "Wert", new_component("pv"), filename="sonne.csv")

    assert data.values == [1.5, 2.5, None, 4.0]                           # an empty value stays visible
    assert (data.unit, data.source.file, data.source.column) == ("capacity factor", "sonne.csv", "Wert")


@pytest.mark.parametrize("template, unit", [
    ("demand", ""), ("heat_demand", ""), ("pv", "capacity factor"), ("wind", "capacity factor"),
    ("grid", "€ per kWh"), ("heat_pump", "ratio"),
])
def test_the_unit_that_is_stored_with_a_series(template, unit):
    assert series_data(table_of([1, 2]), "Wert", new_component(template)).unit == unit


@pytest.mark.parametrize("price_unit, expected", [
    (None, [0.25, 0.30]), ("€/kWh", [0.25, 0.30]), ("ct/kWh", [0.0025, 0.003]), ("€/MWh", [0.00025, 0.0003]),
])
def test_a_price_is_stored_in_euro_per_kwh_whatever_unit_the_file_has(price_unit, expected):
    data = series_data(table_of([0.25, 0.30]), "Wert", new_component("grid"), price_unit=price_unit)

    assert data.values == pytest.approx(expected) and data.unit == "€ per kWh"


def test_the_price_units_to_choose_from():
    assert PRICE_UNITS == ("€/kWh", "ct/kWh", "€/MWh")


def test_an_unknown_price_unit_is_refused():
    with pytest.raises(ValueError, match="unknown price unit 'GBP'"):
        series_data(table_of([1]), "Wert", new_component("grid"), price_unit="GBP")


def test_the_part_of_the_file_from_a_start_is_used():
    table = table_of(range(48), start="2021-03-01 00:00")

    data = series_data(table, "Wert", new_component("demand"), start=datetime(2021, 3, 2, 0, 0))

    assert data.values[0] == 24.0 and len(data.values) == 24


def test_a_column_that_is_not_a_number_or_does_not_exist_is_refused_with_a_sentence():
    table = read_table(b"Zeit;Name;Wert\n2021-01-01 00:00;a;1\n2021-01-01 01:00;b;2\n", "x.csv")

    for column, code in (("Name", "column_not_numbers"), ("Nope", "column_missing")):
        with pytest.raises(TimeSeriesFileError) as raised:
            series_data(table, column, new_component("pv"))
        assert raised.value.code == code


def test_infinite_values_are_refused():
    table = table_of([1, 2, 3])
    table.df["Wert"] = [1.0, float("inf"), 3.0]

    with pytest.raises(TimeSeriesFileError) as raised:
        series_data(table, "Wert", new_component("pv"))

    assert raised.value.code == "infinite_values"
    assert import_text(raised.value, DE) == "Die Spalte 'Wert' enthält unendliche Werte."


def test_a_component_without_a_time_series_refuses_one():
    with pytest.raises(ValueError, match="has no time series"):
        series_data(table_of([1]), "Wert", new_component("gas_boiler"))


def test_what_to_tell_the_user_about_a_series():
    summary = summarize(SeriesData(values=[1.0, None, 3.0, 5.0]))

    assert (summary.count, summary.empty, summary.minimum, summary.maximum, summary.total) == (4, 1, 1.0, 5.0, 9.0)
    assert math.isnan(summarize(SeriesData(values=[None, None])).minimum)
    assert summarize(SeriesData(values=[])).count == 0


# ---------------------------------------------------------------------------
# a file with a time step shorter than an hour
# ---------------------------------------------------------------------------

def quarters(values, start="2021-03-01 00:00", **options):
    """Hourly values 0, 1, 2, ... each written four times (as values of 15 minutes): the average is the hour itself."""

    return table_of(values, start=start, minutes=15, **options)


def hourly(values, aggregate, component="pv", minutes=15, **options):
    table = table_of(values, minutes=minutes)
    return series_data(table, "Wert", new_component(component), aggregate=aggregate, **options).values


def test_values_of_15_minutes_become_hourly_values_by_the_average():
    assert hourly([1, 2, 3, 4, 5, 6, 7, 8], "mean") == [2.5, 6.5]


def test_values_of_15_minutes_become_hourly_values_by_the_sum():
    assert hourly([1, 2, 3, 4, 5, 6, 7, 8], "sum") == [10.0, 26.0]


@pytest.mark.parametrize("minutes, per_hour", [(30, 2), (20, 3), (15, 4), (12, 5), (10, 6), (5, 12), (1, 60)])
def test_any_time_step_that_divides_the_hour_can_be_converted(minutes, per_hour):
    values = [h for h in range(5) for _ in range(per_hour)]                   # the hours 0 to 4, each written per_hour times

    assert hourly(values, "mean", minutes=minutes) == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert hourly(values, "sum", minutes=minutes) == [0.0, float(per_hour), 2.0 * per_hour, 3.0 * per_hour, 4.0 * per_hour]


def test_an_hour_with_a_missing_row_stays_empty_and_later_values_do_not_move():
    # the rows of 01:15, 01:30 and 01:45 and all of 02:00 to 02:45 are missing
    rows = ["Zeit;Wert"]
    for hour in (0, 1, 3):
        for minute in (0, 15, 30, 45):
            if hour == 1 and minute > 0:
                continue
            rows.append(f"2021-01-01 {hour:02d}:{minute:02d};{hour}")
    table = read_table(("\n".join(rows) + "\n").encode(), "x.csv")

    values = series_data(table, "Wert", new_component("pv"), aggregate="mean").values

    assert values == [0.0, None, None, 3.0]                                      # the hour 03:00 is still at place 4


def test_an_empty_value_makes_its_hour_empty():
    assert hourly([1, 2, None, 4, 5, 6, 7, 8], "mean") == [None, 6.5]


def test_the_rows_are_put_in_the_order_of_the_hours():
    rows = ["Zeit;Wert"] + [f"2021-01-01 {h:02d}:{m:02d};{h}" for h in (1, 0) for m in (0, 15, 30, 45)]
    table = read_table(("\n".join(rows) + "\n").encode(), "x.csv")

    assert series_data(table, "Wert", new_component("pv"), aggregate="mean").values == [0.0, 1.0]


def test_the_first_and_the_last_hour_that_have_only_some_of_their_values_stay_empty():
    table = table_of([1, 2, 3, 4, 5, 6, 7], start="2021-01-01 00:30", minutes=15)         # 00:30, 00:45, 01:00 ... 02:00

    assert series_data(table, "Wert", new_component("pv"), aggregate="mean").values == [None, 4.5, None]


def test_an_hour_that_is_written_twice_is_empty_and_not_added_up():
    # the end of daylight saving time: 02:00 to 03:00 is recorded twice
    rows = ["Zeit;Wert"] + [f"2021-10-31 {h:02d}:{m:02d};1" for h in (1, 2, 2, 3) for m in (0, 15, 30, 45)]
    table = read_table(("\n".join(rows) + "\n").encode(), "x.csv")

    assert series_data(table, "Wert", new_component("pv"), aggregate="sum").values == [4.0, None, 4.0]


def test_an_hourly_file_is_taken_as_it_is_whatever_aggregate_is_given():
    table = table_of([1, 2, 3])

    for aggregate in (None, "mean", "sum"):
        assert series_data(table, "Wert", new_component("pv"), aggregate=aggregate).values == [1.0, 2.0, 3.0]
    assert series_notices(table, "Wert") == []


def test_a_file_without_dates_is_taken_as_it_is():
    assert series_data(table_of([1, 2, 3], stamps=False), "Wert", new_component("pv"), aggregate="mean").values == [1.0, 2.0, 3.0]


def test_a_file_that_needs_converting_without_saying_how_is_an_error_with_a_sentence():
    with pytest.raises(TimeSeriesFileError) as raised:
        series_data(table_of([1, 2, 3, 4], minutes=15), "Wert", new_component("pv"))      # 15 minutes and no aggregate

    error = raised.value
    assert error.code == "convert_needed" and error.params["step"].minutes == 15
    assert str(error) == ("The time step of the file is 15 minutes, but the model works with hourly values. "
                          "Choose how to convert the values to hourly values.")
    assert import_text(error, DE).startswith("Der Zeitschritt der Datei ist 15 Minuten, das Modell rechnet aber")


@pytest.mark.parametrize("minutes, code", [(120, "step_too_long"), (1440, "step_too_long"),
                                           (45, "step_not_divisor"), (7, "step_not_divisor")])
def test_a_time_step_that_cannot_be_converted_is_an_error_with_a_sentence(minutes, code):
    with pytest.raises(TimeSeriesFileError) as raised:
        series_data(table_of([1, 2, 3, 4], minutes=minutes), "Wert", new_component("pv"), aggregate="mean")

    assert raised.value.code == code
    assert "{" not in import_text(raised.value, DE) and import_text(raised.value, DE) != str(raised.value)


def test_the_unit_of_a_price_is_converted_after_the_average():
    values = hourly([25, 25, 25, 25, 30, 30, 30, 30], "mean", component="grid", price_unit="ct/kWh")

    assert values == pytest.approx([0.25, 0.30])


def test_the_part_from_a_start_is_cut_from_the_hours_after_the_conversion():
    values = [h for h in range(48) for _ in range(4)]

    data = series_data(quarters(values), "Wert", new_component("pv"), aggregate="mean", start=datetime(2021, 3, 2, 0, 0))

    assert data.values == [float(h) for h in range(24, 48)]


def test_a_start_outside_the_hours_of_a_converted_file_is_an_error():
    with pytest.raises(TimeSeriesFileError) as raised:
        series_data(quarters([1] * 8), "Wert", new_component("pv"), aggregate="mean", start=datetime(2021, 3, 5))

    assert raised.value.code == "start_outside"


# ---------------------------------------------------------------------------
# which way of converting fits which component
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template, expected", [
    ("pv", "mean"), ("wind", "mean"), ("grid", "mean"), ("heat_pump", "mean"),
])
def test_profiles_prices_and_the_cop_are_averaged(template, expected):
    assert aggregate_for(new_component(template)) == expected and not needs_choice(new_component(template))


@pytest.mark.parametrize("template", ["demand", "heat_demand"])
def test_shares_of_the_annual_demand_are_added_up_and_a_demand_in_kw_is_the_users_choice(template):
    component = new_component(template)
    assert aggregate_for(component) == "sum" and not needs_choice(component)

    component.blocks["demand"]["profile_type"] = "absolute"

    assert aggregate_for(component) is None and needs_choice(component)
    assert AGGREGATES == ("mean", "sum")


def test_a_component_without_a_series_has_nothing_to_choose():
    assert not needs_choice(new_component("gas_boiler"))


def test_a_demand_in_kw_is_converted_the_way_the_user_says():
    component = new_component("demand")
    component.blocks["demand"]["profile_type"] = "absolute"
    kwh_per_quarter = [0.25, 0.25, 0.25, 0.25, 0.5, 0.5, 0.5, 0.5]            # 1 kW, then 2 kW

    as_energy = series_data(table_of(kwh_per_quarter, minutes=15), "Wert", component, aggregate="sum").values
    as_power = series_data(table_of([1, 1, 1, 1, 2, 2, 2, 2], minutes=15), "Wert", component, aggregate="mean").values

    assert as_energy == as_power == [1.0, 2.0]


# ---------------------------------------------------------------------------
# what the user is told about it
# ---------------------------------------------------------------------------

def test_the_user_is_told_how_the_file_was_converted_in_both_languages():
    table = table_of([1, 2, 3, 4, 5, 6, 7, 8], minutes=15)

    (notice,) = series_notices(table, "Wert", "mean")

    assert (notice.level, notice.code) == ("info", "converted")
    assert notice.text == "Converted 8 values with a time step of 15 minutes to 2 hourly values (average)."
    assert import_text(notice, DE) == "8 Werte mit einem Zeitschritt von 15 Minuten wurden in 2 Stundenwerte umgerechnet (Mittelwert)."
    (summed,) = series_notices(table, "Wert", "sum")
    assert summed.text.endswith("(sum).") and import_text(summed, DE).endswith("(Summe).")


def test_the_user_is_told_about_the_hours_that_stayed_empty():
    table = table_of([1, 2, None, 4, 5, 6, 7, None, 9, 10, 11, 12], minutes=15)

    converted, incomplete = series_notices(table, "Wert", "mean")

    assert (incomplete.level, incomplete.code, incomplete.params["n"]) == ("warning", "incomplete_hours", 2)
    assert incomplete.text == "2 hours are incomplete (some of their values are missing) and stay empty. The first one starts at 01.01.2021 00:00."
    assert import_text(incomplete, DE) == (
        "2 Stunden sind unvollständig (einige ihrer Werte fehlen) und bleiben leer. Die erste beginnt am 01.01.2021 00:00.")
    assert "1 hour is incomplete" in series_notices(table_of([1, 2, 3, 4, 5, None, 7, 8], minutes=15), "Wert", "mean")[1].text
    assert "1 Stunde ist unvollständig" in import_text(series_notices(table_of([1, 2, 3, 4, 5, None, 7, 8], minutes=15), "Wert", "mean")[1], DE)


def test_the_words_for_the_way_of_converting():
    assert Aggregate("mean").render(Translator("en")) == "average" and Aggregate("sum").render(DE) == "Summe"


def test_a_converted_series_is_still_checked_for_its_length_and_its_empty_values():
    draft = draft_of("Electricity only", steps=4)
    draft.component("demand").blocks["demand"]["profile_type"] = "absolute"
    values = [1.0] * 16

    data = series_data(table_of(values, minutes=15), "Wert", draft.component("demand"), aggregate="mean")
    draft.set_series("demand", data)
    assert len(data.values) == 4 and ("error", "series_short") not in codes(draft)

    broken = series_data(table_of([1.0, None] + values[2:], minutes=15), "Wert", draft.component("demand"), aggregate="mean")
    draft.set_series("demand", broken)

    assert ("error", "series_invalid") in codes(draft)                                     # the empty hour is not run


@needs_cbc
def test_a_draft_with_a_converted_demand_in_kwh_per_quarter_hour_can_be_run():
    draft = draft_of("Electricity only", steps=24)
    draft.component("demand").blocks["demand"]["profile_type"] = "absolute"
    kwh = [0.25] * 96                                                                     # 1 kW all day, as the meter says it
    draft.set_series("demand", series_data(table_of(kwh, minutes=15), "Wert", draft.component("demand"), aggregate="sum"))
    give(draft, "grid", [0.30] * 24)

    result = service_v2.run(draft.scenario())

    assert result.objective == pytest.approx(24 * 1.0 * 0.30)


def test_whatever_file_is_converted_it_gives_a_series_or_an_error_with_a_sentence():
    rng = random.Random(3)
    for _ in range(300):
        minutes = rng.choice([1, 5, 10, 15, 20, 30, 45, 60, 90, 7])
        count = rng.randint(2, 60)
        values = [rng.choice([None, rng.random()]) for _ in range(count)]
        table = table_of(values, minutes=minutes)
        if "Wert" not in table.df.columns or table.df["Wert"].isna().all():
            continue
        try:
            data = series_data(table, "Wert", new_component("pv"), aggregate=rng.choice([None, "mean", "sum"]))
        except TimeSeriesFileError as error:
            assert error.code in {"convert_needed", "step_too_long", "step_not_divisor"}
        else:
            assert isinstance(data.values, list)


# ---------------------------------------------------------------------------
# in the draft
# ---------------------------------------------------------------------------

def test_a_series_belongs_to_its_component_and_is_part_of_the_scenario():
    draft = draft_of("PV system")

    give(draft, "demand", [1, 2, 3])

    scenario = draft.scenario()
    assert draft.series_of("demand").values == [1.0, 2.0, 3.0] and draft.uses_series("demand")
    assert scenario.series["electricity_demand"].values == [1.0, 2.0, 3.0]
    assert next(c for c in scenario.components if c.id == "demand").blocks["demand"]["series"] == "electricity_demand"


def test_a_component_without_a_series_has_none():
    draft = draft_of("PV system")

    assert draft.series_of("demand") is None and not draft.uses_series("demand")
    assert draft.scenario().series == {}


def test_the_scenario_is_a_copy_that_does_not_change_the_draft():
    draft = draft_of("PV system")
    give(draft, "demand", [1, 2, 3])

    draft.scenario().series["electricity_demand"].values.append(99.0)

    assert draft.series_of("demand").values == [1.0, 2.0, 3.0]


def test_a_component_that_is_removed_takes_its_series_with_it_and_a_new_one_starts_without():
    draft = draft_of("PV system")
    give(draft, "demand", [1, 2, 3])
    give(draft, "pv", [0.1, 0.2, 0.3])

    draft.set("pv", False)
    assert draft.series_of("pv") is None and "pv_profile" not in draft.scenario().series
    draft.set("pv", True)

    assert draft.series_of("pv") is None
    assert draft.series_of("demand") is not None                           # the others keep theirs


def test_a_template_keeps_the_series_of_the_components_that_stay():
    draft = draft_of("PV system")
    give(draft, "demand", [1, 2, 3])
    give(draft, "pv", [0.1, 0.2, 0.3])

    draft.apply_template("Electricity only")                               # the PV system goes, the demand stays

    assert draft.series_of("demand") is not None and draft.series_of("pv") is None
    assert set(draft.scenario().series) == {"electricity_demand"}


def test_clearing_the_draft_clears_its_series():
    draft = draft_of("PV system")
    give(draft, "demand", [1, 2, 3])

    draft.clear()
    draft.apply_template("PV system")

    assert draft.series_of("demand") is None


def test_a_series_for_a_component_that_is_not_there_is_refused():
    draft = draft_of("Electricity only")

    with pytest.raises(KeyError):
        draft.set_series("pv", SeriesData(values=[1.0]))


def test_a_series_for_a_component_that_has_none_is_refused():
    draft = draft_of("Gas heating")                                         # the gas import is part of it

    with pytest.raises(ValueError, match="'gas_import' has no time series"):
        draft.set_series("gas_import", SeriesData(values=[1.0]))


def test_taking_a_series_away_is_always_possible():
    draft = draft_of("PV system")

    draft.clear_series("demand")                                           # nothing there: nothing happens
    give(draft, "demand", [1, 2, 3])
    draft.clear_series("demand")

    assert draft.series_of("demand") is None
    assert "series" not in draft.component("demand").blocks["demand"]


# ---------------------------------------------------------------------------
# the grid price and the COP: a constant or a series
# ---------------------------------------------------------------------------

def test_the_grid_switches_between_a_price_and_a_series_and_keeps_the_price():
    draft = draft_of("PV system")
    set_value(draft.component("grid"), "costs", "variable_costs", 0.35)

    give(draft, "grid", [0.2, 0.3], price_unit="€/kWh")
    assert draft.uses_series("grid") and scenario_to_v1(draft.scenario()).settings["grid"]["price_mode"] == "timeseries"

    draft.clear_series("grid")

    assert not draft.uses_series("grid") and draft.component("grid").blocks["costs"]["variable_costs"] == 0.35
    assert scenario_to_v1(draft.scenario()).settings["grid"]["price_mode"] == "constant"


def test_a_grid_with_a_series_does_not_need_the_price_but_one_without_does():
    draft = draft_of("PV system")
    draft.component("grid").blocks["costs"].pop("variable_costs")
    needs = lambda: [f for f in draft.findings() if f.code == "value_missing" and "Electricity price" in f.message]

    assert needs()
    give(draft, "grid", [0.2, 0.3])
    assert not needs()
    draft.clear_series("grid")
    assert needs()


def test_the_heat_pump_switches_between_a_cop_and_a_series_and_gets_its_cop_back():
    draft = draft_of("Heat pump + heating rod")
    pump = draft.component("heat_pump")
    set_value(pump, "conversion", "outputs.heat.ratio", 4.2)

    give(draft, "heat_pump", [3.0, 3.2, 3.4])

    assert "ratio" not in pump.blocks["conversion"]["outputs"]["heat"]            # a series and a constant exclude each other
    assert pump.blocks["conversion"]["outputs"]["heat"]["ratio_series"] == "cop_profile"
    settings = scenario_to_v1(draft.scenario()).settings["heat_pump"]
    assert settings["cop_mode"] == "timeseries"

    draft.clear_series("heat_pump")

    assert pump.blocks["conversion"]["outputs"]["heat"] == {"ratio": 4.2}
    assert scenario_to_v1(draft.scenario()).settings["heat_pump"]["cop_value"] == 4.2


def test_a_cop_that_was_cleared_comes_back_as_the_default_after_the_series():
    draft = draft_of("Heat pump + heating rod")
    set_value(draft.component("heat_pump"), "conversion", "outputs.heat.ratio", None)

    give(draft, "heat_pump", [3.0, 3.2])
    draft.clear_series("heat_pump")

    assert draft.component("heat_pump").blocks["conversion"]["outputs"]["heat"] == {"ratio": 3.5}


def test_the_cop_of_a_heat_pump_that_was_removed_is_forgotten():
    draft = draft_of("Heat pump + heating rod")
    set_value(draft.component("heat_pump"), "conversion", "outputs.heat.ratio", 4.2)
    give(draft, "heat_pump", [3.0, 3.2])

    draft.set("heat_pump", False)
    draft.set("heat_pump", True)

    assert draft.component("heat_pump").blocks["conversion"]["outputs"]["heat"] == {"ratio": 3.5}   # the default again


# ---------------------------------------------------------------------------
# the check answers the series
# ---------------------------------------------------------------------------

def codes(draft):
    return [(f.level, f.code) for f in draft.findings()]


def test_a_series_that_is_too_short_is_an_error_and_one_that_is_too_long_a_warning():
    draft = draft_of("Electricity only", steps=24)
    assert ("error", "profile_missing") in codes(draft)

    give(draft, "demand", range(10))
    assert ("error", "series_short") in codes(draft) and ("error", "profile_missing") not in codes(draft)

    give(draft, "demand", range(24))
    assert not any(code in ("series_short", "series_long") for _, code in codes(draft))

    give(draft, "demand", range(30))
    assert ("warning", "series_long") in codes(draft)


def test_empty_values_in_a_series_are_an_error():
    draft = draft_of("Electricity only", steps=4)

    give(draft, "demand", [1, None, 3, 4])

    assert ("error", "series_invalid") in codes(draft)


def test_a_demand_that_does_not_add_up_to_one_over_a_year_gets_a_warning():
    draft = draft_of("Electricity only", steps=8760)

    give(draft, "demand", [0.0002] * 8760)                                  # adds up to 1.752

    assert any(f.code == "profile_shares" for f in draft.findings())


def test_the_series_reach_the_engine_under_their_old_names():
    draft = draft_of("PV system")
    give(draft, "demand", [1, 2, 3])
    give(draft, "pv", [0.1, 0.2, 0.3])
    give(draft, "grid", [25, 30, 35], price_unit="ct/kWh")

    series = scenario_to_v1(draft.scenario()).series

    assert set(series) == {"electricity_demand", "pv", "grid_price"}
    assert series["grid_price"] == pytest.approx([0.25, 0.30, 0.35])


def test_whatever_is_done_with_series_stays_a_valid_scenario():
    rng = random.Random(5)
    draft = ScenarioDraft(steps=24)
    templates = ["PV system", "Electricity only", "Heat pump + heating rod", "Full system", "Gas heating"]
    keys = ["demand", "heat_demand", "pv", "wind", "grid", "heat_pump", "grid_feedin"]

    for _ in range(600):
        action = rng.choice(["template", "give", "clear", "remove", "add", "constant"])
        key = rng.choice(keys)
        if action == "template":
            draft.apply_template(rng.choice(templates))
        elif action == "give" and draft.is_selected(key) and has_series(draft.component(key)):
            give(draft, key, [rng.random() for _ in range(rng.choice([5, 24, 30]))])
        elif action == "clear" and draft.is_selected(key):
            draft.clear_series(key)
        elif action == "remove":
            draft.set(key, False)
        elif action == "add":
            draft.set(key, True)
        elif action == "constant" and draft.is_selected("heat_pump"):
            set_value(draft.component("heat_pump"), "conversion", "outputs.heat.ratio", rng.choice([None, 2.5, 4]))
        draft.scenario()                                                    # must never raise
        draft.findings()


@needs_cbc
def test_a_draft_with_uploaded_series_can_be_run():
    draft = draft_of("PV system", steps=24)
    set_value(draft.component("pv"), "capacity", "capacity", 3)
    draft.component("demand").blocks["demand"]["profile_type"] = "absolute"          # the demand in kW
    give(draft, "demand", [1.0 + 0.5 * math.sin(h / 24 * 6.28) for h in range(24)])
    give(draft, "pv", [max(0.0, math.sin((h - 6) / 12 * math.pi)) for h in range(24)])
    give(draft, "grid", [25 + h % 6 for h in range(24)], price_unit="ct/kWh")

    assert [f for f in draft.findings() if f.level == "error"] == []
    result = service_v2.run(draft.scenario())

    assert 0 < result.objective < 24 * 1.5 * 0.31          # cheaper than buying everything from the grid