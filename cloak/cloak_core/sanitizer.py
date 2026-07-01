"""The sanitizer — orchestrates detect → decide → substitute → verify.

Host-independent. Covers the guaranteed tiers (declared + PII, auto-approved)
and runs the fail-closed verification gate. Model suggestions (review-gated,
PENDING; Phase 4) flow through the same tier-agnostic path: held for review,
never auto-applied, and excluded from the gate (FR-9, FR-14).
"""

from __future__ import annotations

from cloak_core.detectors.base import Detector
from cloak_core.model import (
    Decision,
    DecisionState,
    Detection,
    SanitizationResult,
    Span,
    TrustTier,
)
from cloak_core.placeholders import DEFAULT_SCHEME, PlaceholderScheme
from cloak_core.vault import Vault
from cloak_core.verify import VerificationGate


def _resolve_overlaps(detections: list[Detection]) -> list[Detection]:
    """Keep a non-overlapping set, preferring the **longest** span, then higher
    trust, then position.

    Longest-wins matters when one detection contains another — e.g. a declared
    name inside an email (``jane@acme.com``). Letting the email win removes the
    whole address (no ``@domain`` fragment leaks) while still removing the name
    (it's inside the larger placeholder), so the declared guarantee holds. With a
    single detector there are no cross-detector overlaps and this is a no-op.
    """
    ordered = sorted(
        detections,
        key=lambda d: (-d.span.length, d.tier.value, d.span.start),
    )
    kept: list[Detection] = []
    for det in ordered:
        if any(det.span.overlaps(other.span) for other in kept):
            continue
        kept.append(det)
    return kept


def sanitize(
    text: str,
    detectors: list[Detector],
    *,
    vault: Vault | None = None,
    scheme: PlaceholderScheme = DEFAULT_SCHEME,
) -> SanitizationResult:
    """Detect and replace sensitive items in ``text``.

    Guarantees: declared terms and enabled PII become consistent placeholders
    (FR-1/FR-2/FR-3); the same input yields the same result (PG6); the key
    reverses every replacement (PG4); substrings are never corrupted (FR-1); and
    the result is re-checked, with ``clean=False`` + ``survivors`` if anything
    guaranteed leaked (FR-6/PG7). Pass a shared ``vault`` to keep placeholders
    consistent across multiple texts/segments.
    """
    vault = vault if vault is not None else Vault(scheme)

    detections: list[Detection] = []
    for detector in detectors:
        detections.extend(detector.detect(text))
    kept = _resolve_overlaps(detections)

    # Group occurrences by canonical identity → one decision per item (FR-3),
    # preserving first-seen order for a stable, readable decision list.
    by_canonical: dict[str, list[Detection]] = {}
    order: list[str] = []
    for det in sorted(kept, key=lambda d: d.span.start):
        if det.canonical not in by_canonical:
            by_canonical[det.canonical] = []
            order.append(det.canonical)
        by_canonical[det.canonical].append(det)

    decisions: list[Decision] = []
    replacements: list[tuple[Span, str]] = []
    for canonical in order:
        occurrences = by_canonical[canonical]
        # The most-trusted occurrence represents the group: if the same value is
        # both guaranteed (declared/PII) and model-suggested, the guaranteed tier
        # wins — auto-approved and removed everywhere, never held for review. With
        # a single tier this is just the first occurrence (overlap resolution has
        # already dropped lower-tier hits that share a span).
        representative = min(occurrences, key=lambda d: (d.tier.value, d.span.start))
        # Guaranteed tiers (declared + PII) are removed automatically; only model
        # suggestions are held PENDING for review (FR-9). A PENDING item is not
        # spliced in and gets no placeholder/key entry here, so the key stays
        # exactly the set of applied substitutions; its placeholder is allocated on
        # approval (Phase 5).
        state = (
            DecisionState.PENDING
            if representative.tier == TrustTier.SUGGESTED
            else DecisionState.APPROVED
        )
        if state == DecisionState.APPROVED:
            placeholder = vault.placeholder_for(
                canonical, representative.label, representative.restore
            )
            replacements.extend((det.span, placeholder) for det in occurrences)
        else:
            placeholder = ""
        decisions.append(
            Decision(
                canonical=canonical,
                placeholder=placeholder,
                label=representative.label,
                original=representative.restore,
                tier=representative.tier,
                type=representative.type,
                reason=representative.reason,
                state=state,
                occurrences=list(occurrences),
            )
        )

    scrubbed = _apply(text, replacements)
    key = vault.key()
    # Independent re-check (FR-6): re-scan the output and fail closed if any
    # declared term or enabled PII type survived. Placeholders are ignored so a
    # term that appears inside a label (e.g. declared "TERM") isn't a false hit.
    # Suggestion detectors are excluded: their items are review-gated (never
    # auto-removed, so they are *expected* to remain) and re-running a model
    # during verification would be wasteful.
    guaranteed = [
        d for d in detectors if getattr(d, "tier", None) != TrustTier.SUGGESTED
    ]
    verification = VerificationGate(guaranteed).verify(
        scrubbed, ignore=key.entries.keys()
    )
    return SanitizationResult(
        scrubbed=scrubbed,
        decisions=decisions,
        key=key,
        clean=verification.clean,
        survivors=verification.survivors,
    )


def _apply(text: str, replacements: list[tuple[Span, str]]) -> str:
    """Splice placeholders into ``text``, right-to-left so spans stay valid."""
    result = text
    for span, placeholder in sorted(
        replacements, key=lambda item: item[0].start, reverse=True
    ):
        result = result[: span.start] + placeholder + result[span.end :]
    return result
