"""The Vault — allocates consistent placeholders and records the reversible key."""

from __future__ import annotations

from sanitizer_core.model import Key
from sanitizer_core.placeholders import DEFAULT_SCHEME, PlaceholderScheme


class Vault:
    """Allocates one placeholder per distinct canonical value and records the key.

    Guarantees:
      * idempotent — the same ``canonical`` always returns the same placeholder;
      * injective — distinct canonical values get distinct placeholders;
      * reversible — :meth:`key` maps every allocated placeholder to its original.

    A single Vault can be shared across many texts/segments so placeholders stay
    consistent across a whole transcript.
    """

    def __init__(self, scheme: PlaceholderScheme = DEFAULT_SCHEME) -> None:
        self._scheme = scheme
        self._placeholder_by_canonical: dict[str, str] = {}
        self._original_by_placeholder: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def placeholder_for(self, canonical: str, label: str, original: str) -> str:
        existing = self._placeholder_by_canonical.get(canonical)
        if existing is not None:
            return existing
        index = self._counters.get(label, 0) + 1
        self._counters[label] = index
        placeholder = self._scheme.format(label, index)
        self._placeholder_by_canonical[canonical] = placeholder
        self._original_by_placeholder[placeholder] = original
        return placeholder

    def key(self) -> Key:
        return Key(entries=dict(self._original_by_placeholder))
