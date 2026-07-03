"""Sanitizer's host-independent sanitization core.

Pure Python by contract: this package MUST NOT import Buzz or PyQt6, so the
safety-critical logic stays verifiable on its own (enforced by
``tests/boundary_test.py``). Public API below; internals live in the submodules.
"""

from __future__ import annotations

from sanitizer_core import persistence
from sanitizer_core.appstate import (
    Preferences,
    read_preferences,
    write_preferences,
)
from sanitizer_core.categories import CATEGORIES, label_for
from sanitizer_core.declared_store import (
    add_declared_term,
    read_declared_terms,
    remove_declared_term,
    write_declared_terms,
)
from sanitizer_core.detectors.base import Detector
from sanitizer_core.detectors.declared import DeclaredListDetector, parse_declared_terms
from sanitizer_core.detectors.pii import PII_TYPES, pii_detectors
from sanitizer_core.detectors.suggest import (
    DEFAULT_LABELS,
    ModelProvider,
    ModelSuggestionDetector,
    RawEntity,
)
from sanitizer_core.formats import (
    FORMATS,
    FormatHandler,
    MarkdownHandler,
    TextHandler,
    format_handler,
)
from sanitizer_core.model import (
    Decision,
    DecisionState,
    Detection,
    Key,
    SanitizationResult,
    Span,
    TrustTier,
)
from sanitizer_core.persistence import (
    Sidecar,
    has_sidecar,
    list_sidecars,
    read_meta,
    read_sidecar,
    write_sidecar,
)
from sanitizer_core.placeholders import (
    BraceScheme,
    BracketScheme,
    PlaceholderScheme,
    is_ascii_safe,
    is_markdown_safe,
)
from sanitizer_core.restore import restore
from sanitizer_core.sanitizer import sanitize
from sanitizer_core.transcript import (
    MissCandidate,
    Placement,
    ReviewItem,
    SanitizedSegment,
    TranscriptSanitization,
    apply_review,
    build_manual_item,
    find_miss_candidates,
    next_free_placeholder,
    sanitize_transcript,
    scan_safe_text,
    suggest_items,
)
from sanitizer_core.vault import Vault
from sanitizer_core.verify import Verification, VerificationGate

__version__ = "0.7.2"

__all__ = [
    "CATEGORIES",
    "DEFAULT_LABELS",
    "FORMATS",
    "PII_TYPES",
    "BraceScheme",
    "BracketScheme",
    "Decision",
    "DecisionState",
    "Detection",
    "Detector",
    "DeclaredListDetector",
    "FormatHandler",
    "Key",
    "MarkdownHandler",
    "MissCandidate",
    "ModelProvider",
    "ModelSuggestionDetector",
    "PlaceholderScheme",
    "Placement",
    "Preferences",
    "RawEntity",
    "ReviewItem",
    "SanitizationResult",
    "SanitizedSegment",
    "Sidecar",
    "Span",
    "TextHandler",
    "TranscriptSanitization",
    "TrustTier",
    "Vault",
    "Verification",
    "VerificationGate",
    "add_declared_term",
    "apply_review",
    "build_manual_item",
    "find_miss_candidates",
    "format_handler",
    "has_sidecar",
    "is_ascii_safe",
    "is_markdown_safe",
    "label_for",
    "list_sidecars",
    "next_free_placeholder",
    "parse_declared_terms",
    "persistence",
    "pii_detectors",
    "read_declared_terms",
    "read_meta",
    "read_preferences",
    "read_sidecar",
    "remove_declared_term",
    "restore",
    "sanitize",
    "sanitize_transcript",
    "scan_safe_text",
    "suggest_items",
    "write_declared_terms",
    "write_preferences",
    "write_sidecar",
]
