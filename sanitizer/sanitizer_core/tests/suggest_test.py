"""Model-suggestion tier — SUGGESTED, PENDING, review-gated, never auto-applied.

Covers FR-9/FR-15 and the guarantee that suggestions stay out of the guaranteed
set (PG6): they are held for review, excluded from the fail-closed gate, and the
guaranteed path still works when the model is absent. The model is faked with a
stub :class:`ModelProvider` so the core stays host-free (no ML, no network).
"""

from __future__ import annotations

import pytest

from sanitizer_core.detectors.declared import DeclaredListDetector
from sanitizer_core.detectors.suggest import ModelSuggestionDetector, RawEntity
from sanitizer_core.model import DecisionState, TrustTier
from sanitizer_core.sanitizer import sanitize


class _StubProvider:
    """Locates each ``(surface, label[, score])`` spec in the text and returns it
    as a :class:`RawEntity`, finding every non-overlapping occurrence."""

    def __init__(self, *specs: tuple) -> None:
        self._specs = [
            (spec[0], spec[1], spec[2] if len(spec) > 2 else 1.0) for spec in specs
        ]

    def predict(self, text, labels):
        out: list[RawEntity] = []
        for surface, label, score in self._specs:
            start = text.find(surface)
            while start >= 0:
                out.append(RawEntity(start, start + len(surface), label, score))
                start = text.find(surface, start + len(surface))
        return out


def _suggest(*specs, threshold=0.5):
    return ModelSuggestionDetector(_StubProvider(*specs), threshold=threshold)


# --- detector: tier, mapping, substring safety ------------------------------
def test_suggestion_is_suggested_tier():
    [det] = _suggest(("Acme", "organization")).detect("I work at Acme today")
    assert det.tier is TrustTier.SUGGESTED
    assert det.type == "org"
    assert det.label == "ORG"
    assert det.value == "Acme"
    assert "model suggestion" in det.reason


@pytest.mark.parametrize(
    "label,category,placeholder_label",
    [
        ("person", "person", "PERSON"),
        ("organization", "org", "ORG"),
        ("location", "place", "PLACE"),
        ("project", "project", "PROJECT"),
        ("PER", "person", "PERSON"),  # transformers-NER tag spelling
        ("LOC", "place", "PLACE"),
    ],
)
def test_label_maps_to_category(label, category, placeholder_label):
    [det] = _suggest(("Xenon", label)).detect("see Xenon here")
    assert det.type == category
    assert det.label == placeholder_label


def test_unknown_label_is_skipped():
    assert _suggest(("Xenon", "weather")).detect("Xenon is cold") == []


def test_value_matches_span_slice():
    text = "ping Dana at noon"
    for det in _suggest(("Dana", "person")).detect(text):
        assert det.value == text[det.span.start : det.span.end]


def test_repeated_suggestion_yields_one_per_occurrence():
    dets = _suggest(("Dana", "person")).detect("Dana then Dana")
    assert [d.value for d in dets] == ["Dana", "Dana"]
    assert {d.canonical for d in dets} == {"dana"}


def test_detection_carries_the_model_score():
    # The provider's confidence rides through onto the Detection (→ triage filter).
    [det] = _suggest(("Dana", "person", 0.82)).detect("Dana hi")
    assert det.score == 0.82


# --- detector: thresholds + defensive span handling -------------------------
def test_below_threshold_filtered():
    assert _suggest(("Dana", "person", 0.20), threshold=0.5).detect("Dana waved") == []


def test_at_or_above_threshold_kept():
    assert len(_suggest(("Dana", "person", 0.50), threshold=0.5).detect("Dana hi")) == 1


def test_out_of_bounds_span_is_skipped():
    class _Bad:
        def predict(self, text, labels):
            return [RawEntity(0, len(text) + 5, "person", 1.0)]

    assert ModelSuggestionDetector(_Bad()).detect("hi") == []


def test_edge_whitespace_is_trimmed_offsets_stay_exact():
    text = "x Dana y"

    class _Pad:
        def predict(self, t, labels):
            return [RawEntity(1, 7, "person", 1.0)]  # " Dana "

    [det] = ModelSuggestionDetector(_Pad()).detect(text)
    assert det.value == "Dana"
    assert (det.span.start, det.span.end) == (2, 6)
    assert det.value == text[det.span.start : det.span.end]


def test_provider_failure_degrades_to_no_suggestions():
    class _Boom:
        def predict(self, text, labels):
            raise RuntimeError("model not available")

    assert ModelSuggestionDetector(_Boom()).detect("anything") == []


# --- through the sanitizer: held, not removed, not gated --------------------
def test_suggestion_is_pending_and_not_removed():
    result = sanitize("Met Dana today", [_suggest(("Dana", "person"))])
    [decision] = result.decisions
    assert decision.state is DecisionState.PENDING
    assert decision.tier is TrustTier.SUGGESTED
    assert "Dana" in result.scrubbed  # never auto-applied (FR-9)


def test_pending_suggestion_has_no_placeholder_or_key_entry():
    # The key is exactly the applied substitutions; a held suggestion is neither.
    result = sanitize("Met Dana today", [_suggest(("Dana", "person"))])
    assert result.decisions[0].placeholder == ""
    assert result.key.entries == {}


def test_suggestion_does_not_fail_the_gate():
    # A suggested value left in cleartext must NOT make the result "not clean".
    result = sanitize("Dana and Dana", [_suggest(("Dana", "person"))])
    assert result.clean is True
    assert result.survivors == []


# --- cross-tier: guaranteed dominates a same-value suggestion ----------------
def test_declared_dominates_same_value_suggestion():
    detectors = [
        DeclaredListDetector({"project": ["Apollo"]}),
        _suggest(("Apollo", "project")),
    ]
    result = sanitize("Apollo launches Apollo", detectors)
    [decision] = result.decisions
    assert decision.tier is TrustTier.DECLARED
    assert decision.state is DecisionState.APPROVED
    assert "Apollo" not in result.scrubbed
    assert result.scrubbed == "{{PROJECT-A}} launches {{PROJECT-A}}"


def test_declared_and_suggested_distinct_values_coexist():
    detectors = [
        DeclaredListDetector({"person": ["Jane"]}),
        _suggest(("Acme", "organization")),
    ]
    result = sanitize("Jane joined Acme", detectors)
    by_type = {d.type: d for d in result.decisions}
    assert by_type["person"].state is DecisionState.APPROVED
    assert by_type["org"].state is DecisionState.PENDING
    assert "Jane" not in result.scrubbed
    assert "Acme" in result.scrubbed  # suggestion kept until reviewed


# --- graceful degradation: guaranteed path unaffected by the model ----------
def test_guaranteed_path_works_when_model_is_absent():
    class _Boom:
        def predict(self, text, labels):
            raise RuntimeError("no model")

    detectors = [DeclaredListDetector(["Jane"]), ModelSuggestionDetector(_Boom())]
    result = sanitize("Call Jane now", detectors)
    assert result.scrubbed == "Call {{TERM-1}} now"
    assert result.clean is True
