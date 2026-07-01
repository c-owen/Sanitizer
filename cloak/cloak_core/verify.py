"""The verification gate — the independent re-check that fails closed (FR-6, PG7).

After substitution, the gate re-scans the scrubbed output with the *guaranteed*
detectors (declared + enabled PII). If any of them still matches, a declared term
or enabled PII type leaked, so the result is **not clean** — and the host must
refuse to present it as safe or auto-copy it (PG7). Model suggestions are a
separate, review-gated tier and are deliberately **not** verified here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cloak_core.detectors.base import Detector
from cloak_core.model import Detection, TrustTier

# Tiers that are removed automatically and therefore must not survive.
GUARANTEED_TIERS = frozenset({TrustTier.DECLARED, TrustTier.PII})


@dataclass(frozen=True)
class Verification:
    clean: bool
    survivors: list[Detection] = field(default_factory=list)


class VerificationGate:
    """Re-scans text and reports any surviving guaranteed item.

    Assumes: ``ignore`` holds the placeholders just emitted (so the gate doesn't
    flag a declared term that happens to appear inside a placeholder label).
    Guarantees: ``clean`` is True iff no declared/PII detector matches the text
    outside the ignored placeholders; survivor spans index the text as given.
    """

    def __init__(self, detectors: list[Detector]) -> None:
        self._detectors = detectors

    def verify(self, text: str, *, ignore: object = ()) -> Verification:
        scan = _mask(text, ignore)
        survivors = [
            detection
            for detector in self._detectors
            for detection in detector.detect(scan)
            if detection.tier in GUARANTEED_TIERS
        ]
        return Verification(clean=not survivors, survivors=survivors)


def _mask(text: str, ignore: object) -> str:
    """Blank out each ignored token with equal-length spaces, preserving offsets
    so survivor spans stay valid against the original text."""
    scan = text
    for token in sorted(set(ignore), key=len, reverse=True):
        if token:
            scan = scan.replace(token, " " * len(token))
    return scan
