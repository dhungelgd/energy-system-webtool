"""Texts for the user in English and German.

The texts live in catalogs (`en.json`, `de.json`, next to this file), never in the
code. A text is looked up by a key such as "run.button". The English catalog is the
fallback: a key that is missing in German shows the English text, and a key that is
missing everywhere shows the key itself, so that a gap is visible and nothing breaks.

    tr = Translator("de")
    tr("run.failed", reason="...")            # a text with a placeholder
    tr.plural("builder.count", 3)             # builder.count.one / builder.count.other, with {count}
    tr.message(Msg("file_error.json"))        # a text that was decided somewhere else

A message that is created far from the page (an error while reading a file, for
example) is a `Msg`: a key plus parameters. The page turns it into a sentence in
the language of the visitor.

This module does not use Streamlit or NiceGUI, so any frontend can use it.
"""

import json
from functools import lru_cache
from pathlib import Path

LANGUAGES = {"en": "English", "de": "Deutsch"}
DEFAULT_LANGUAGE = "en"

FOLDER = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def catalog(language):
    """{key: text} of a language. Do not change the result: it is shared."""

    with open(FOLDER / f"{language}.json", encoding="utf-8") as file:
        return json.load(file)


class Msg:
    """A message for the user that is not worded yet: a key and its parameters."""

    def __init__(self, key, **params):
        self.key = key
        self.params = params

    def __eq__(self, other):
        return isinstance(other, Msg) and (self.key, self.params) == (other.key, other.params)

    def __repr__(self):
        return f"Msg({self.key!r}, **{self.params!r})"


class Translator:
    """Looks texts up in the catalog of one language."""

    def __init__(self, language=DEFAULT_LANGUAGE):
        self.language = language if language in LANGUAGES else DEFAULT_LANGUAGE

    def __call__(self, key, **params):
        text = catalog(self.language).get(key)
        if text is None:
            text = catalog(DEFAULT_LANGUAGE).get(key, key)

        return text.format(**params)

    def has(self, key):
        return key in catalog(self.language) or key in catalog(DEFAULT_LANGUAGE)

    def plural(self, key, count, **params):
        """The text for one ("key.one") or for any other number ("key.other").

        The number is available in the text as {count}.
        """

        params.setdefault("count", count)
        return self(f"{key}.{'one' if count == 1 else 'other'}", **params)

    def message(self, msg):
        return self(msg.key, **msg.params)

    # ----- numbers ---------------------------------------------------------

    def localize(self, text):
        """Swap the separators of a number that was written the English way ('1,234.5' to '1.234,5')."""

        if self.language == "de":
            return text.translate({ord(","): ".", ord("."): ","})
        return text

    def number(self, value, significant=6):
        """A number with a decimal point or comma, without trailing zeros (12.5 or 12,5)."""

        return self.localize(f"{value:.{significant}g}")

    def integer(self, value):
        """A whole number with a thousands separator (8,784 or 8.784)."""

        return self.localize(f"{value:,}")


ENGLISH = Translator("en")


def detect_language(accept_language):
    """The best of the supported languages for the Accept-Language header of a browser.

    "de-DE,de;q=0.9,en;q=0.8" gives "de". Anything else gives the default language.
    """

    if not accept_language:
        return DEFAULT_LANGUAGE

    candidates = []
    for position, part in enumerate(accept_language.split(",")):
        tag, *options = part.strip().split(";")
        language = tag.strip().lower().split("-")[0]

        quality = 1.0
        for option in options:
            option = option.strip()
            if option.startswith("q="):
                try:
                    quality = float(option[2:])
                except ValueError:
                    quality = 0.0

        if language in LANGUAGES and quality > 0:
            candidates.append((-quality, position, language))

    return min(candidates)[2] if candidates else DEFAULT_LANGUAGE


def choose_language(requested, accept_language):
    """The language asked for in the link (?lang=de), else the one of the browser, else English."""

    if requested in LANGUAGES:
        return requested

    return detect_language(accept_language)