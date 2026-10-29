"""Names for the markers of the pages."""

import pytest

from backend.system_templates import SYSTEM_TEMPLATES
from frontend_nicegui.markers import slug


@pytest.mark.parametrize("text, expected", [
    ("Electricity only", "electricity-only"),
    ("PV + battery", "pv-battery"),
    ("Heat pump + heating rod", "heat-pump-heating-rod"),
    ("  Full system  ", "full-system"),
])
def test_names_become_markers(text, expected):
    assert slug(text) == expected


def test_every_template_gets_its_own_marker():
    markers = [slug(name) for name in SYSTEM_TEMPLATES]

    assert len(set(markers)) == len(markers)