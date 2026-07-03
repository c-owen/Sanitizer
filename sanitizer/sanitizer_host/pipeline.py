"""Sanitizer's ``on_complete`` pipeline: sanitize a finished transcript → sidecar.

Host glue around the pure core. It builds detectors from the plugin's config, runs
:func:`~sanitizer_core.transcript.sanitize_transcript` over the **saved** segments
(read-only: the stored transcript is NEVER modified, PG5), and writes the sidecar
keyed by ``transcription_id`` (the key in its own file, PG8).

The default config is the **guaranteed path only** (declared + PII), fully offline
and dependency-free. The suggestion model is **opt-in** and constructed lazily, so a
default install never imports an ML library or hits the network.
"""

from __future__ import annotations

import hashlib
import logging
import os

from sanitizer_core import __version__ as core_version
from sanitizer_core import persistence
from sanitizer_core.appstate import Preferences, read_preferences
from sanitizer_core.declared_store import read_declared_terms
from sanitizer_core.detectors.declared import DeclaredListDetector, parse_declared_terms
from sanitizer_core.detectors.pii import PII_TYPES, pii_detectors
from sanitizer_core.model import DecisionState, TrustTier
from sanitizer_core.transcript import (
    apply_review,
    next_free_placeholder,
    sanitize_transcript,
)
from sanitizer_host.paths import sanitizer_data_dir, sidecar_dir

logger = logging.getLogger(__name__)

CONFIG_DECLARED_TERMS = "declared_terms"
CONFIG_ENABLE_SUGGESTIONS = "enable_suggestions"


def pii_config_key(pii_type: str) -> str:
    """Config key for a per-type PII toggle, e.g. ``pii_email``."""
    return f"pii_{pii_type}"


def enabled_pii_types(config: dict) -> set[str]:
    """The PII types whose toggle is on (default on)."""
    return {t for t in PII_TYPES if _coerce_bool(config.get(pii_config_key(t), True))}


def build_detectors(config: dict, *, data_dir: str | None = None) -> list:
    """Assemble the detector set from plugin config (guaranteed path by default).

    Declared terms are the **union** of the config textarea and Sanitizer's own
    declared-terms store (``data_dir``, when given), so a term the user added
    in-window (US2/FR-16) applies to this and every later transcript, not just the
    one where it was caught.
    """
    detectors: list = []

    terms = parse_declared_terms(_declared_text(config, data_dir))
    if terms:
        detectors.append(DeclaredListDetector(terms))

    detectors.extend(pii_detectors(enabled_pii_types(config)))

    if _coerce_bool(config.get(CONFIG_ENABLE_SUGGESTIONS, False)):
        suggester = _build_suggestion_detector()
        if suggester is not None:
            detectors.append(suggester)

    return detectors


def _declared_text(config: dict, data_dir: str | None) -> str:
    """Config declared-terms text unioned with Sanitizer's own store, as one blob."""
    text = config.get(CONFIG_DECLARED_TERMS, "") or ""
    if data_dir:
        stored = read_declared_terms(data_dir)
        if stored:
            text = (text + "\n" + "\n".join(stored)).strip()
    return text


def sanitize_to_sidecar(
    transcription_id, segments, config: dict, *, base_dir=None, source_name=None
):
    """Sanitize ``segments`` and persist the sidecar; return (directory, result).

    ``base_dir`` overrides the real Buzz cache location (used by tests) and is also
    where Sanitizer's declared-terms store and preferences live. The stored transcript
    is never touched: only the sidecar is written. ``source_name``, when given, is a
    display label (e.g. the source file's basename) recorded in ``meta.json`` so the
    review window can show it instead of the bare transcription id; Buzz has no
    public lookup for it after the fact, so the caller must capture it at hook time.
    """
    data_dir = base_dir if base_dir is not None else _data_dir()
    detectors = build_detectors(config, data_dir=data_dir)
    sanitization = sanitize_transcript(segments, detectors)

    # Informed auto-apply (FR-12): only after the user has reviewed at least once
    # and explicitly opted in. The pure core still held these PENDING (FR-9); this
    # is the *host* applying the user's recorded choice, never a silent default.
    prefs = read_preferences(data_dir) if data_dir else Preferences()
    auto_applied = 0
    if prefs.auto_apply_suggestions and prefs.has_reviewed:
        auto_applied = _auto_apply_suggestions(sanitization)

    directory = (
        os.path.join(base_dir, str(transcription_id))
        if base_dir is not None
        else sidecar_dir(transcription_id)
    )
    meta = {
        "sanitizer_version": core_version,
        "transcription_id": str(transcription_id),
        "source_name": source_name,
        "clean": sanitization.clean,
        "removed_items": sanitization.removed_items,
        "pending_items": sanitization.pending_items,
        "auto_applied_suggestions": auto_applied,  # FR-12: 0 unless opted in
        "segment_count": len(sanitization.segments),
        "detector_count": len(detectors),  # empty-state scan evidence (US8)
        "settings": {
            "pii": sorted(enabled_pii_types(config)),
            "suggestions": _coerce_bool(config.get(CONFIG_ENABLE_SUGGESTIONS, False)),
        },
        "source_sha256": hashlib.sha256(
            sanitization.original_text.encode("utf-8")
        ).hexdigest(),
    }
    persistence.write_sidecar(directory, sanitization, meta)
    return directory, sanitization


def _auto_apply_suggestions(sanitization) -> int:
    """Approve every held suggestion and re-derive; return how many (FR-12).

    Mutates ``sanitization`` in place: flips each PENDING suggestion to APPROVED,
    allocates a fresh placeholder, then re-derives the scrubbed segments + key via
    :func:`~sanitizer_core.transcript.apply_review`. ``clean`` is unaffected:
    suggestions are never gated, so approving them only adds removals.
    """
    existing = {i.placeholder for i in sanitization.items if i.placeholder}
    approved = 0
    for item in sanitization.items:
        if item.tier == TrustTier.SUGGESTED and item.state == DecisionState.PENDING:
            item.state = DecisionState.APPROVED
            if not item.placeholder:
                item.placeholder = next_free_placeholder(existing, item.label)
                existing.add(item.placeholder)
            approved += 1
    if approved:
        segments, key = apply_review(sanitization.segments, sanitization.items)
        sanitization.segments = segments
        sanitization.key = key
    return approved


def _data_dir() -> str | None:
    """Sanitizer's real data directory, or ``None`` if platformdirs is unavailable."""
    try:
        return sanitizer_data_dir()
    except Exception:  # noqa: BLE001 - platformdirs absent → no store, defaults
        return None


def _build_suggestion_detector():
    """Construct the model-backed suggestion detector, or ``None`` if unavailable.

    Imported lazily so the guaranteed path never pays for the ML stack; any failure
    (missing dep, etc.) degrades to no suggestions.
    """
    try:
        from sanitizer_core.detectors.suggest import ModelSuggestionDetector
        from sanitizer_host.model_provider_buzz import BuzzGlinerProvider

        return ModelSuggestionDetector(BuzzGlinerProvider())
    except Exception:  # noqa: BLE001 - suggestions are best-effort, never required
        logger.exception(
            "Sanitizer: suggestion model unavailable; skipping suggestions"
        )
        return None


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
