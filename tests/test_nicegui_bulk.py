"""One file with all the time series on the NiceGUI page: the card, the assignment, using it (simulated user)."""

import re

import pytest

pytest.importorskip("nicegui")
from nicegui import ui  # noqa: E402
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402

from tests.test_nicegui_draft_run import exists, field, give_demand, settle, switched_to  # noqa: E402
from tests.test_nicegui_frame import views  # noqa: E402
from tests.test_series_bulk import ALL, csv, workbook  # noqa: E402

KEYS = ("demand", "heat_demand", "pv", "grid")
NONE = "__none__"


async def open_with(user: User, *keys, language=None, steps=24):
    """Open the page, choose the components (one by one) and the period."""

    await user.open("/" if language is None else f"/?lang={language}")
    for key in keys:
        user.find(marker=f"component-{key}").click()
    user.find(marker="draft-steps").clear().type(str(steps))
    await settle()


async def upload(user: User, content, name="alle.csv", kind="text/csv"):
    await field(user, "series-bulk-upload").handle_uploads([SmallFileUpload(name, kind, content)])
    await user.should_see(marker="series-bulk-prepare")


def texts(user, marker):
    """All the texts below an element, in order."""

    with user.client:
        return [e.text for e in field(user, marker).descendants() if isinstance(e, ui.label)]


def choice(user, key):
    return field(user, f"series-bulk-map-{key}").value


async def use_it(user: User):
    user.find(marker="series-bulk-use").click()
    await settle()


# ---------------------------------------------------------------------------
# the card
# ---------------------------------------------------------------------------

async def test_the_card_is_in_the_system_view_and_takes_a_file_even_before_any_component_is_chosen(user: User):
    await user.open("/")

    await user.should_see("All time series from one file")
    assert exists(user, "series-bulk") and exists(user, "series-bulk-upload")
    assert not exists(user, "series-bulk-empty") and not exists(user, "series-bulk-prepare")      # no file, nothing to say yet


async def test_the_card_comes_before_the_card_for_opening_a_scenario_file_and_after_the_board(user: User):
    await open_with(user, "demand")

    order = list(user.client.content.descendants())

    assert order.index(field(user, "lane-electricity")) < order.index(field(user, "series-bulk")) < order.index(field(user, "upload"))


# ---------------------------------------------------------------------------
# the assignment
# ---------------------------------------------------------------------------

async def test_a_file_gets_a_row_for_each_component_with_a_series_and_a_suggested_column(user: User):
    await open_with(user, *KEYS)

    await upload(user, csv(ALL))

    assert {key: choice(user, key) for key in KEYS} == {
        "demand": "Strom_Last", "heat_demand": "Waermebedarf", "pv": "PV", "grid": "Strompreis"}
    for key in KEYS:
        assert texts(user, f"series-bulk-status-{key}") == ["24 values will be used."], key
    assert field(user, "series-bulk-use").text == "Use 4 time series"


async def test_the_file_is_shown_before_it_is_used(user: User):
    await open_with(user, *KEYS)

    await upload(user, csv(ALL))

    assert exists(user, "series-preview-bulk")
    await user.should_see("File: alle.csv")
    await user.should_see("Which column belongs to which component?")
    assert not exists(user, "series-summary-demand")                       # nothing is used until the visitor says so


async def test_a_column_can_be_changed_and_set_to_none(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))

    field(user, "series-bulk-map-pv").set_value(NONE)
    await settle()

    assert choice(user, "pv") == NONE
    assert texts(user, "series-bulk-status-pv") == ["Not taken from this file; the series stays as it is."]
    assert field(user, "series-bulk-use").text == "Use 3 time series"

    field(user, "series-bulk-map-pv").set_value("PV")
    await settle()

    assert texts(user, "series-bulk-status-pv") == ["24 values will be used."] and field(user, "series-bulk-use").text == "Use 4 time series"


async def test_a_column_that_is_chosen_for_one_component_is_taken_from_the_one_it_was_suggested_for(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))

    field(user, "series-bulk-map-pv").set_value("Strom_Last")             # the column that was suggested for the demand
    await settle()

    assert choice(user, "pv") == "Strom_Last" and choice(user, "demand") == NONE
    assert texts(user, "series-bulk-status-demand") == ["Not taken from this file; the series stays as it is."]
    assert field(user, "series-bulk-use").text == "Use 3 time series"


