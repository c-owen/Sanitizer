"""Property-based checks for the two load-bearing guarantees (FR-1, PG4).

`hypothesis` is a test-only dependency; the suite skips cleanly without it (the
explicit example tests already cover these cases — this widens the input space).
"""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from sanitizer_core.detectors.declared import DeclaredListDetector  # noqa: E402
from sanitizer_core.restore import restore  # noqa: E402
from sanitizer_core.sanitizer import sanitize  # noqa: E402

# "Wordy" tokens: letters only, so there are no regex-special chars and a clean
# word boundary on either side.
_words = st.text(
    alphabet=st.characters(min_codepoint=ord("a"), max_codepoint=ord("z")),
    min_size=1,
    max_size=8,
)


@given(term=_words, filler=st.lists(_words, max_size=6))
def test_substring_safety_property(term, filler):
    # The term embedded inside a longer word must never be detected on its own.
    text = " ".join([*filler, term + "x"])
    for det in DeclaredListDetector([term]).detect(text):
        assert det.value.casefold() == term.casefold()


@given(terms=st.lists(_words, min_size=1, max_size=5, unique_by=lambda s: s.casefold()))
def test_round_trip_property(terms):
    text = " ".join(terms)
    result = sanitize(text, [DeclaredListDetector(terms)])
    assert restore(result.scrubbed, result.key) == text
