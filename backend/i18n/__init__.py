"""Texts for the user in English and German (see translator.py)."""

from backend.i18n.translator import (
    DEFAULT_LANGUAGE,
    ENGLISH,
    LANGUAGES,
    Msg,
    Translator,
    catalog,
    choose_language,
    detect_language,
)

__all__ = [
    "DEFAULT_LANGUAGE", "ENGLISH", "LANGUAGES", "Msg", "Translator", "catalog",
    "choose_language", "detect_language",
]