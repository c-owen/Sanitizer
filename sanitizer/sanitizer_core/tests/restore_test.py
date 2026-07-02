"""Restore — reversibility and skip-unmatched (FR-7, PG4)."""

from __future__ import annotations

from sanitizer_core.detectors.declared import DeclaredListDetector
from sanitizer_core.model import Key
from sanitizer_core.restore import restore
from sanitizer_core.sanitizer import sanitize


def _sanitize(text, terms):
    return sanitize(text, [DeclaredListDetector(terms)])


def test_round_trip_for_declared_spelling():
    text = "Jane called Bob about Jane"
    result = _sanitize(text, ["Jane", "Bob"])
    assert restore(result.scrubbed, result.key) == text


def test_multiword_round_trip():
    text = "Project Apollo and Jane"
    result = _sanitize(text, ["Jane", "Project Apollo"])
    assert restore(result.scrubbed, result.key) == text


def test_case_variants_restore_to_declared_form():
    # Variants collapse to one placeholder, so restore yields the declared
    # spelling everywhere — consistent by design (FR-3), documented behavior.
    result = _sanitize("JANE and jane", ["Jane"])
    assert restore(result.scrubbed, result.key) == "Jane and Jane"


def test_unmatched_placeholders_are_skipped():
    key = Key({"{{TERM-1}}": "Jane"})
    text = "Hello {{TERM-1}} and {{TERM-9}}"
    assert restore(text, key) == "Hello Jane and {{TERM-9}}"


def test_empty_key_is_a_no_op():
    assert restore("nothing to do", Key()) == "nothing to do"


def test_restore_only_touches_known_placeholders():
    result = _sanitize("Jane", ["Jane"])
    # Text the LLM returned with extra prose around the placeholder.
    returned = f"Summary: {result.scrubbed} did the thing."
    assert restore(returned, result.key) == "Summary: Jane did the thing."
