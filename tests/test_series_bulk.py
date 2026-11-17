"""One file with all the time series: the suggestion of a column for each component, and the assignment."""

import io
from datetime import datetime, timedelta

import pytest
from openpyxl import Workbook

from backend.timeseries_import import TimeSeriesFileError
from frontend_nicegui.draft import ScenarioDraft
from frontend_nicegui.series_bulk import ADD_ORDER, PRIORITY, RULES, BulkSession, FilePeriod, compact, fits, guess, kind_of
from frontend_nicegui.series_session import START_SCENARIO


def csv(columns, hours=24, step_minutes=60, start="2021-01-01", sep=";"):
    """A CSV file: a time column and a column for each name (given as a function of the number of the row)."""

    names = list(columns)
    rows = [sep.join(["Zeit"] + names)]
    first = datetime.fromisoformat(start)
    for i in range(hours * (60 // step_minutes)):
        stamp = (first + timedelta(minutes=i * step_minutes)).strftime("%Y-%m-%d %H:%M")
        rows.append(sep.join([stamp] + [str(columns[n](i)) for n in names]))

    return ("\n".join(rows) + "\n").encode()


ALL = {
    "Strom_Last": lambda i: 1.0 + i / 10,
    "Waermebedarf": lambda i: 2.0 + i / 10,
    "PV": lambda i: max(0, i - 6) / 10,
    "Strompreis": lambda i: 30 + i,
}


def draft_with(*keys, steps=24):
    draft = ScenarioDraft(steps=steps)
    for key in keys:
        draft.set(key, True)

    return draft


def session_for(keys=("demand", "heat_demand", "pv", "grid"), content=None, columns=ALL, steps=24):
    draft = draft_with(*keys, steps=steps)
    session = BulkSession(content if content is not None else csv(columns), "alle.csv")
    components = BulkSession.components_with_series(draft)
    session.update(components)

    return draft, session, components


# ---------------------------------------------------------------------------
# what a column is called
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("Wärme-Bedarf [kWh]", "warmebedarfkwh"), ("Strom_Last", "stromlast"), ("PV (kW)", "pvkw"), ("Größe", "groe"),
    ("", ""), (12, "12"),
])
def test_a_column_name_is_made_plain_letters_and_digits(name, expected):
    assert compact(name) == expected


@pytest.mark.parametrize("key, column", [
    ("demand", "Strom_Last"), ("demand", "Last"), ("demand", "load_kW"), ("demand", "Strombedarf"), ("demand", "Verbrauch"),
    ("heat_demand", "Waermebedarf"), ("heat_demand", "Wärmelast"), ("heat_demand", "Heat demand"), ("heat_demand", "Heizung"),
    ("pv", "PV"), ("pv", "PV_Profil"), ("pv", "Solar"), ("pv", "Photovoltaik"),
    ("wind", "Wind"), ("wind", "Windkraft"),
    ("grid", "Strompreis"), ("grid", "Preis_EUR_MWh"), ("grid", "Spotpreis"), ("grid", "price"), ("grid", "Börse"),
    ("heat_pump", "COP"), ("heat_pump", "COP_Waermepumpe"), ("heat_pump", "Arbeitszahl"),
])
def test_a_name_that_says_what_the_column_is_fits_its_component(key, column):
    assert fits(key, column)


@pytest.mark.parametrize("key, column", [
    ("demand", "Waermebedarf"), ("demand", "Strompreis"), ("demand", "PV"), ("demand", "Windkraft"), ("demand", "Zeit"),
    ("heat_demand", "COP_Waermepumpe"), ("heat_demand", "Strom_Last"), ("heat_demand", "Waermepreis"),
    ("pv", "PV_Preis"), ("pv", "Wind"), ("wind", "Windpreis"), ("wind", "PV"),
    ("grid", "Gaspreis"), ("grid", "Waermepreis"), ("grid", "Einspeisepreis"), ("grid", "Last"),
    ("heat_pump", "Strom_Last"),
])
def test_a_name_that_says_something_else_does_not_fit(key, column):
    assert not fits(key, column)


def test_a_component_that_the_rules_do_not_know_fits_no_column():
    assert not fits("fusion_reactor", "Strom_Last") and "fusion_reactor" not in RULES


