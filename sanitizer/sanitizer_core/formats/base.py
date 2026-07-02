"""The FormatHandler interface — how scrubbed text leaves, and how returned text
comes back, for a given format (FR-24)."""

from __future__ import annotations

from typing import Protocol


class FormatHandler(Protocol):
    """Adapts scrubbed text to/from a wire format.

    Assumes: placeholders are robust (FR-23), so the round trip never alters a
    token; ``serialize`` then ``parse`` preserves every placeholder.
    Guarantees (each implementation): ``serialize`` produces output the user can
    copy out in this format, and ``parse`` returns text ready for ``restore``
    (which is substring-based, so format wrapping *around* a token is fine).
    """

    name: str

    def serialize(self, text: str) -> str: ...

    def parse(self, text: str) -> str: ...
