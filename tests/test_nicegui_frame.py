"""The frame of the page: the top bar (name, status, run, language) and the three views (simulated user)."""

import asyncio

import pytest

pytest.importorskip("nicegui")
from nicegui import ElementFilter, ui  # noqa: E402
from nicegui.testing import User  # noqa: E402

from tests.test_nicegui_draft_run import (  # noqa: E402
    PRICE,
    build_draft,
    build_pv_draft,
    exists,
    fake_result,
    field,
    give_demand,
    open_example,
    run_button,
    settle,
    switched_to,
    use_clock,
    use_solver,
)


def views(user):
    """The tabs that choose the view (System, Check, Results)."""

    with user.client:
        return next(iter(ElementFilter(marker="views")))


def status_of(user):
    return field(user, "status").text


def element(user, marker):
    """An element whether it can be seen or not (find() leaves out what is hidden)."""

    with user.client:
        return next(iter(ElementFilter(marker=marker)))


# ---------------------------------------------------------------------------
# the top bar
# ---------------------------------------------------------------------------

async def test_the_top_bar_has_the_title_the_name_the_status_the_run_button_and_the_language(user: User):
    await user.open("/")

    with user.client:
        assert len(list(ElementFilter(kind=ui.header))) == 1
    for marker in ("app-title", "draft-name", "status", "draft-run", "language"):
        assert any(isinstance(parent, ui.header) for parent in field(user, marker).ancestors()), marker
    assert field(user, "app-title").text == "Energy System Web Tool"


async def test_the_top_bar_is_in_german(user: User):
    await build_draft(user, language="de")

    assert field(user, "app-title").text == "Energiesystem-Webtool"
    assert field(user, "draft-run").text == "Optimierung starten"
    assert status_of(user) == "Bereit"


async def test_the_name_is_typed_in_the_top_bar_and_the_field_is_not_drawn_again_while_typing(user: User):
    await build_draft(user)
    typed_into = field(user, "draft-name")

    user.find(marker="draft-name").clear().type("My own system")
    await settle()

    assert field(user, "draft-name") is typed_into                          # the same field: the cursor stays in it
    assert field(user, "draft-title").text == "My own system"               # and the check view knows the name


# ---------------------------------------------------------------------------
# the status
# ---------------------------------------------------------------------------

async def test_the_status_says_what_the_visitor_can_do_next(user: User):
    await user.open("/")
    assert status_of(user) == "Choose components" and not run_button(user).enabled

    user.find(marker="template-electricity-only").click()
    await user.should_see(marker="selection-count")
    user.find(marker="draft-steps").clear().type("24")
    await settle()
    assert status_of(user) == "1 error" and not run_button(user).enabled           # the demand has no data yet

    await give_demand(user)
    assert status_of(user) == "Ready" and run_button(user).enabled


async def test_only_a_warning_is_shown_as_a_count_of_warnings_and_the_run_is_free(user: User):
    await build_pv_draft(user)
    user.find(marker="field-pv-capacity-maximum").clear().type("50")
    await settle()

    assert status_of(user) == "1 warning" and run_button(user).enabled


async def test_the_status_counts_errors_and_warnings_together(user: User):
    await build_pv_draft(user)                                            # a plant that would be built without end

    assert status_of(user) == "1 error, 1 warning" and not run_button(user).enabled


async def test_a_result_that_is_out_of_date_says_so_and_the_run_is_free(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("72 €")
    assert status_of(user) == "Ready"

    user.find(marker=PRICE).clear().type("0.35")
    await settle()

    assert status_of(user) == "Result outdated" and run_button(user).enabled


async def test_the_status_is_in_german(user: User):
    await build_pv_draft(user, language="de")

    assert status_of(user) == "1 Fehler, 1 Warnung"


async def test_the_status_follows_a_change_of_language(user: User):
    await build_draft(user)
    assert status_of(user) == "Ready" and field(user, "draft-run").text == "Run optimization"

    await switched_to(user, "de")

    assert status_of(user) == "Bereit" and field(user, "draft-run").text == "Optimierung starten"


# ---------------------------------------------------------------------------
# the badge on the check
# ---------------------------------------------------------------------------

async def test_the_check_tab_has_a_badge_with_the_number_of_findings_and_none_when_all_is_well(user: User):
    await build_pv_draft(user)
    badge = element(user, "check-badge")
    assert badge.visible and badge.text == "2"                              # one error, one warning
    assert badge.props["color"] == "negative"

    user.find(marker="field-pv-capacity-maximum").clear().type("50")
    await settle()
    assert badge.text == "1" and badge.props["color"] == "warning"


async def test_the_badge_is_hidden_when_the_check_finds_nothing(user: User):
    await build_draft(user)

    assert not element(user, "check-badge").visible


# ---------------------------------------------------------------------------
# the views
# ---------------------------------------------------------------------------

async def test_there_are_three_views_and_the_page_starts_in_the_first(user: User):
    await user.open("/")

    assert [field(user, f"view-{name}").props["label"] for name in ("system", "check", "results")] == [
        "System", "Check", "Results"]
    assert views(user).value == "system"


async def test_the_chosen_view_stays_when_the_language_changes_and_the_labels_follow(user: User):
    await build_draft(user)
    views(user).set_value("check")

    await switched_to(user, "de")

    assert views(user).value == "check"
    assert [field(user, f"view-{name}").props["label"] for name in ("system", "check", "results")] == [
        "System", "Prüfung", "Ergebnisse"]


async def test_the_status_opens_the_check(user: User):
    await build_draft(user)
    assert views(user).value == "system"

    user.find(marker="status").click()

    assert views(user).value == "check"


async def test_starting_a_run_shows_the_results_view_and_says_that_the_result_comes(user: User, monkeypatch):
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    assert views(user).value == "system"

    user.find(marker="draft-run").click()
    await user.should_see(marker="draft-running")

    assert views(user).value == "results"
    await user.should_see("The optimization is running. The result appears here.")

    release.set()
    await user.should_see("72 €")
    assert not exists(user, "draft-running")


async def test_the_results_view_without_a_result_says_what_to_do(user: User):
    await user.open("/")

    await user.should_see("No result yet")
    await user.should_see("Start the optimization with the button in the top bar.")
    await user.should_see("A day takes seconds")                              # the hint about the time of a run


async def test_a_result_that_was_seen_stays_when_the_view_is_changed_and_back(user: User, monkeypatch):
    async def solver(scenario):
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    user.find(marker="draft-run").click()
    await user.should_see("72 €")
    drawn = field(user, "draft-results")

    views(user).set_value("system")
    views(user).set_value("results")
    await settle()

    assert field(user, "draft-results") is drawn                             # not drawn again by a change of view


# ---------------------------------------------------------------------------
# the run of an opened file
# ---------------------------------------------------------------------------

async def test_while_an_opened_file_runs_the_top_bar_says_so_and_the_run_of_the_draft_is_blocked(user: User, monkeypatch):
    now = use_clock(monkeypatch)
    release = asyncio.Event()

    async def solver(scenario):
        await release.wait()
        return fake_result()

    use_solver(monkeypatch, solver)
    await build_draft(user)
    await open_example(user, "pv_and_grid")

    user.find(marker="run").click()
    await user.should_see(marker="status", content="Running")
    assert not run_button(user).enabled and not field(user, "language").enabled
    now[0] += 3

    release.set()
    await user.should_see("72 €")

    assert "Running" not in status_of(user) and run_button(user).enabled and field(user, "language").enabled