async def test_with_no_column_assigned_there_is_nothing_to_use(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))

    for key in KEYS:
        field(user, f"series-bulk-map-{key}").set_value(NONE)
        await settle()

    assert exists(user, "series-bulk-nothing") and not exists(user, "series-bulk-use")
    assert field(user, "series-bulk-nothing").text == "No column is assigned yet."


async def test_a_component_that_is_taken_out_loses_its_row_and_one_that_is_added_gets_one(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))

    user.find(marker="component-pv").click()
    await settle()
    assert not exists(user, "series-bulk-map-pv") and exists(user, "series-bulk-map-demand")
    assert exists(user, "series-bulk-prepare")                             # the file stays

    user.find(marker="component-wind").click()
    await settle()
    assert exists(user, "series-bulk-map-wind") and choice(user, "wind") == NONE      # no column called wind


async def test_the_card_follows_a_component_that_is_added_or_removed_on_the_board(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))

    user.find(marker="add-wind").click()                                   # the Add button of the board
    await settle()
    assert exists(user, "series-bulk-map-wind")

    user.find(marker="tile-pv").click()
    user.find(marker="drawer-remove-pv").click()                           # the Remove button of the side sheet
    await settle()
    assert not exists(user, "series-bulk-map-pv") and exists(user, "series-bulk-map-demand")


async def test_the_card_follows_a_template_and_clearing_the_selection(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))

    user.find(marker="template-electricity-only").click()                  # a demand and the grid
    await settle()
    assert exists(user, "series-bulk-map-demand") and not exists(user, "series-bulk-map-pv")
    assert not exists(user, "series-bulk-map-heat_demand")

    user.find(marker="clear-selection").click()
    await settle()
    assert exists(user, "series-bulk-empty") and exists(user, "series-bulk-upload")      # the file stays, without rows
    assert exists(user, "series-bulk-columns") and not exists(user, "series-bulk-map-demand")


async def test_the_options_for_the_grid_and_the_start_of_the_file_are_there_when_they_are_needed(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))

    assert exists(user, "series-price-unit-bulk") and exists(user, "series-start-bulk")
    field(user, "series-bulk-map-grid").set_value(NONE)
    await settle()
    assert not exists(user, "series-price-unit-bulk")                      # the price unit is for the grid only


async def test_a_file_that_does_not_include_the_start_of_the_scenario_says_so(user: User):
    await open_with(user, "demand")

    await upload(user, csv({"Last": lambda i: 1.0}, start="2020-06-01"))

    assert exists(user, "series-start-note-bulk") and not exists(user, "series-start-bulk")
    assert texts(user, "series-bulk-status-demand") == ["24 values will be used."]      # it is used from its first row


# ---------------------------------------------------------------------------
# using the file
# ---------------------------------------------------------------------------

async def test_using_the_file_gives_each_component_its_series_and_says_so(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))
    assert exists(user, "problems-demand")                                 # the check says that the demand has no data

    await use_it(user)

    for key in KEYS:
        assert exists(user, f"series-summary-{key}"), key
    assert texts(user, "series-summary-demand")[0].startswith("24 values from 1 to 3.3")
    assert texts(user, "series-summary-pv")[1] == "From the file alle.csv, column PV."
    assert field(user, "series-bulk-done").text == "4 time series were taken from the file alle.csv."
    assert not exists(user, "problems-demand")                             # the check follows: the demand has its data now
    assert exists(user, "series-bulk-prepare") and exists(user, "series-bulk-upload")      # the file stays for later
    assert all(texts(user, f"series-bulk-status-{key}") == ["Taken from this file."] for key in KEYS)
    assert not exists(user, "series-bulk-use")
    assert field(user, "series-bulk-all-used").text == "Everything that is assigned has been taken over."


