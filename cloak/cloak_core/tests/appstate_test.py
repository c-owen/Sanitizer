"""Preferences store — cross-transcript app state (US6 teaching, FR-12 gate).

Pure core (no buzz/Qt); runs on system Python. Reads must be total: a missing or
corrupt store yields defaults, never an error.
"""

from __future__ import annotations

from cloak_core.appstate import (
    Preferences,
    read_preferences,
    write_preferences,
)


def test_defaults_when_absent(tmp_path):
    prefs = read_preferences(tmp_path)
    assert prefs == Preferences()
    assert prefs.has_reviewed is False
    assert prefs.auto_apply_suggestions is False
    assert prefs.key_note_dismissed is False


def test_round_trip(tmp_path):
    write_preferences(
        tmp_path,
        Preferences(
            has_reviewed=True, auto_apply_suggestions=True, key_note_dismissed=True
        ),
    )
    prefs = read_preferences(tmp_path)
    assert prefs.has_reviewed is True
    assert prefs.auto_apply_suggestions is True
    assert prefs.key_note_dismissed is True


def test_write_creates_directory(tmp_path):
    target = tmp_path / "nested" / "cloak"
    write_preferences(target, Preferences(has_reviewed=True))
    assert read_preferences(target).has_reviewed is True


def test_corrupt_store_reads_as_defaults(tmp_path):
    (tmp_path / "preferences.json").write_text("not json{", encoding="utf-8")
    assert read_preferences(tmp_path) == Preferences()


def test_non_object_store_reads_as_defaults(tmp_path):
    (tmp_path / "preferences.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert read_preferences(tmp_path) == Preferences()