# ---------------------------------------------------------------------------
# the suggestion
# ---------------------------------------------------------------------------

def test_each_component_gets_the_column_that_its_name_suggests():
    columns = ["Zeit_x", "Strom_Last_kW", "Waermebedarf_kW", "PV_Profil", "Wind", "Strompreis_EUR_MWh", "COP_WP", "Gaspreis"]

    found = guess(["demand", "heat_demand", "pv", "wind", "grid", "heat_pump"], columns)

    assert found == {"demand": "Strom_Last_kW", "heat_demand": "Waermebedarf_kW", "pv": "PV_Profil", "wind": "Wind",
                     "grid": "Strompreis_EUR_MWh", "heat_pump": "COP_WP"}


def test_a_component_without_a_matching_column_gets_none():
    assert guess(["demand", "pv"], ["Zeit", "Temperatur"]) == {"demand": None, "pv": None}
    assert guess(["demand"], []) == {"demand": None}


def test_a_column_is_given_to_one_component_only_and_the_specific_components_choose_first():
    # 'Last_Solar' fits the PV system and the demand; the PV system chooses before the demand
    found = guess(["demand", "pv"], ["Last_Solar", "Last"])

    assert found == {"pv": "Last_Solar", "demand": "Last"}
    assert guess(["demand", "pv"], ["Last_Solar"]) == {"pv": "Last_Solar", "demand": None}


def test_the_first_column_that_fits_is_taken_in_the_order_of_the_file():
    assert guess(["demand"], ["Last_B", "Last_A"]) == {"demand": "Last_B"}


def test_columns_that_are_taken_already_are_not_suggested_again():
    assert guess(["demand"], ["Last"], taken={"Last"}) == {"demand": None}


def test_the_priority_covers_every_rule_and_puts_the_demand_last():
    assert set(PRIORITY) == set(RULES) and PRIORITY[-1] == "demand"


# ---------------------------------------------------------------------------
# the assignment of a file
# ---------------------------------------------------------------------------


def test_a_file_is_read_and_the_columns_are_suggested():
    _, session, components = session_for()

    assert session.readable and session.filename == "alle.csv"
    assert session.columns() == list(ALL)
    assert session.mapping == {"demand": "Strom_Last", "heat_demand": "Waermebedarf", "pv": "PV", "grid": "Strompreis"}
    assert {c.template: column for c, column in session.assigned(components)} == session.mapping


def test_only_the_components_with_a_time_series_are_assigned():
    draft = draft_with("demand", "pv", "grid", "battery", "gas_boiler")

    assert sorted(c.template for c in BulkSession.components_with_series(draft)) == ["demand", "grid", "pv"]


def test_every_assigned_column_gives_a_series_of_the_length_of_the_file():
    draft, session, components = session_for()

    results = session.results(components, draft.start)

    assert set(results) == {"demand", "heat_demand", "pv", "grid"}
    assert all(problem is None and len(data.values) == 24 for data, problem in results.values())
    assert results["demand"][0].values[:3] == pytest.approx([1.0, 1.1, 1.2]) and results["pv"][0].values[6] == 0.0


def test_a_series_knows_the_file_and_the_column_that_it_came_from():
    draft, session, components = session_for()

    source = session.results(components, draft.start)["pv"][0].source

    assert source.file == "alle.csv" and source.column == "PV"


def test_applying_gives_each_assigned_component_its_series_and_says_which():
    draft, session, components = session_for()

    done = session.apply(draft, components)

    assert sorted(done) == ["demand", "grid", "heat_demand", "pv"]
    assert draft.series_of("heat_demand").values[:2] == pytest.approx([2.0, 2.1]) and draft.uses_series("grid")


def test_a_component_set_to_none_keeps_what_it_had():
    draft, session, components = session_for()
    pv = next(c for c in components if c.template == "pv")
    draft.set_series("pv", session.build(pv, "Strom_Last", draft.start))
    before = draft.series_of("pv")
    session.choose("pv", None)

    done = session.apply(draft, components)

    assert "pv" not in done and draft.series_of("pv") is before


