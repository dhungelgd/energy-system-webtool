"""The areas of the tool: what a partner can do in it, as one list.

The page has a start page and one area for each entry of AREAS (today the optimization; the analysis of a load
profile and others come as one more entry each). The bar of the areas and the cards of the start page are drawn from
this list, so a new area is one entry here and its own content, and nothing else on the page has to change.
No NiceGUI code in here, so it is easy to test.
"""

import os
from dataclasses import dataclass

START = "start"                              # the start page: not an area with content, but where one chooses
START_ENV = "WEBTOOL_START_AREA"             # where the page opens if the address does not say (a server can set it)


@dataclass(frozen=True)
class Area:
    key: str                                 # also the value of ?area= in the address
    label: str                               # the text of the key in the bar of the areas
    icon: str                                # the icon of the card on the start page
    title: str                               # the texts of that card
    text: str
    button: str
    resume: str                              # the text of the button if there is work in this area already


AREAS = (
    Area("optimization", "area.optimization", "tune", "start.optimization.title", "start.optimization.text",
         "start.optimization.button", "start.optimization.continue"),
)


def keys():
    """Every place that the page can show: the start page and the areas, in the order of the bar."""

    return [START, *[area.key for area in AREAS]]


def is_area(value):
    return value in keys()


def area_of(key):
    """The Area with this key (the start page is not one: a KeyError)."""

    return next(area for area in AREAS if area.key == key)


def start_area(query=None, environ=None):
    """Where the page opens: the area that the address names, else the one that the server is set to open in, else the
    start page. A name that is not an area is ignored (a link that is old or mistyped must not break the page)."""

    environ = os.environ if environ is None else environ

    for value in (query, environ.get(START_ENV)):
        if is_area(value):
            return value

    return START