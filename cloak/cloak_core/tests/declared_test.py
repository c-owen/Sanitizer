"""DeclaredListDetector — substring safety, variants, multi-word (FR-1)."""

from __future__ import annotations

import pytest

from cloak_core.detectors.declared import DeclaredListDetector


def test_matches_exact_word():
    dets = DeclaredListDetector(["Jane"]).detect("Jane went home.")
    assert len(dets) == 1
    assert dets[0].value == "Jane"
    assert (dets[0].span.start, dets[0].span.end) == (0, 4)
    assert dets[0].canonical == "jane"
    assert dets[0].restore == "Jane"


@pytest.mark.parametrize("text", ["Janet", "Janitor", "Marjane", "Janes", "JaneDoe"])
def test_does_not_match_substring(text):
    # The catastrophic case: "Jane" must never touch a larger word.
    assert DeclaredListDetector(["Jane"]).detect(text) == []


@pytest.mark.parametrize("surface", ["jane", "JANE", "JaNe"])
def test_case_insensitive(surface):
    dets = DeclaredListDetector(["Jane"]).detect(f"hello {surface} bye")
    assert len(dets) == 1
    assert dets[0].value == surface
    assert dets[0].canonical == "jane"
    assert dets[0].restore == "Jane"


def test_possessive_matches_name_only():
    dets = DeclaredListDetector(["Jane"]).detect("Jane's car")
    assert len(dets) == 1
    assert dets[0].value == "Jane"  # the "'s" is left untouched


@pytest.mark.parametrize(
    "text", ["Project Apollo", "project  apollo", "Project\nApollo"]
)
def test_multiword_flexible_whitespace(text):
    dets = DeclaredListDetector(["Project Apollo"]).detect(text)
    assert len(dets) == 1
    assert dets[0].canonical == "project apollo"


def test_finds_all_occurrences():
    dets = DeclaredListDetector(["Jane"]).detect("Jane and Jane and JANE")
    assert len(dets) == 3


def test_longest_term_wins_on_overlap():
    dets = DeclaredListDetector(["Jane", "Jane Doe"]).detect("Jane Doe spoke")
    assert len(dets) == 1
    assert dets[0].value == "Jane Doe"
    assert dets[0].canonical == "jane doe"


def test_blank_and_duplicate_terms_ignored():
    det = DeclaredListDetector(["Jane", " jane ", "", "   "])
    assert len(det.detect("Jane")) == 1


def test_value_matches_span_slice():
    text = "ring Jane please"
    for det in DeclaredListDetector(["Jane"]).detect(text):
        assert det.value == text[det.span.start : det.span.end]


def test_no_terms_no_detections():
    assert DeclaredListDetector([]).detect("anything at all") == []