def test_a_column_of_the_file_replaces_a_series_that_was_uploaded_on_its_own():
    draft, session, components = session_for(("demand", "pv"))
    pv = next(c for c in components if c.template == "pv")
    draft.set_series("pv", session.build(pv, "Strom_Last", draft.start))

    session.apply(draft, components)

    assert draft.series_of("pv").source.column == "PV"


def test_choosing_a_column_and_choosing_none():
    draft, session, components = session_for()

    session.choose("demand", "Waermebedarf")
    assert session.mapping["demand"] == "Waermebedarf"
    session.choose("demand", None)

    assert session.mapping["demand"] is None and "demand" not in [c.template for c, _ in session.assigned(components)]


def test_a_column_that_was_chosen_for_one_component_is_not_suggested_for_another():
    draft, session, components = session_for(("demand", "heat_demand"), columns={"Last": lambda i: 1.0, "Wärmelast": lambda i: 2.0})
    assert session.mapping == {"heat_demand": "Wärmelast", "demand": "Last"}

    session.choose("demand", "Wärmelast")
    session.update(components)

    assert session.mapping == {"demand": "Wärmelast", "heat_demand": None}


def test_what_was_set_to_none_stays_none_when_the_assignment_is_updated():
    draft, session, components = session_for()
    session.choose("demand", None)

    session.update(components)

    assert session.mapping["demand"] is None                               # the visitor said none: it is not suggested again


def test_a_component_that_is_added_later_gets_a_suggestion_from_the_columns_that_are_left():
    draft, session, components = session_for(("demand",))
    draft.set("pv", True)

    session.update(BulkSession.components_with_series(draft))

    assert session.mapping == {"demand": "Strom_Last", "pv": "PV"}


def test_a_component_that_is_taken_out_loses_its_entry_and_its_column_is_free_again():
    draft, session, components = session_for()
    draft.set("pv", False)

    session.update(BulkSession.components_with_series(draft))

    assert "pv" not in session.mapping
    draft.set("wind", True)
    session.update(BulkSession.components_with_series(draft))
    assert session.mapping["wind"] is None                                 # 'PV' is no column for the wind turbine


def test_a_column_that_is_not_there_after_the_file_was_read_again_is_forgotten_and_suggested_again():
    draft, session, components = session_for(("demand", "pv"), content=csv({"Last": lambda i: 1.0, "Solar": lambda i: 2.0}))
    assert session.mapping == {"demand": "Last", "pv": "Solar"}

    session.master.change(delimiter=",")                                   # a wrong delimiter: the file is one text column
    session.update(components)
    assert session.columns() == [] and session.mapping == {"demand": None, "pv": None}

    session.master.change(delimiter=None)                                  # detected again: the columns are back
    session.update(components)

    assert session.mapping == {"demand": "Last", "pv": "Solar"}


# ---------------------------------------------------------------------------
# what cannot be done
# ---------------------------------------------------------------------------

def test_a_file_that_cannot_be_read_says_why_and_has_no_columns():
    session = BulkSession(b"\x00\x01\x02 not a table", "kaputt.csv")

    assert not session.readable and isinstance(session.error, TimeSeriesFileError) and session.columns() == []


def test_a_file_without_a_numeric_column_gives_no_suggestion():
    draft, session, components = session_for(content=b"Zeit;Name\n2021-01-01 00:00;a\n2021-01-01 01:00;b\n")

    assert session.mapping == {"demand": None, "heat_demand": None, "pv": None, "grid": None}
    assert session.results(components, draft.start) == {} and not session.usable(components, draft)


def test_nothing_is_usable_when_no_column_is_assigned():
    draft, session, components = session_for()
    for key in list(session.mapping):
        session.choose(key, None)

    assert not session.usable(components, draft) and session.apply(draft, components) == []


def test_a_start_that_the_file_does_not_cover_is_a_problem_for_every_column_that_uses_it():
    draft, session, components = session_for()
    session.master.start_choice = START_SCENARIO
    draft.start = "2022-01-01"

    results = session.results(components, draft.start)

    assert {problem.code for _, problem in results.values()} == {"start_outside"}
    assert not session.usable(components, draft)


