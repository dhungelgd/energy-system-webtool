"""The NiceGUI interface: pages are tested with NiceGUI's simulated user (no browser)."""

import pytest

pytest.importorskip("nicegui")
from nicegui.testing import User  # noqa: E402


async def test_the_home_page_shows_the_title(user: User):
    await user.open("/")

    await user.should_see("Energy System Web Tool")
    await user.should_see("NiceGUI")