async def test_one_series_is_said_in_the_singular(user: User):
    await open_with(user, "demand")

    await upload(user, csv({"Last": lambda i: 1.0}))
    assert field(user, "series-bulk-use").text == "Use 1 time series"
    await use_it(user)

    assert field(user, "series-bulk-done").text == "1 time series was taken from the file alle.csv."


async def test_a_new_file_takes_the_message_about_the_last_one_away(user: User):
    await open_with(user, "demand")
    await upload(user, csv({"Last": lambda i: 1.0}))
    await use_it(user)
    assert exists(user, "series-bulk-done")

    await field(user, "series-bulk-upload").handle_uploads([SmallFileUpload("neu.csv", "text/csv", csv({"Last": lambda i: 2.0}))])
    await settle()

    assert not exists(user, "series-bulk-done") and texts(user, "series-bulk-status-demand") == ["24 values will be used."]
    await user.should_see("File: neu.csv")


async def test_the_unit_of_the_price_is_used(user: User):
    await open_with(user, "grid")
    await upload(user, csv({"Strompreis": lambda i: 30 + i}))

    field(user, "series-price-unit-bulk").set_value("€/MWh")
    await settle()
    await use_it(user)

    assert texts(user, "series-summary-grid")[0].startswith("24 values from 0.03 to 0.053")


async def test_removing_the_file_throws_it_away(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))

    user.find(marker="series-bulk-remove").click()
    await settle()

    assert not exists(user, "series-bulk-prepare") and not exists(user, "series-summary-demand")
    assert exists(user, "series-bulk-upload") and not exists(user, "series-bulk-remove")


async def test_a_file_that_cannot_be_read_is_explained(user: User):
    await open_with(user, *KEYS)

    await upload(user, b"\x00\x01\x02 this is not a table", name="kaputt.csv")

    assert exists(user, "series-bulk-error") and not exists(user, "series-bulk-use") and not exists(user, "series-bulk-map-demand")
    assert not exists(user, "series-bulk-columns")
    user.find(marker="series-bulk-remove").click()
    await settle()
    assert not exists(user, "series-bulk-prepare")


# ---------------------------------------------------------------------------
# an Excel file, quarter hours, and the single upload next to it
# ---------------------------------------------------------------------------

async def test_an_excel_file_with_several_sheets_asks_for_the_sheet(user: User):
    from datetime import datetime

    await open_with(user, "demand", "pv")
    content = workbook({
        "Notizen": (["Text"], [["nichts"]]),
        "Zeitreihen": (["Zeit", "Last", "Solar"], [[datetime(2021, 1, 1, h), 1.0 + h, h / 10] for h in range(24)]),
    })

    await upload(user, content, name="alle.xlsx", kind="application/vnd.ms-excel")
    assert exists(user, "series-sheet-bulk")

    field(user, "series-sheet-bulk").set_value("Zeitreihen")
    await settle()

    assert choice(user, "demand") == "Last" and choice(user, "pv") == "Solar"
    await use_it(user)
    assert exists(user, "series-summary-demand") and exists(user, "series-summary-pv")


async def test_a_file_of_quarter_hours_asks_how_a_demand_in_kw_is_converted_before_it_can_be_used(user: User):
    await open_with(user, "demand", "pv")
    field(user, "field-demand-demand-profile_type").value = "absolute"
    await settle()

    await upload(user, csv({"Last": lambda i: 2.0, "PV": lambda i: 1.0}, step_minutes=15))

    assert exists(user, "series-aggregate-bulk") and not exists(user, "series-bulk-use")
    assert texts(user, "series-bulk-status-demand") == [                   # the row says why the demand cannot be used yet
        "The time step of the file is 15 minutes, but the model works with hourly values. "
        "Choose how to convert the values to hourly values."]
    assert texts(user, "series-bulk-status-pv") == ["24 values will be used."]      # a PV profile needs no answer
    field(user, "series-aggregate-bulk").set_value("mean")
    await settle()

    assert exists(user, "series-bulk-use") and texts(user, "series-bulk-status-demand") == ["24 values will be used."]


