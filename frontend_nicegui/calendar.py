"""The texts of the calendar in the date picker.

The date picker (Quasar) shows English month and day names unless it is given others.
English needs nothing; for German the names are given here.
"""

import json

LOCALES = {
    "de": {
        "days": ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"],
        "daysShort": ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"],
        "months": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
                   "Oktober", "November", "Dezember"],
        "monthsShort": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
        "firstDayOfWeek": 1,            # a week starts on Monday
    },
}


def locale_prop(language):
    """The property for the date picker ':locale=...', or None if the language needs none."""

    names = LOCALES.get(language)

    if names is None:
        return None

    return f":locale='{json.dumps(names, ensure_ascii=False)}'"