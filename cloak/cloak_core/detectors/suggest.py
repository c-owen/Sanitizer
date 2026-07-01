"""Model-suggestion detection — the additive, review-gated tier (FR-9/FR-15).

A small on-device zero-shot model proposes *undeclared* names, organizations,
locations and obvious codename/project mentions. These are **suggestions**, not
guarantees: they enter the ``SUGGESTED`` tier, are always held PENDING for the
user's one-click review (FR-9), are never auto-applied, and are deliberately
excluded from the verification gate (PG6 — the guaranteed set stays predictable).

This module is **host-independent**. The model itself lives behind a
:class:`ModelProvider` **port** so ``cloak_core`` never imports an ML library or
Buzz: the host supplies an adapter (``cloak_host/model_provider_buzz.py``) and
tests inject a stub. The detector owns *what* to look for (zero-shot labels) and
the confidence cutoff; the provider only knows *how* to run a model.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from cloak_core.categories import ORG, PERSON, PLACE, PROJECT, label_for
from cloak_core.model import Detection, Span, TrustTier

logger = logging.getLogger(__name__)

# Zero-shot labels requested from the model (a GLiNER-style hint). Tunable per
# provider; the category map below absorbs synonyms and fixed-NER tag spellings.
DEFAULT_LABELS: tuple[str, ...] = ("person", "organization", "location", "project")

# Confidence below which a candidate is dropped. Suggestions are reviewed anyway,
# so this only trims obvious noise; the provider may pre-filter at a lower floor.
DEFAULT_THRESHOLD = 0.5

# Model label (lower-cased) → Cloak category. Covers GLiNER zero-shot labels and
# the fixed tags a transformers-NER fallback emits (PER / ORG / LOC / MISC).
_CATEGORY_BY_LABEL: dict[str, str] = {
    "person": PERSON,
    "people": PERSON,
    "name": PERSON,
    "per": PERSON,
    "organization": ORG,
    "organisation": ORG,
    "company": ORG,
    "org": ORG,
    "location": PLACE,
    "place": PLACE,
    "gpe": PLACE,
    "loc": PLACE,
    "project": PROJECT,
    "project name": PROJECT,
    "codename": PROJECT,
    "product": PROJECT,
    "program": PROJECT,
    "misc": PROJECT,
}

_REASON_BY_CATEGORY: dict[str, str] = {
    PERSON: "possible name (model suggestion)",
    ORG: "possible organization (model suggestion)",
    PLACE: "possible location (model suggestion)",
    PROJECT: "possible codename or project (model suggestion)",
}


@dataclass(frozen=True)
class RawEntity:
    """One entity span as reported by a :class:`ModelProvider`.

    ``start``/``end`` index the exact text passed to ``predict``; ``label`` is the
    model's own label string (mapped to a category by the detector); ``score`` is
    its confidence in ``[0, 1]``.
    """

    start: int
    end: int
    label: str
    score: float = 1.0


class ModelProvider(Protocol):
    """Port: run a local NER/zero-shot model over text and return entity spans.

    Assumes: ``text`` is the exact string the returned offsets index into.
    Guarantees expected of an implementation: offsets lie within ``text`` and
    ``score`` is in ``[0, 1]``. The provider may pre-filter at a permissive floor;
    the detector applies the authoritative confidence cutoff. Implementations live
    in ``cloak_host`` (so the core never imports an ML lib); ``labels`` are a
    best-effort hint a fixed-label model may ignore.
    """

    def predict(self, text: str, labels: Sequence[str]) -> list[RawEntity]: ...


def _canonical(value: str) -> str:
    """Identity for a suggested value: internal whitespace collapsed, casefolded
    (mirrors the declared detector, so a suggestion of a declared term groups with
    it and the guaranteed tier wins)."""
    return re.sub(r"\s+", " ", value).strip().casefold()


def _trim(value: str, start: int, end: int) -> tuple[str, int, int]:
    """Strip edge whitespace from a span, keeping offsets exact so the substring
    invariant (``value == text[start:end]``) still holds."""
    lead = len(value) - len(value.lstrip())
    trail = len(value) - len(value.rstrip())
    return value.strip(), start + lead, end - trail


class ModelSuggestionDetector:
    """Turns a :class:`ModelProvider`'s entities into ``SUGGESTED`` detections.

    Assumes: ``text`` is the text spans index into.
    Guarantees: every returned :class:`Detection` is ``SUGGESTED`` tier with
    ``value == text[span.start:span.end]`` (substring-safe), carries a categorized
    label/reason, and never crashes the pipeline — if the provider raises (e.g. the
    model is unavailable), detection degrades to an empty list so the guaranteed
    path is unaffected.
    """

    # Declares to the sanitizer/gate that this detector only ever suggests, so its
    # items are excluded from the fail-closed re-check (they are never auto-removed).
    tier = TrustTier.SUGGESTED

    def __init__(
        self,
        provider: ModelProvider,
        *,
        labels: Sequence[str] = DEFAULT_LABELS,
        threshold: float = DEFAULT_THRESHOLD,
        category_map: dict[str, str] | None = None,
    ) -> None:
        self._provider = provider
        self._labels = tuple(labels)
        self._threshold = threshold
        self._category_map = dict(_CATEGORY_BY_LABEL)
        if category_map:
            self._category_map.update(
                {key.lower(): value for key, value in category_map.items()}
            )
        # Observability. This tier degrades to ``[]`` on any provider failure so the
        # guaranteed path is never affected — but a silent ``[]`` is indistinguishable
        # from "the model ran and found nothing". These record *why*, so a caller (the
        # on-demand "Run suggestions" flow) can tell the user a missing/broken model
        # apart from an empty result, instead of reporting a false "all clear".
        self.available = True
        self.last_error: str | None = None

    def detect(self, text: str) -> list[Detection]:
        try:
            entities = self._provider.predict(text, self._labels)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully if model fails
            self.available = False
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("suggestion model failed; continuing without suggestions")
            return []

        detections: list[Detection] = []
        for entity in entities:
            if entity.score < self._threshold:
                continue
            if not 0 <= entity.start < entity.end <= len(text):
                continue
            value, start, end = _trim(
                text[entity.start : entity.end], entity.start, entity.end
            )
            if not value:
                continue
            category = self._category_for(entity.label)
            if category is None:
                continue
            detections.append(
                Detection(
                    span=Span(start, end),
                    value=value,
                    type=category,
                    label=label_for(category),
                    tier=TrustTier.SUGGESTED,
                    reason=_REASON_BY_CATEGORY.get(
                        category, f"possible {category} (model suggestion)"
                    ),
                    canonical=_canonical(value),
                    restore=value,
                    score=entity.score,
                )
            )
        return detections

    def _category_for(self, label: str) -> str | None:
        return self._category_map.get(label.strip().lower())
