"""Placeholder robustness — the markdown / copy-paste / edit reliability gate (FR-23).

The placeholder must survive the markdown round trip so restore stays reliable.
These tests pin the two properties (ASCII-safe, markdown-safe) and prove restore
works when the token is wrapped or lightly edited.
"""

from __future__ import annotations

import unicodedata

import pytest

from sanitizer_core.detectors.declared import DeclaredListDetector
from sanitizer_core.model import Key
from sanitizer_core.placeholders import (
    DEFAULT_SCHEME,
    BracketScheme,
    is_ascii_safe,
    is_markdown_safe,
)
from sanitizer_core.restore import restore
from sanitizer_core.sanitizer import sanitize


def test_default_token_shape():
    assert DEFAULT_SCHEME.format("TERM", 1) == "{{TERM-1}}"


def test_default_token_is_ascii_and_markdown_safe():
    token = DEFAULT_SCHEME.format("EMAIL", 3)
    assert is_ascii_safe(token)  # survives legacy / cp1252 copy-paste
    assert is_markdown_safe(token)  # no markdown-active characters


def test_bracket_scheme_is_markdown_safe_but_not_ascii():
    # Documents WHY the default moved away from ⟦ ⟧ (the cp1252 / font signal).
    token = BracketScheme().format("TERM", 1)
    assert is_markdown_safe(token)
    assert not is_ascii_safe(token)


def test_token_unchanged_by_unicode_normalization():
    token = DEFAULT_SCHEME.format("TERM", 1)
    for form in ("NFC", "NFD", "NFKC", "NFKD"):
        assert unicodedata.normalize(form, token) == token


@pytest.mark.parametrize(
    "wrapped",
    [
        "**{{TERM-1}}**",  # bold
        "_{{TERM-1}}_",  # italic
        "`{{TERM-1}}`",  # inline code
        "- {{TERM-1}}",  # list item
        "> {{TERM-1}}",  # block quote
        "{{TERM-1}}.",  # trailing period
        "({{TERM-1}})",  # parenthesized
        "[{{TERM-1}}](http://x)",  # link text
        "see {{TERM-1}}, ok",  # adjacent comma
    ],
)
def test_restore_survives_markdown_wrapping(wrapped):
    key = Key({"{{TERM-1}}": "Jane"})
    assert "Jane" in restore(wrapped, key)


def test_token_survives_real_markdown_render():
    md = pytest.importorskip("markdown")
    html = md.markdown("contact {{TERM-1}} now")
    assert "{{TERM-1}}" in html


def test_markdown_round_trip_restores_original():
    result = sanitize(
        "Jane met Bob about the deal.", [DeclaredListDetector(["Jane", "Bob"])]
    )
    # Jane is the first item → {{TERM-1}}; simulate the LLM bolding it.
    returned = result.scrubbed.replace("{{TERM-1}}", "**{{TERM-1}}**")
    assert restore(returned, result.key) == "**Jane** met Bob about the deal."
