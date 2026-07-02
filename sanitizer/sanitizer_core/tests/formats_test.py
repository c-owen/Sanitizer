"""Format handlers — text & markdown, both directions (FR-24)."""

from __future__ import annotations

import pytest

from sanitizer_core.detectors.declared import DeclaredListDetector
from sanitizer_core.formats import FORMATS, format_handler
from sanitizer_core.formats.markdown import MarkdownHandler
from sanitizer_core.formats.text import TextHandler
from sanitizer_core.restore import restore
from sanitizer_core.sanitizer import sanitize


def test_registry_has_text_and_markdown():
    assert set(FORMATS) == {"text", "markdown"}


def test_format_handler_lookup():
    assert isinstance(format_handler("text"), TextHandler)
    assert isinstance(format_handler("markdown"), MarkdownHandler)


def test_unknown_format_raises():
    with pytest.raises(ValueError):
        format_handler("docx")


@pytest.mark.parametrize("name", ["text", "markdown"])
def test_round_trip_through_handler(name):
    handler = format_handler(name)
    result = sanitize("Jane called Bob.", [DeclaredListDetector(["Jane", "Bob"])])
    serialized = handler.serialize(result.scrubbed)  # copy out in this format
    restored = restore(handler.parse(serialized), result.key)  # paste back, restore
    assert restored == "Jane called Bob."


def test_markdown_handler_preserves_placeholders():
    handler = MarkdownHandler()
    result = sanitize("Jane", [DeclaredListDetector(["Jane"])])
    assert "{{TERM-1}}" in handler.serialize(result.scrubbed)