def test_when_one_column_has_a_problem_only_the_others_are_applied():
    draft = draft_with("demand", "pv")
    draft.component("demand").blocks["demand"]["profile_type"] = "absolute"        # a demand in kW: the quarter hours need an answer
    session = BulkSession(csv({"Last": lambda i: 2.0, "PV": lambda i: 1.0}, step_minutes=15), "viertel.csv")
    components = BulkSession.components_with_series(draft)
    session.update(components)

    assert not session.usable(components, draft)
    done = session.apply(draft, components)

    assert done == ["pv"] and draft.series_of("pv") is not None and draft.series_of("demand") is None


def test_a_file_of_quarter_hours_needs_the_answer_for_a_demand_in_kw_and_not_for_other_components():
    draft = draft_with("demand", "pv")
    draft.component("demand").blocks["demand"]["profile_type"] = "absolute"
    session = BulkSession(csv({"Last": lambda i: 2.0, "PV": lambda i: 1.0}, step_minutes=15), "viertel.csv")
    components = BulkSession.components_with_series(draft)
    session.update(components)

    assert session.needs_aggregate(components)
    results = session.results(components, draft.start)
    assert results["demand"][1].code == "convert_needed" and results["pv"][1] is None      # a PV profile is averaged

    session.master.aggregate = "mean"

    assert session.usable(components, draft) and len(session.results(components, draft.start)["demand"][0].values) == 24


def test_a_demand_as_a_share_of_the_year_needs_no_answer_for_quarter_hours():
    draft = draft_with("demand")                                           # the default: a share of the annual demand
    session = BulkSession(csv({"Last": lambda i: 1.0}, step_minutes=15), "viertel.csv")
    components = BulkSession.components_with_series(draft)
    session.update(components)

    assert not session.needs_aggregate(components) and session.usable(components, draft)


def test_the_notices_of_a_column_are_those_of_the_column_and_not_those_of_the_whole_file():
    draft = draft_with("pv")
    session = BulkSession(csv({"PV": lambda i: 1.0}, step_minutes=15), "viertel.csv")
    components = BulkSession.components_with_series(draft)
    session.update(components)

    file_codes = {notice.code for notice in session.master.table.messages}
    column_codes = {notice.code for notice in session.notices(components[0], "PV")}

    assert file_codes and column_codes and not file_codes & column_codes


def test_a_column_that_cannot_be_made_a_series_has_no_notices_of_its_own():
    draft = draft_with("demand")
    draft.component("demand").blocks["demand"]["profile_type"] = "absolute"                  # the quarter hours need an answer
    session = BulkSession(csv({"Last": lambda i: 1.0}, step_minutes=15), "viertel.csv")
    components = BulkSession.components_with_series(draft)
    session.update(components)

    assert session.notices(components[0], "Last") == []                    # the problem is shown on its own


def test_the_unit_of_a_price_is_used_for_the_grid():
    draft, session, components = session_for()

    assert session.results(components, draft.start)["grid"][0].values[0] == 30.0         # in euro per kWh as it is
    session.master.price_unit = "€/MWh"

    assert session.results(components, draft.start)["grid"][0].values[:2] == pytest.approx([0.03, 0.031])
    assert session.results(components, draft.start)["demand"][0].values[0] == 1.0         # the unit is for the price only


# ---------------------------------------------------------------------------
# an Excel file
# ---------------------------------------------------------------------------

def workbook(sheets):
    book = Workbook()
    book.remove(book.active)
    for name, (header, rows) in sheets.items():
        sheet = book.create_sheet(name)
        sheet.append(header)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)

    return buffer.getvalue()


def test_the_columns_of_the_sheet_that_is_chosen_are_assigned():
    stamps = [datetime(2021, 1, 1, h) for h in range(24)]
    content = workbook({
        "Notizen": (["Text"], [["nichts"]]),
        "Zeitreihen": (["Zeit", "Last", "Solar"], [[stamp, 1.0 + h, h / 10] for h, stamp in enumerate(stamps)]),
    })
    draft = draft_with("demand", "pv")
    session = BulkSession(content, "alle.xlsx")
    components = BulkSession.components_with_series(draft)

    session.master.change(sheet="Zeitreihen")
    session.update(components)

    assert session.master.sheets() == ["Notizen", "Zeitreihen"]
    assert session.mapping == {"demand": "Last", "pv": "Solar"}
    assert sorted(session.apply(draft, components)) == ["demand", "pv"]
    assert draft.series_of("demand").values[:2] == [1.0, 2.0]


