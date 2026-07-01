"""Markdown format handler (FR-24).

For v1 this is a pass-through, and deliberately so: a transcript is already valid
CommonMark, and the placeholder scheme is markdown-safe (FR-23), so the tokens
survive rendering untouched. Restore is substring-based, so when the returned
markdown wraps a token (``**{{NAME-1}}**``, `` `{{NAME-1}}` ``, a list item, a
block quote), the token is still found and replaced — the surrounding formatting
is preserved. Richer markdown handling (e.g. escaping) is unnecessary for the
round trip and would alter the user's text, so we don't do it.
"""

from __future__ import annotations


class MarkdownHandler:
    """Emit/accept transcript text as markdown (pass-through for v1)."""

    name = "markdown"

    def serialize(self, text: str) -> str:
        return text

    def parse(self, text: str) -> str:
        return text