async def test_the_single_upload_in_the_settings_of_a_component_still_works_next_to_it(user: User):
    await open_with(user, "demand", "pv")
    await give_demand(user, values=[2.0] * 24)
    assert exists(user, "series-summary-demand") and exists(user, "series-upload-pv")

    await upload(user, csv({"Solar": lambda i: 1.0}))                      # a file for the PV system only: no column for the demand
    assert choice(user, "demand") == NONE
    await use_it(user)

    assert texts(user, "series-summary-demand")[1] == "From the file daten.csv, column Last."       # it was not touched
    assert texts(user, "series-summary-pv")[1] == "From the file alle.csv, column Solar."


async def test_a_file_that_was_being_prepared_for_one_component_is_out_of_date_when_the_big_file_is_used(user: User):
    await open_with(user, "pv")
    await field(user, "series-upload-pv").handle_uploads([SmallFileUpload("einzeln.csv", "text/csv", csv({"Solar": lambda i: 3.0}))])
    await user.should_see(marker="series-prepare-pv")                      # the single upload is being prepared

    await upload(user, csv({"PV": lambda i: 1.0}))
    await use_it(user)

    assert not exists(user, "series-prepare-pv")
    assert texts(user, "series-summary-pv")[1] == "From the file alle.csv, column PV."


async def test_a_column_of_the_file_replaces_a_series_that_was_uploaded_on_its_own(user: User):
    await open_with(user, "demand")
    await give_demand(user, values=[2.0] * 24)

    await upload(user, csv({"Last": lambda i: 5.0}))
    await use_it(user)

    assert texts(user, "series-summary-demand")[1] == "From the file alle.csv, column Last."


# ---------------------------------------------------------------------------
# language
# ---------------------------------------------------------------------------

async def test_the_card_is_in_german(user: User):
    await open_with(user, *KEYS, language="de")

    await user.should_see("Alle Zeitreihen aus einer Datei")
    await upload(user, csv(ALL))
    assert texts(user, "series-bulk-status-demand") == ["24 Werte werden verwendet."]
    assert field(user, "series-bulk-use").text == "4 Zeitreihen übernehmen"
    assert field(user, "series-bulk-map-demand").props["label"] == "Spalte für Strombedarf"

    await use_it(user)

    assert field(user, "series-bulk-done").text == "4 Zeitreihen wurden aus der Datei alle.csv übernommen."


async def test_the_file_and_the_assignment_stay_when_the_language_changes(user: User):
    await open_with(user, *KEYS)
    await upload(user, csv(ALL))
    field(user, "series-bulk-map-pv").set_value(NONE)
    await settle()

    await switched_to(user, "de")

    assert choice(user, "pv") == NONE and choice(user, "demand") == "Strom_Last"
    assert field(user, "series-bulk-use").text == "3 Zeitreihen übernehmen"


# ---------------------------------------------------------------------------
# the button in the top bar
# ---------------------------------------------------------------------------

def record_scrolling(monkeypatch):
    """Take over what the page tells the browser to run (the scrolling), and give the list of it."""

    calls = []
    monkeypatch.setattr(ui, "run_javascript", lambda code, **kwargs: calls.append(code))

    return calls


def scrolled_to(user, code):
    """The element that a call of the scrolling goes to."""

    return user.client.elements[int(re.search(r'getElementById\("c(\d+)"\)', code).group(1))]


def tooltip_of(user, marker):
    """The hint of a button: it is the element that follows the button in its parent."""

    button = field(user, marker)
    siblings = list(button.parent_slot.parent.default_slot.children)
    following = siblings[siblings.index(button) + 1]

    return [following.text] if isinstance(following, ui.tooltip) else []


async def test_the_top_bar_has_a_button_for_the_file_with_all_the_time_series(user: User):
    await user.open("/")

    assert field(user, "header-series").text == "Time series file"
    assert tooltip_of(user, "header-series") == ["Go to the upload of all time series from one file"]
    order = list(user.client.layout.descendants())
    assert order.index(field(user, "header-series")) < order.index(field(user, "status"))      # before the status and Run


async def test_the_button_is_in_german_and_follows_the_language(user: User):
    await user.open("/")

    await switched_to(user, "de")

    assert field(user, "header-series").text == "Zeitreihen-Datei"
    assert tooltip_of(user, "header-series") == ["Zum Hochladen aller Zeitreihen aus einer Datei"]


