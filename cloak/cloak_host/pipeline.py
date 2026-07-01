"""Cloak's ``on_complete`` pipeline: sanitize a finished transcript → sidecar.

Host glue around the pure core. It builds detectors from the plugin's config, runs
:func:`~cloak_core.transcript.sanitize_transcript` over the **saved** segments
(read-only — the stored transcript is NEVER modified, PG5), and writes the sidecar
keyed by ``transcription_id`` (the key in its own file, PG8).

The default config is the **guaranteed path only** (declared + PII), fully offline
and dependency-free. The suggestion model is **opt-in** and constructed lazily, so a
default install never imports an ML library or hits the network.
"""

from __future__ import annotations

import hashlib
import logging
import os

from cloak_core import __version__ as core_version
from cloak_core import persistence
from cloak_core.detectors.declared import DeclaredListDetector, parse_declared_terms
from cloak_core.detectors.pii import PII_TYPES, pii_detectors
from cloak_core.transcript import sanitize_transcript
from cloak_host.paths import sidecar_dir

logger = logging.getLogger(__name__)

CONFIG_DECLARED_TERMS = "declared_terms"
CONFIG_ENABLE_SUGGESTIONS = "enable_suggestions"


def pii_config_key(pii_type: str) -> str:
    """Config key for a per-type PII toggle, e.g. ``pii_email``."""
    return f"pii_{pii_type}"


def enabled_pii_types(config: dict) -> set[str]:
    """The PII types whose toggle is on (default on)."""
    return {t for t in PII_TYPES if _coerce_bool(config.get(pii_config_key(t), True))}


def build_detectors(config: dict) -> list:
    """Assemble the detector set from plugin config (guaranteed path by default)."""
    detectors: list = []

    terms = parse_declared_terms(config.get(CONFIG_DECLARED_TERMS, "") or "")
    if terms:
        detectors.append(DeclaredListDetector(terms))

    detectors.extend(pii_detectors(enabled_pii_types(config)))

    if _coerce_bool(config.get(CONFIG_ENABLE_SUGGESTIONS, False)):
        suggester = _build_suggestion_detector()
        if suggester is not None:
            detectors.append(suggester)

    return detectors


def sanitize_to_sidecar(transcription_id, segments, config: dict, *, base_dir=None):
    """Sanitize ``segments`` and persist the sidecar; return (directory, result).

    ``base_dir`` overrides the real Buzz cache location (used by tests). The stored
    transcript is never touched — only the sidecar is written.
    """
    detectors = build_detectors(config)
    sanitization = sanitize_transcript(segments, detectors)

    directory = (
        os.path.join(base_dir, str(transcription_id))
        if base_dir is not None
        else sidecar_dir(transcription_id)
    )
    meta = {
        "cloak_version": core_version,
        "transcription_id": str(transcription_id),
        "clean": sanitization.clean,
        "removed_items": sanitization.removed_items,
        "pending_items": sanitization.pending_items,
        "segment_count": len(sanitization.segments),
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


def _build_suggestion_detector():
    """Construct the model-backed suggestion detector, or ``None`` if unavailable.

    Imported lazily so the guaranteed path never pays for the ML stack; any failure
    (missing dep, etc.) degrades to no suggestions.
    """
    try:
        from cloak_core.detectors.suggest import ModelSuggestionDetector
        from cloak_host.model_provider_buzz import BuzzGlinerProvider

        return ModelSuggestionDetector(BuzzGlinerProvider())
    except Exception:  # noqa: BLE001 - suggestions are best-effort, never required
        logger.exception("Cloak: suggestion model unavailable; skipping suggestions")
        return None


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
