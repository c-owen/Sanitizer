"""Import/export format handlers: the swappable format seam (FR-24, FR-14).

v1 ships ``text`` and ``markdown``, both directions. Adding a new format (a new
file here, e.g. SRT/VTT in P2) must not require touching detection, the sanitizer
or restore.
"""

from __future__ import annotations

from sanitizer_core.formats.base import FormatHandler
from sanitizer_core.formats.markdown import MarkdownHandler
from sanitizer_core.formats.text import TextHandler

_HANDLERS: dict[str, type] = {
    "text": TextHandler,
    "markdown": MarkdownHandler,
}

FORMATS: tuple[str, ...] = tuple(_HANDLERS)


def format_handler(name: str) -> FormatHandler:
    """Return the handler for ``name`` (``"text"`` or ``"markdown"``)."""
    try:
        return _HANDLERS[name]()
    except KeyError:
        raise ValueError(f"unknown format: {name!r}") from None


__all__ = [
    "FORMATS",
    "FormatHandler",
    "MarkdownHandler",
    "TextHandler",
    "format_handler",
]