async def test_the_button_shows_the_system_view_when_another_view_is_open(user: User, monkeypatch):
    record_scrolling(monkeypatch)
    await open_with(user, "demand")
    views(user).set_value("results")
    assert views(user).value == "results"

    user.find(marker="header-series").click()

    assert views(user).value == "system"


async def test_the_button_scrolls_to_the_card_for_the_file(user: User, monkeypatch):
    calls = record_scrolling(monkeypatch)
    await open_with(user, "demand")

    user.find(marker="header-series").click()

    assert len(calls) == 1 and "scrollIntoView" in calls[0] and "setTimeout" in calls[0]     # a moment later: the view is there
    assert field(user, "series-bulk") in list(scrolled_to(user, calls[0]).descendants())      # to a place that holds the card


async def test_the_button_goes_there_every_time_and_also_before_any_component_is_chosen(user: User, monkeypatch):
    calls = record_scrolling(monkeypatch)
    await user.open("/")

    user.find(marker="header-series").click()
    user.find(marker="header-series").click()

    assert len(calls) == 2 and exists(user, "series-bulk-upload")           # the card takes a file right away


async def test_the_place_that_is_scrolled_to_stays_when_the_card_is_drawn_again(user: User, monkeypatch):
    calls = record_scrolling(monkeypatch)
    await open_with(user, "demand")
    user.find(marker="header-series").click()

    user.find(marker="component-pv").click()                               # the card is drawn again for the new component
    await upload(user, csv({"Last": lambda i: 1.0, "PV": lambda i: 2.0}))
    user.find(marker="header-series").click()

    assert scrolled_to(user, calls[0]) is scrolled_to(user, calls[1])
    assert field(user, "series-bulk") in list(scrolled_to(user, calls[1]).descendants())


async def test_the_place_is_new_after_the_language_changed_and_the_button_still_goes_there(user: User, monkeypatch):
    calls = record_scrolling(monkeypatch)
    await open_with(user, "demand")

    await switched_to(user, "de")
    user.find(marker="header-series").click()

    assert field(user, "series-bulk") in list(scrolled_to(user, calls[-1]).descendants())


# ---------------------------------------------------------------------------
# the file first, the components later
# ---------------------------------------------------------------------------

def columns_of(user):
    """The rows of the table of the columns of the file."""

    return field(user, "series-bulk-columns").rows


async def test_a_file_can_be_uploaded_before_any_component_is_chosen_and_the_card_shows_what_it_holds(user: User):
    await user.open("/")

    await upload(user, csv(ALL))

    assert columns_of(user) == [
        {"column": "Strom_Last", "values": "24", "kind": "Electricity demand"},
        {"column": "Waermebedarf", "values": "24", "kind": "Heat demand"},
        {"column": "PV", "values": "24", "kind": "PV system"},
        {"column": "Strompreis", "values": "24", "kind": "Electricity grid"},
    ]
    assert field(user, "series-bulk-period-info").text == "Period of the file: 2021-01-01 00:00 to 2021-01-01 23:00 (24 hours)"
    assert field(user, "series-bulk-empty").text.startswith("No component with a time series is chosen yet.")
    assert not exists(user, "series-bulk-map-demand") and not exists(user, "series-bulk-use")


async def test_a_column_that_looks_like_no_component_is_listed_as_not_recognised(user: User):
    await user.open("/")

    await upload(user, csv({"Temperatur": lambda i: 5.0, "PV": lambda i: 1.0}))

    assert [(row["column"], row["kind"]) for row in columns_of(user)] == [("Temperatur", "not recognised"), ("PV", "PV system")]


async def test_the_values_that_are_empty_are_not_counted_in_the_table_of_the_columns(user: User):
    await user.open("/")

    await upload(user, csv({"Last": lambda i: "" if i < 4 else 1.0}))

    assert columns_of(user)[0]["values"] == "20"


