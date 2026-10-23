"""Pytest setup for all tests."""

# NiceGUI brings its own test fixtures ("user"). They are only loaded when
# NiceGUI is installed, so the other tests also run without it.
try:
    import nicegui.testing.user_plugin  # noqa: F401
except ImportError:
    pass
else:
    pytest_plugins = ["nicegui.testing.user_plugin"]