# ---------------------------------------------------------------------------
# what the file holds
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("column, key", [
    ("Strom_Last", "demand"), ("Waermebedarf", "heat_demand"), ("PV", "pv"), ("Windkraft", "wind"),
    ("Strompreis", "grid"), ("COP", "heat_pump"), ("Last_Solar", "pv"), ("Temperatur", None), ("Zeit", None),
    ("Sonnenstrom", "pv"),                                              # fits the PV system ('sonne') and the demand ('strom')
])
def test_a_column_looks_like_the_component_that_its_name_says_and_the_specific_ones_come_first(column, key):
    assert kind_of(column) == key


def test_the_overview_has_a_row_for_each_column_with_the_values_that_are_filled_and_what_it_looks_like():
    content = csv({"Strom_Last": lambda i: 1.0, "Temperatur": lambda i: "" if i % 4 == 0 else 5.0, "PV": lambda i: 0.5})
    draft, session, components = session_for(("demand",), content=content)

    assert session.overview() == [
        {"column": "Strom_Last", "values": 24, "kind": "demand"},
        {"column": "Temperatur", "values": 18, "kind": None},                  # six of 24 values are empty
        {"column": "PV", "values": 24, "kind": "pv"},
    ]


def test_a_file_that_cannot_be_read_has_no_overview_and_no_period():
    session = BulkSession(b"\x00\x01\x02 not a table", "kaputt.csv")

    assert session.overview() == [] and session.period() is None


def test_the_period_of_a_file_is_when_it_starts_and_ends_and_how_many_hours_it_has():
    session = BulkSession(csv({"Last": lambda i: 1.0}, hours=72, start="2021-03-05"), "drei_tage.csv")

    period = session.period()

    assert period == FilePeriod(start=datetime(2021, 3, 5, 0, 0), end=datetime(2021, 3, 7, 23, 0), hours=72)


def test_a_time_step_shorter_than_an_hour_counts_as_the_part_of_an_hour_that_it_is():
    session = BulkSession(csv({"Last": lambda i: 1.0}, hours=48, step_minutes=15), "viertel.csv")

    assert session.period().hours == 48 and session.period().end == datetime(2021, 1, 2, 23, 45)


def test_a_file_without_dates_has_as_many_hours_as_rows_and_no_start():
    rows = ["Last;Solar"] + [f"{1 + i / 10};{i / 10}" for i in range(96)]
    session = BulkSession(("\n".join(rows) + "\n").encode(), "ohne_datum.csv")

    assert session.period() == FilePeriod(start=None, end=None, hours=96)


def test_the_period_of_an_excel_file_is_read_too():
    stamps = [datetime(2022, 6, 1, h) for h in range(24)]
    session = BulkSession(workbook({"Blatt": (["Zeit", "Last"], [[s, 1.0] for s in stamps])}), "daten.xlsx")

    assert session.period() == FilePeriod(start=datetime(2022, 6, 1), end=datetime(2022, 6, 1, 23), hours=24)


# ---------------------------------------------------------------------------
# the components that the columns suggest
# ---------------------------------------------------------------------------

def test_the_columns_suggest_the_components_that_are_not_in_the_draft_in_a_fixed_order():
    session = BulkSession(csv({**ALL, "Wind": lambda i: 0.2, "COP": lambda i: 3.0}), "alle.csv")

    assert session.suggested_components(draft_with()) == ["demand", "heat_demand", "grid", "pv", "wind", "heat_pump"]
    assert list(ADD_ORDER) == ["demand", "heat_demand", "grid", "pv", "wind", "heat_pump"]


def test_a_component_that_the_draft_has_already_is_not_suggested_again():
    session = BulkSession(csv(ALL), "alle.csv")

    assert session.suggested_components(draft_with("demand", "pv")) == ["heat_demand", "grid"]
    assert session.suggested_components(draft_with("demand", "heat_demand", "grid", "pv")) == []


def test_a_column_that_looks_like_nothing_suggests_no_component():
    session = BulkSession(csv({"Temperatur": lambda i: 5.0, "Luftdruck": lambda i: 1000.0}), "wetter.csv")

    assert session.suggested_components(draft_with()) == []