async def test_the_components_that_the_columns_look_like_are_added_with_one_click_and_get_their_columns(user: User):
    await user.open("/")
    await upload(user, csv(ALL))

    assert field(user, "series-bulk-add-components").text == (
        "Add 4 components for the columns: Electricity demand, Heat demand, Electricity grid, PV system")
    user.find(marker="series-bulk-add-components").click()
    await settle()

    assert all(exists(user, f"tile-{key}") for key in KEYS)
    assert {key: choice(user, key) for key in KEYS} == {
        "demand": "Strom_Last", "heat_demand": "Waermebedarf", "pv": "PV", "grid": "Strompreis"}
    assert not exists(user, "series-bulk-add-components")                  # nothing is left to add
    assert field(user, "series-bulk-use").text == "Use 4 time series"
    assert not exists(user, "series-bulk-empty")


async def test_one_component_for_one_column_is_said_in_the_singular(user: User):
    await user.open("/")

    await upload(user, csv({"PV": lambda i: 1.0}))

    assert field(user, "series-bulk-add-components").text == "Add the component for a column: PV system"


async def test_only_the_components_that_are_not_there_yet_are_offered(user: User):
    await open_with(user, "demand", "pv")

    await upload(user, csv(ALL))

    assert field(user, "series-bulk-add-components").text == "Add 2 components for the columns: Heat demand, Electricity grid"


async def test_no_component_is_offered_for_columns_that_look_like_nothing(user: User):
    await user.open("/")

    await upload(user, csv({"Temperatur": lambda i: 5.0}))

    assert not exists(user, "series-bulk-add-components")


async def test_a_component_that_is_added_later_takes_its_column_from_the_same_file(user: User):
    await open_with(user, "demand")
    await upload(user, csv(ALL))
    await use_it(user)
    assert texts(user, "series-bulk-status-demand") == ["Taken from this file."] and not exists(user, "series-bulk-use")

    user.find(marker="series-bulk-add-components").click()                 # the other three components
    await settle()

    assert texts(user, "series-bulk-status-demand") == ["Taken from this file."]
    assert all(texts(user, f"series-bulk-status-{key}") == ["24 values will be used."] for key in ("heat_demand", "pv", "grid"))
    assert field(user, "series-bulk-use").text == "Use 3 time series"
    await use_it(user)

    assert field(user, "series-bulk-done").text == "3 time series were taken from the file alle.csv."
    assert all(exists(user, f"series-summary-{key}") for key in KEYS)
    assert field(user, "series-bulk-all-used").text == "Everything that is assigned has been taken over."


async def test_a_choice_that_changes_the_series_makes_what_was_taken_over_ready_to_be_taken_again(user: User):
    await open_with(user, "grid")
    await upload(user, csv({"Strompreis": lambda i: 30 + i}))
    await use_it(user)
    assert texts(user, "series-summary-grid")[0].startswith("24 values from 30")

    field(user, "series-price-unit-bulk").set_value("€/MWh")
    await settle()

    assert texts(user, "series-bulk-status-grid") == ["24 values will be used."] and field(user, "series-bulk-use").text == "Use 1 time series"
    await use_it(user)
    assert texts(user, "series-summary-grid")[0].startswith("24 values from 0.03 to 0.053")


# ---------------------------------------------------------------------------
# the period of the file
# ---------------------------------------------------------------------------

async def test_the_period_of_the_file_can_be_taken_for_the_scenario(user: User):
    await user.open("/")
    assert field(user, "draft-steps").value == 8760

    await upload(user, csv({"Last": lambda i: 1.0}, hours=72, start="2021-03-05"))
    assert field(user, "series-bulk-period").text == "Use the period of the file (2021-03-05, 72 hours)"
    user.find(marker="series-bulk-period").click()
    await settle()

    assert field(user, "draft-start").value == "2021-03-05" and field(user, "draft-steps").value == 72
    assert not exists(user, "series-bulk-period")
    assert field(user, "series-bulk-period-note").text == "The period of the file is the period of your scenario."


async def test_a_file_that_has_the_period_of_the_scenario_says_so_and_has_no_button(user: User):
    await open_with(user, "demand")                                        # a day from 2021-01-01

    await upload(user, csv({"Last": lambda i: 1.0}))

    assert not exists(user, "series-bulk-period")
    assert field(user, "series-bulk-period-note").text == "The period of the file is the period of your scenario."


