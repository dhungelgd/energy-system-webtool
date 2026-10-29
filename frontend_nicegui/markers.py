"""Names for the markers that the tests use to find elements of a page."""

import re


def slug(text):
    """A name that can be used as a marker: 'PV + battery' -> 'pv-battery'."""

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")