def test_one_column_suggests_one_component_only():
    session = BulkSession(csv({"Last_Solar": lambda i: 1.0}), "eine.csv")

    assert session.suggested_components(draft_with()) == ["pv"]             # the PV system takes it, not the demand too


# ---------------------------------------------------------------------------
# what was taken over
# ---------------------------------------------------------------------------

def test_what_was_taken_over_is_used_and_is_not_pending_any_more():
    draft, session, components = session_for()
    assert sorted(session.pending(components, draft)) == ["demand", "grid", "heat_demand", "pv"]

    session.apply(draft, components)

    assert session.pending(components, draft) == []
    assert all(session.is_used(key, column, draft) for key, column in session.mapping.items())
    assert not session.usable(components, draft)                           # nothing is left to take over


def test_applying_again_takes_nothing_twice():
    draft, session, components = session_for()
    first = session.apply(draft, components)
    series = {key: draft.series_of(key) for key in first}

    again = session.apply(draft, components)

    assert sorted(first) == ["demand", "grid", "heat_demand", "pv"] and again == []
    assert all(draft.series_of(key) is series[key] for key in first)       # the series were not made again


def test_a_component_that_is_added_later_is_pending_while_the_others_stay_used():
    draft, session, components = session_for(("demand",))
    session.apply(draft, components)
    draft.set("pv", True)
    components = BulkSession.components_with_series(draft)
    session.update(components)

    assert session.pending(components, draft) == ["pv"] and session.usable(components, draft)
    assert session.apply(draft, components) == ["pv"]


def test_a_series_that_was_taken_away_is_pending_again():
    draft, session, components = session_for(("demand", "pv"))
    session.apply(draft, components)

    draft.clear_series("pv")

    assert session.pending(components, draft) == ["pv"] and not session.is_used("pv", "PV", draft)


def test_a_series_that_was_replaced_by_another_file_is_pending_again():
    draft, session, components = session_for(("demand", "pv"))
    session.apply(draft, components)
    other = BulkSession(csv({"PV": lambda i: 9.0}), "anders.csv")
    pv = next(c for c in components if c.template == "pv")

    draft.set_series("pv", other.build(pv, "PV", draft.start))

    assert session.pending(components, draft) == ["pv"]


@pytest.mark.parametrize("name, value", [("price_unit", "€/MWh"), ("start_choice", START_SCENARIO), ("aggregate", "sum")])
def test_a_choice_that_changes_the_series_makes_what_was_taken_pending_again(name, value):
    draft, session, components = session_for()
    session.apply(draft, components)

    setattr(session.master, name, value)

    assert sorted(session.pending(components, draft)) == ["demand", "grid", "heat_demand", "pv"]


def test_the_import_settings_and_the_start_of_the_scenario_make_what_was_taken_pending_again_too():
    draft, session, components = session_for()
    session.apply(draft, components)
    session.master.change(decimal=".")

    assert len(session.pending(components, draft)) == 4

    session.apply(draft, components)
    assert session.pending(components, draft) == []
    draft.start = "2021-01-02"

    assert len(session.pending(components, draft)) == 4


def test_taking_over_the_price_in_another_unit_replaces_the_series_of_the_grid():
    draft, session, components = session_for(("grid",))
    session.apply(draft, components)
    assert draft.series_of("grid").values[0] == 30.0

    session.master.price_unit = "€/MWh"
    session.apply(draft, components)

    assert draft.series_of("grid").values[:2] == pytest.approx([0.03, 0.031])


def test_with_something_taken_over_and_something_pending_the_pending_ones_decide_if_it_is_usable():
    draft = draft_with("demand", "pv")
    draft.component("demand").blocks["demand"]["profile_type"] = "absolute"
    session = BulkSession(csv({"Last": lambda i: 2.0, "PV": lambda i: 1.0}, step_minutes=15), "viertel.csv")
    components = BulkSession.components_with_series(draft)
    session.update(components)
    session.master.aggregate = "mean"
    session.apply(draft, components)

    session.master.aggregate = None

    assert sorted(session.pending(components, draft)) == ["demand", "pv"] and not session.usable(components, draft)