async def test_a_file_with_as_many_hours_but_another_day_still_offers_its_period(user: User):
    await open_with(user, "demand")                                        # 24 hours from 2021-01-01

    await upload(user, csv({"Last": lambda i: 1.0}, hours=24, start="2021-03-05"))

    assert field(user, "series-bulk-period").text == "Use the period of the file (2021-03-05, 24 hours)"
    assert not exists(user, "series-bulk-period-note")


async def test_with_the_period_of_the_file_the_check_no_longer_says_that_the_series_is_longer_than_the_scenario(user: User):
    await open_with(user, "demand")                                        # a scenario of 24 hours
    await upload(user, csv({"Last": lambda i: 1.0}, hours=72))
    await use_it(user)
    assert texts(user, "series-bulk-status-demand") == ["Taken from this file."]
    assert any("the time series has 72 values, but the selected time range needs 24" in text for text in texts(user, "problems-demand"))

    user.find(marker="series-bulk-period").click()
    await settle()

    assert field(user, "draft-steps").value == 72
    assert not any("the selected time range needs" in text for text in texts(user, "problems-demand"))


async def test_a_file_that_is_longer_than_a_scenario_can_be_says_so(user: User):
    await user.open("/")

    await upload(user, csv({"Last": lambda i: 1.0}, hours=8790))

    assert field(user, "series-bulk-period-note").text == "The file covers 8,790 hours; a scenario can have at most 8,784."
    assert not exists(user, "series-bulk-period")


async def test_a_file_without_dates_gives_its_length_and_keeps_the_start_of_the_scenario(user: User):
    await user.open("/")
    rows = ["Last;Solar"] + [f"{1 + i / 10};{i / 10}" for i in range(96)]

    await upload(user, ("\n".join(rows) + "\n").encode(), name="ohne_datum.csv")
    assert field(user, "series-bulk-period-info").text == "The file has 96 values per column and no dates."
    assert field(user, "series-bulk-period").text == "Use the length of the file (96 hours)"
    user.find(marker="series-bulk-period").click()
    await settle()

    assert field(user, "draft-steps").value == 96 and field(user, "draft-start").value == "2021-01-01"


# ---------------------------------------------------------------------------
# a column that fits, offered in the settings of a component
# ---------------------------------------------------------------------------

async def test_the_settings_of_a_component_offer_the_column_of_the_file_that_fits(user: User):
    await open_with(user, "demand", "pv")

    await upload(user, csv(ALL))

    assert texts(user, "series-bulk-hint-pv")[0] == "The file alle.csv has a column that fits: PV."
    assert field(user, "series-bulk-hint-use-pv").text == "Use column PV"
    assert field(user, "series-bulk-hint-use-demand").text == "Use column Strom_Last"


async def test_a_component_that_is_added_after_the_file_gets_its_hint_right_away(user: User):
    await user.open("/")
    await upload(user, csv(ALL))
    assert not exists(user, "series-bulk-hint-pv")                         # no component yet

    user.find(marker="component-pv").click()
    await settle()

    assert texts(user, "series-bulk-hint-pv")[0] == "The file alle.csv has a column that fits: PV."
    user.find(marker="add-wind").click()                                   # one that the file has no column for
    await settle()
    assert not exists(user, "series-bulk-hint-wind") and exists(user, "series-bulk-hint-pv")


async def test_a_click_on_the_hint_takes_over_that_one_column_and_the_hint_goes(user: User):
    await open_with(user, "demand", "pv")
    await upload(user, csv(ALL))

    user.find(marker="series-bulk-hint-use-pv").click()
    await settle()

    assert texts(user, "series-summary-pv")[1] == "From the file alle.csv, column PV."
    assert not exists(user, "series-bulk-hint-pv") and exists(user, "series-bulk-hint-demand")
    assert texts(user, "series-bulk-status-pv") == ["Taken from this file."]       # the card knows
    assert texts(user, "series-bulk-status-demand") == ["24 values will be used."]
    assert field(user, "series-bulk-use").text == "Use 1 time series"
    assert field(user, "series-bulk-done").text == "1 time series was taken from the file alle.csv."


