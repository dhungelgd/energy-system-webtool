"""Pytest setup for all tests."""

import pytest

# NiceGUI brings its own test fixtures ("user"). They are only loaded when
# NiceGUI is installed, so the other tests also run without it.
try:
    import nicegui.testing.user_plugin  # noqa: F401
except ImportError:
    pass
else:
    pytest_plugins = ["nicegui.testing.user_plugin"]

# pytest puts the name of the running test in an environment variable (PYTEST_CURRENT_TEST), and the name of a
# parametrized test contains its values. Windows allows 32,767 characters for the whole variable, so a test with a
# big value in its parameters stops there, but not on Linux. This stops it on every system.
MAX_TEST_NAME_LENGTH = 1000


def pytest_collection_modifyitems(items):
    too_long = [item.nodeid[:90] + "..." for item in items if len(item.nodeid) > MAX_TEST_NAME_LENGTH]

    if too_long:
        raise pytest.UsageError(
            f"The name of a test is longer than {MAX_TEST_NAME_LENGTH} characters (a big value as a parameter?). "
            f"Give it a short id with pytest.param(..., id='...'): " + "; ".join(too_long)
        )


@pytest.fixture(autouse=True)
def the_page_tests_open_in_the_optimization(monkeypatch):
    """The page opens on its start page. The page tests that were written before the start page existed begin in the
    optimization, so they say so with the setting that a server has for it. A test of the start page names it in the
    address (?area=start), which wins over this setting."""

    monkeypatch.setenv("WEBTOOL_START_AREA", "optimization")