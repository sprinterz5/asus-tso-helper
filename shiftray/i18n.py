"""Translations, like G-Helper's Strings.<lang>.resx: tr("English text") -> the user's language.

Each language is one JSON file in translations/, {"English text": "translation"}; a missing or
empty entry stays English, so a partial translation still works. Placeholders keep their names:
tr("Charge: {percent}%", percent=80). The language is picked once at start (the app's setting,
else the system's), so tables built at import time are translated too; changing it needs a
restart, as in G-Helper.
"""
import json
import os

LANGUAGES = {"en": "English", "de": "Deutsch", "es": "Español", "pl": "Polski", "pt": "Português (Brasil)",
             "ru": "Русский", "zh": "简体中文"}
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translations")
CONFIG = os.path.join(os.path.expanduser("~/.config"), "shiftray", "config.json")


def _setting():
    try:
        with open(CONFIG) as f:
            return json.load(f).get("language", "auto")
    except (OSError, ValueError):
        return "auto"


def _system():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value and value not in ("C", "POSIX") and not value.startswith("C."):
            return value.split(":")[0][:2].lower()
    return "en"


def _load(lang):
    if lang == "en":
        return {}
    try:
        with open(os.path.join(DIR, f"{lang}.json"), encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if v}
    except (OSError, ValueError):
        return {}


setting = _setting()
language = setting if setting in LANGUAGES else _system()
if language not in LANGUAGES:
    language = "en"
_table = _load(language)


def tr(text, **values):
    out = _table.get(text, text)
    return out.format(**values) if values else out
