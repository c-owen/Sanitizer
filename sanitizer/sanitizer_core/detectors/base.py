"""The Detector interface — the swappable detection-method seam (FR-14)."""

from __future__ import annotations

from typing import Protocol

from sanitizer_core.model import Detection


class Detector(Protocol):
    """Finds sensitive occurrences in a text.

    Assumes: ``text`` is the exact string that returned spans index into.
    Guarantees (each implementation): for every returned :class:`Detection`,
    ``d.value == text[d.span.start:d.span.end]``, the span lies within bounds,
    and matches never corrupt substrings (a match is a standalone token, not
    part of a larger word). Detections from different detectors may overlap; the
    sanitizer resolves overlaps by trust tier.
    """

    def detect(self, text: str) -> list[Detection]: ...