async def test_there_is_no_hint_for_a_component_that_the_visitor_set_to_none(user: User):
    await open_with(user, "demand", "pv")
    await upload(user, csv(ALL))

    field(user, "series-bulk-map-pv").set_value(NONE)
    await settle()

    assert not exists(user, "series-bulk-hint-pv") and exists(user, "series-bulk-hint-demand")


async def test_there_is_no_hint_when_the_file_has_no_fitting_column(user: User):
    await open_with(user, "wind")

    await upload(user, csv(ALL))

    assert not exists(user, "series-bulk-hint-wind")


async def test_the_hints_go_when_the_file_is_removed_and_come_back_with_a_new_one(user: User):
    await open_with(user, "demand", "pv")
    await upload(user, csv(ALL))
    assert exists(user, "series-bulk-hint-pv")

    user.find(marker="series-bulk-remove").click()
    await settle()
    assert not exists(user, "series-bulk-hint-pv") and not exists(user, "series-bulk-hint-demand")

    await upload(user, csv(ALL))
    assert exists(user, "series-bulk-hint-pv")


async def test_the_hints_go_when_the_card_takes_the_series_over(user: User):
    await open_with(user, "demand", "pv")
    await upload(user, csv(ALL))

    await use_it(user)

    assert not exists(user, "series-bulk-hint-pv") and not exists(user, "series-bulk-hint-demand")


async def test_a_column_that_cannot_be_used_yet_is_offered_with_the_reason_and_without_a_button(user: User):
    await open_with(user, "demand")
    field(user, "field-demand-demand-profile_type").value = "absolute"
    await settle()

    await upload(user, csv({"Last": lambda i: 2.0}, step_minutes=15))

    assert texts(user, "series-bulk-hint-demand")[0] == "The file alle.csv has a column that fits: Last."
    assert exists(user, "series-bulk-hint-problem-demand") and not exists(user, "series-bulk-hint-use-demand")


async def test_a_hint_for_a_component_that_has_a_series_from_another_file_still_offers_the_column(user: User):
    await open_with(user, "demand")
    await give_demand(user, values=[2.0] * 24)                             # a series from daten.csv

    await upload(user, csv({"Last": lambda i: 5.0}))

    assert field(user, "series-bulk-hint-use-demand").text == "Use column Last"


# ---------------------------------------------------------------------------
# language
# ---------------------------------------------------------------------------

async def test_the_overview_the_period_and_the_hints_are_in_german(user: User):
    await open_with(user, "demand", language="de")

    await upload(user, csv(ALL, hours=24))

    await user.should_see("Was die Datei enthält")
    assert field(user, "series-bulk-period-info").text == "Zeitraum der Datei: 2021-01-01 00:00 bis 2021-01-01 23:00 (24 Stunden)"
    assert [row["kind"] for row in columns_of(user)] == ["Strombedarf", "Wärmebedarf", "PV-Anlage", "Stromnetz"]
    assert field(user, "series-bulk-add-components").text == (
        "3 Bauteile für die Spalten hinzufügen: Wärmebedarf, Stromnetz, PV-Anlage")
    assert texts(user, "series-bulk-hint-demand")[0] == "Die Datei alle.csv hat eine passende Spalte: Strom_Last."
    assert field(user, "series-bulk-hint-use-demand").text == "Spalte Strom_Last übernehmen"
    assert field(user, "series-bulk-remove").text == "Datei entfernen"


async def test_the_period_button_is_in_german(user: User):
    await user.open("/?lang=de")

    await upload(user, csv({"Last": lambda i: 1.0}, hours=72, start="2021-03-05"))

    assert field(user, "series-bulk-period").text == "Zeitraum der Datei übernehmen (2021-03-05, 72 Stunden)"


async def test_the_file_and_what_it_holds_stay_when_the_language_changes(user: User):
    await user.open("/")
    await upload(user, csv(ALL))

    await switched_to(user, "de")

    assert [row["column"] for row in columns_of(user)] == list(ALL) and exists(user, "series-bulk-add-components")
    await user.should_see("Was die Datei enthält")