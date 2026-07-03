"""VerificationGate: the independent, fail-closed re-check (FR-6, PG7)."""

from __future__ import annotations

from sanitizer_core.detectors.pii import EmailDetector
from sanitizer_core.model import Detection, Span, TrustTier
from sanitizer_core.verify import VerificationGate


def test_dirty_text_is_not_clean():
    verification = VerificationGate([EmailDetector()]).verify("reach me at a@b.com")
    assert verification.clean is False
    assert [s.value for s in verification.survivors] == ["a@b.com"]


def test_clean_text_is_clean():
    verification = VerificationGate([EmailDetector()]).verify("nothing here")
    assert verification.clean is True
    assert verification.survivors == []


def test_placeholders_are_ignored():
    text = "reach me at {{EMAIL-1}}"
    verification = VerificationGate([EmailDetector()]).verify(
        text, ignore=["{{EMAIL-1}}"]
    )
    assert verification.clean is True


def test_survivor_span_indexes_original_text():
    text = "x a@b.com"
    verification = VerificationGate([EmailDetector()]).verify(text)
    span = verification.survivors[0].span
    assert text[span.start : span.end] == "a@b.com"


def test_suggested_tier_is_not_verified():
    class _SuggestDetector:
        def detect(self, text):
            index = text.find("maybe")
            if index < 0:
                return []
            return [
                Detection(
                    span=Span(index, index + 5),
                    value="maybe",
                    type="name",
                    label="NAME",
                    tier=TrustTier.SUGGESTED,
                    reason="looks like a name",
                    canonical="maybe",
                    restore="maybe",
                )
            ]

    verification = VerificationGate([_SuggestDetector()]).verify("maybe a name")
    assert verification.clean is True  # suggestions are review-gated, not verified
