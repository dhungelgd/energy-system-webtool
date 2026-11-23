"""What the name of a column says about it: which component a column of a file looks like (a demand, a PV system, a price).

One list of words for the whole tool: the file with all the series of the optimization takes its columns for the
components with it, and the reading of a load profile uses it to tell the load from the other columns of a file (a price,
a PV profile, a COP are not the electricity use of a site). No NiceGUI code in here, so any frontend can call it.
"""

import re
import unicodedata

# what a column of a component is called (words of the name, without accents, upper case or signs), and what it
# is not: ('waerme', 'heat' ... say heat; 'preis' says a price). The first column that fits is taken.
RULES = {
    "heat_pump": (("cop", "arbeitszahl", "leistungszahl", "jaz"), ()),
    "heat_demand": (("warme", "waerme", "heat", "heiz", "thermal", "fernwarme"), ("cop", "preis", "price", "pump")),
    "pv": (("pv", "photovolt", "solar", "sonne"), ("preis", "price")),
    "wind": (("wind",), ("preis", "price")),
    "grid": (("preis", "price", "tarif", "spot", "borse", "boerse", "dayahead", "epex"),
             ("gas", "warme", "waerme", "heat", "einspeis", "feedin")),
    "demand": (("strom", "elektr", "electric", "last", "load", "demand", "bedarf", "verbrauch", "consumption"),
               ("warme", "waerme", "heat", "heiz", "thermal", "preis", "price", "cop", "pv", "wind", "solar",
                "erzeug", "einspeis", "feedin")),
}
# the specific ones first, so that a column that fits the PV system is not taken for the electricity demand
PRIORITY = ("heat_pump", "heat_demand", "pv", "wind", "grid", "demand")


def compact(name):
    """A column name as plain lower case letters and digits: 'Wärme-Bedarf [kWh]' becomes 'warmebedarfkwh'."""

    plain = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")

    return re.sub(r"[^a-z0-9]", "", plain.lower())


def fits(key, column):
    """True if the name of the column looks like a column for the component `key` (its template)."""

    include, exclude = RULES.get(key, ((), ()))
    name = compact(column)

    return any(word in name for word in include) and not any(word in name for word in exclude)


def kind_of(column):
    """The component that the name of the column looks like (its template), or None if it looks like none."""

    return next((key for key in PRIORITY if fits(key, column)), None)