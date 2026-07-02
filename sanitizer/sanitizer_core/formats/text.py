"""Plain-text format handler — the identity round trip (FR-24)."""

from __future__ import annotations


class TextHandler:
    """Scrubbed text is already plain text; restore runs on it directly."""

    name = "text"

    def serialize(self, text: str) -> str:
        return text

    def parse(self, text: str) -> str:
        return text
