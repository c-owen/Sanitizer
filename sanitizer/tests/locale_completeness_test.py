"""Locale files are complete and safe — 14 files, valid JSON, no empty values.

Buzz's plugin translator falls back to the English source only because an empty
value is *falsy*; a key mapped to ``""`` therefore **blanks that string in the UI**
(see ``buzz/buzz/plugins/AGENTS.md``: "Never use an empty string as a translation
value"). This guards every bundled locale against that trap — each file must be a
JSON object and must never map a key to an empty/whitespace-only string. Pure stdlib.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_LOCALE_DIR = Path(__file__).resolve().parents[1] / "locale"
_LOCALE_FILES = sorted(_LOCALE_DIR.glob("*.json"))
EXPECTED_LOCALES = 14


def test_expected_locale_files_are_present():
    assert len(_LOCALE_FILES) == EXPECTED_LOCALES


@pytest.mark.parametrize("path", _LOCALE_FILES, ids=lambda p: p.name)
def test_locale_file_is_a_json_object_with_no_empty_values(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name}: must be a JSON object"
    for key, value in data.items():
        assert isinstance(value, str), f"{path.name}: {key!r} maps to a non-string"
        assert value.strip(), f"{path.name}: {key!r} maps to an empty value (blanks UI)"
