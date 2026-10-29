"""The scenario page of the NiceGUI interface, with simulated uploads (no browser)."""

import json
from pathlib import Path

import pytest

pytest.importorskip("nicegui")
from nicegui.elements.upload_files import SmallFileUpload  # noqa: E402
from nicegui.testing import User  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "scenarios_v2"


async def open_file(user: User, name: str, content: bytes):
    await user.open("/")
    upload = user.find(marker="upload").elements.pop()
    await upload.handle_uploads([SmallFileUpload(name, "application/json", content)])


async def open_example(user: User, name: str):
    await open_file(user, f"{name}.json", (EXAMPLES / f"{name}.json").read_bytes())


async def table_rows(user: User, marker: str):
    # find() does not wait, should_see() does: the page updates after the upload
    await user.should_see(marker=marker)
    return user.find(marker=marker).elements.pop().rows


async def test_the_page_asks_for_a_scenario_file(user: User):
    await user.open("/")

    await user.should_see("Open a scenario file")
    await user.should_see("examples/scenarios_v2")
    await user.should_see(marker="upload")
    await user.should_not_see(marker="scenario-name")


async def test_a_good_scenario_is_described(user: User):
    await open_example(user, "two_pv_systems")

    await user.should_see("Two PV systems, one day")
    await user.should_see("File: two_pv_systems.json")
    await user.should_see("24 hourly steps (1 day) from 01.01.2021 00:00")
    await user.should_see("Solver: cbc")


async def test_the_components_are_listed_with_their_own_names_and_what_they_are(user: User):
    await open_example(user, "two_pv_systems")

    rows = await table_rows(user, "components")

    assert [row["component"] for row in rows] == [
        "Electricity demand", "Electricity grid", "PV south roof", "PV east roof",
    ]
    assert rows[2] == {"component": "PV south roof", "type": "PV system", "mode": "fixed", "size": "60 kW"}
    assert rows[3] == {"component": "PV east roof", "type": "PV system", "mode": "invest", "size": "up to 40 kW"}


async def test_the_time_series_are_summarised_and_say_who_uses_them(user: User):
    await open_example(user, "two_pv_systems")

    rows = {row["series"]: row for row in await table_rows(user, "series")}

    assert rows["electricity_demand"]["values"] == 24
    assert rows["pv_south_profile"]["used_by"] == "PV south roof"
    assert rows["pv_east_profile"]["unit"] == "capacity factor"
    assert rows["pv_east_profile"]["empty"] == 0


async def test_a_scenario_without_problems_is_ready(user: User):
    await open_example(user, "pv_and_grid")

    await user.should_see("System check passed. Ready to optimize.")
    await user.should_not_see("Fix the errors above")


async def test_errors_and_warnings_are_shown_and_say_what_to_do(user: User):
    await open_example(user, "with_problems")

    await user.should_see("the time series has 10 values")
    await user.should_see("the generation profile has values up to 3.00")
    await user.should_see("Surplus electricity from PV system cannot be exported")
    await user.should_see("Fix the errors above before the optimization can start.")
    await user.should_not_see("System check passed")


async def test_only_warnings_do_not_block(user: User):
    scenario = json.loads((EXAMPLES / "with_problems.json").read_text(encoding="utf-8"))
    scenario["series"]["electricity_demand"]["values"] = [0.01] * 24

    await open_file(user, "warnings_only.json", json.dumps(scenario).encode())

    await user.should_see("Surplus electricity from PV system")
    await user.should_see("There are warnings but no errors. The optimization can be started.")
    await user.should_not_see("Fix the errors above")


async def test_what_the_engine_cannot_run_is_shown_as_an_error_with_the_reason(user: User):
    await open_example(user, "two_pv_systems")

    await user.should_see("The engine can only run one PV system (found pv_south, pv_east)")
    await user.should_see("Fix the errors above before the optimization can start.")


async def test_a_file_that_is_not_json_is_explained(user: User):
    await open_file(user, "notes.json", b"this is not json")

    await user.should_see("This file is not valid JSON.")
    await user.should_not_see(marker="scenario-name")


async def test_a_file_that_is_not_a_scenario_is_explained(user: User):
    await open_file(user, "other.json", json.dumps({"components": ["ufo"]}).encode())

    await user.should_see("This file is not a scenario saved by this tool")


async def test_a_saved_result_is_not_taken_for_a_scenario(user: User):
    result_like = json.dumps({"objective": 72.0, "buses": {}, "horizon_hours": 24})

    await open_file(user, "result.json", result_like.encode())

    await user.should_see("This looks like a saved result, not a scenario.")


async def test_a_scenario_in_the_old_format_is_explained(user: User):
    from backend.scenario import Scenario

    old = Scenario(components=["demand"]).model_dump_json()

    await open_file(user, "old.json", old.encode())

    await user.should_see("This scenario file is in an old format that this version cannot open.")
    await user.should_not_see(marker="scenario-name")


async def test_a_second_file_replaces_the_first(user: User):
    await open_example(user, "pv_and_grid")
    await user.should_see("PV and grid, one day")

    upload = user.find(marker="upload").elements.pop()
    second = (EXAMPLES / "two_pv_systems.json").read_bytes()
    await upload.handle_uploads([SmallFileUpload("second.json", "application/json", second)])

    await user.should_see("Two PV systems, one day")
    await user.should_not_see("PV and grid, one day")


async def test_a_bad_file_after_a_good_one_clears_the_old_details(user: User):
    await open_example(user, "pv_and_grid")
    upload = user.find(marker="upload").elements.pop()

    await upload.handle_uploads([SmallFileUpload("bad.json", "application/json", b"nope")])

    await user.should_see("This file is not valid JSON.")
    await user.should_not_see("PV and grid, one day")


def test_the_upload_element_only_accepts_json_files():
    # the browser file dialog is limited to .json files; the source is read as
    # text, because importing the page module here would break the simulation
    # of the other tests (see the note in test_nicegui_run.py)
    source = (Path(__file__).resolve().parent.parent / "frontend_nicegui" / "app.py").read_text(encoding="utf-8")

    assert "accept=.json" in source