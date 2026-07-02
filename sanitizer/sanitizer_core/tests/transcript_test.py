"""Transcript-level sanitization — per-segment timing, shared placeholders, merge.

Covers PG5 (timing preserved), cross-segment placeholder consistency, the merged
review items, fail-closed across segments, and the apply_review re-derivation used
when the user edits decisions (Phase 5b) — plus JSON round-tripping for the sidecar.
"""

from __future__ import annotations

from dataclasses import dataclass

from sanitizer_core.detectors.declared import DeclaredListDetector
from sanitizer_core.model import DecisionState, Detection, Span, TrustTier
from sanitizer_core.transcript import (
    apply_review,
    item_from_dict,
    item_to_dict,
    sanitize_transcript,
    segment_from_dict,
    segment_to_dict,
)


@dataclass
class Seg:
    start: int
    end: int
    text: str


class _MissesSecondDetector:
    """Detects only the first 'SECRET' in a text — a recall miss the gate catches."""

    def detect(self, text):
        index = text.find("SECRET")
        if index < 0:
            return []
        return [
            Detection(
                span=Span(index, index + 6),
                value="SECRET",
                type="secret",
                label="SECRET",
                tier=TrustTier.PII,
                reason="pattern",
                canonical="secret",
                restore="SECRET",
            )
        ]


def _declared(*terms):
    return [DeclaredListDetector(list(terms))]


class _StubSuggest:
    """A stand-in suggestion detector: flags fixed surfaces wherever they appear in
    the text it is handed (a window), like the real model would. Each spec is
    ``(surface, label, type[, score])`` — score defaults to 1.0."""

    tier = TrustTier.SUGGESTED

    def __init__(self, *surfaces):
        self._surfaces = surfaces

    def detect(self, text):
        out = []
        for spec in self._surfaces:
            surface, label, type_ = spec[0], spec[1], spec[2]
            score = spec[3] if len(spec) > 3 else 1.0
            index = text.find(surface)
            if index >= 0:
                out.append(
                    Detection(
                        span=Span(index, index + len(surface)),
                        value=surface,
                        type=type_,
                        label=label,
                        tier=TrustTier.SUGGESTED,
                        reason="model suggestion",
                        canonical=surface.strip().casefold(),
                        restore=surface,
                        score=score,
                    )
                )
        return out


def test_segment_timing_is_preserved():
    segments = [Seg(0, 1000, "Hi Jane"), Seg(1000, 2500, "Bye Jane")]
    result = sanitize_transcript(segments, _declared("Jane"))
    assert [(s.start, s.end) for s in result.segments] == [(0, 1000), (1000, 2500)]


def test_same_value_shares_placeholder_across_segments():
    segments = [Seg(0, 1, "Jane here"), Seg(1, 2, "and Jane there")]
    result = sanitize_transcript(segments, _declared("Jane"))
    assert len(result.items) == 1
    item = result.items[0]
    assert item.count == 2
    assert {p.segment for p in item.placements} == {0, 1}
    assert result.segments[0].scrubbed == "{{TERM-1}} here"
    assert result.segments[1].scrubbed == "and {{TERM-1}} there"


def test_scrubbed_text_joins_close_segments_as_one_paragraph():
    # A tiny (< 2s) gap between segments reads as continuous speech — space-joined
    # prose, matching Buzz's own plain-text export, not one line per segment.
    segments = [Seg(0, 1, "Call Jane"), Seg(1, 2, "or Bob")]
    result = sanitize_transcript(segments, _declared("Jane", "Bob"))
    assert result.scrubbed_text == "Call {{TERM-1}} or {{TERM-2}}"
    assert result.original_text == "Call Jane or Bob"


def test_scrubbed_text_breaks_paragraph_on_a_real_pause():
    # A >= 2s gap between segments is a real pause — starts a new paragraph
    # (matches Buzz's BUZZ_PARAGRAPH_SPLIT_TIME default of 2000ms).
    segments = [Seg(0, 1000, "Call Jane"), Seg(3000, 4000, "or Bob")]
    result = sanitize_transcript(segments, _declared("Jane", "Bob"))
    assert result.scrubbed_text == "Call {{TERM-1}}\n\nor {{TERM-2}}"
    assert result.original_text == "Call Jane\n\nor Bob"


def test_scrubbed_text_gap_just_under_threshold_stays_one_paragraph():
    segments = [Seg(0, 1000, "Call Jane"), Seg(2999, 4000, "or Bob")]  # 1999ms gap
    result = sanitize_transcript(segments, _declared("Jane", "Bob"))
    assert "\n\n" not in result.scrubbed_text
    assert result.scrubbed_text == "Call {{TERM-1}} or {{TERM-2}}"


def test_distinct_segments_distinct_placeholders_and_counts():
    segments = [Seg(0, 1, "Jane"), Seg(1, 2, "Bob"), Seg(2, 3, "Jane again")]
    result = sanitize_transcript(segments, _declared("Jane", "Bob"))
    assert {i.original: i.count for i in result.items} == {"Jane": 2, "Bob": 1}
    assert result.removed_items == 2


def test_clean_is_false_if_any_segment_leaks():
    # The transcript is clean only if every segment is: a recall miss in segment 1
    # must fail the whole transcript closed (clean=False), collecting the survivor.
    segments = [Seg(0, 1, "nothing here"), Seg(1, 2, "SECRET and SECRET")]
    result = sanitize_transcript(segments, [_MissesSecondDetector()])
    assert result.clean is False
    assert any(s.value == "SECRET" for s in result.survivors)


def test_clean_transcript_stays_clean():
    segments = [Seg(0, 1, "Jane"), Seg(1, 2, "nothing")]
    result = sanitize_transcript(segments, _declared("Jane"))
    assert result.clean is True
    assert result.survivors == []


def test_apply_review_reproduces_sanitization():
    segments = [Seg(0, 1, "Jane and Jane"), Seg(1, 2, "then Bob")]
    result = sanitize_transcript(segments, _declared("Jane", "Bob"))
    rebuilt, key = apply_review(result.segments, result.items)
    assert [s.scrubbed for s in rebuilt] == [s.scrubbed for s in result.segments]
    assert key.entries == result.key.entries


def test_apply_review_reflects_a_rejected_item():
    segments = [Seg(0, 1, "Jane and Bob")]
    result = sanitize_transcript(segments, _declared("Jane", "Bob"))
    jane = next(i for i in result.items if i.original == "Jane")
    jane.state = DecisionState.REJECTED
    rebuilt, key = apply_review(result.segments, result.items)
    assert "Jane" in rebuilt[0].scrubbed  # kept in cleartext now
    assert jane.placeholder not in key.entries  # and dropped from the key
    assert "Bob" not in rebuilt[0].scrubbed  # Bob still removed


def test_item_json_round_trip():
    segments = [Seg(0, 1, "Jane"), Seg(1, 2, "Jane")]
    item = sanitize_transcript(segments, _declared("Jane")).items[0]
    restored = item_from_dict(item_to_dict(item))
    assert restored.original == "Jane"
    assert restored.tier is TrustTier.DECLARED
    assert restored.state is DecisionState.APPROVED
    assert [(p.segment, p.start, p.end) for p in restored.placements] == [
        (p.segment, p.start, p.end) for p in item.placements
    ]


def test_segment_json_round_trip():
    segment = sanitize_transcript([Seg(0, 5, "Jane")], _declared("Jane")).segments[0]
    restored = segment_from_dict(segment_to_dict(segment))
    assert (restored.start, restored.end) == (0, 5)
    assert restored.original == "Jane"
    assert restored.scrubbed == "{{TERM-1}}"


def test_empty_transcript_is_empty():
    result = sanitize_transcript([], _declared("Jane"))
    assert result.items == []
    assert result.scrubbed_text == ""
    assert result.clean is True


def test_next_free_placeholder_skips_used_and_letters_vs_numbers():
    from sanitizer_core.transcript import next_free_placeholder

    existing = {"{{PERSON-A}}", "{{PERSON-B}}"}
    assert (
        next_free_placeholder(existing, "PERSON") == "{{PERSON-C}}"
    )  # entities letter
    assert next_free_placeholder(existing, "EMAIL") == "{{EMAIL-1}}"  # others number


# --- miss-catching (UX-3 / FR-22 / FR-16) -----------------------------------
def test_find_miss_candidates_ranks_by_frequency():
    from sanitizer_core.transcript import find_miss_candidates

    candidates = find_miss_candidates("Karen met Karen and Bobby")
    assert candidates[0].surface == "Karen"  # count 2 → first
    assert candidates[0].count == 2
    assert {c.surface for c in candidates} == {"Karen", "Bobby"}


def test_find_miss_candidates_excludes_known_and_placeholders():
    from sanitizer_core.transcript import find_miss_candidates

    candidates = find_miss_candidates("{{PERSON-A}} met Karen and Bob", known={"bob"})
    assert {c.surface for c in candidates} == {"Karen"}  # placeholder + Bob excluded


def test_scan_safe_text_never_merges_a_run_across_a_segment_boundary():
    # Regression: _join_as_paragraphs (display) can space-join two close segments,
    # which would let the miss-scan regex invent "Karen Karen again" -- a phrase
    # present in no single segment -- if it were fed that text. scan_safe_text
    # must always hard-break with \n regardless of how close the segments are.
    from sanitizer_core.transcript import find_miss_candidates, scan_safe_text

    segments = sanitize_transcript(
        [Seg(0, 1, "Call Jane about Karen"), Seg(1, 2, "Karen again")],
        _declared("Jane"),
    ).segments
    text = scan_safe_text(segments)
    assert "\n" in text  # never space-joined, no matter the segment gap

    candidates = find_miss_candidates(text)
    surfaces = {c.surface for c in candidates}
    assert "Karen Karen again" not in surfaces  # the phantom must not appear
    assert "Karen" in surfaces or "Karen again" in surfaces  # real candidates intact


def test_build_manual_item_redacts_all_occurrences():
    from sanitizer_core.transcript import build_manual_item

    segments = sanitize_transcript(
        [Seg(0, 1, "Karen and Karen"), Seg(1, 2, "then Karen")], _declared("Zzz")
    ).segments
    item = build_manual_item("Karen", segments, existing_placeholders=set())
    assert item is not None
    assert item.tier is TrustTier.DECLARED
    assert item.state is DecisionState.APPROVED
    assert item.count == 3
    assert item.original == "Karen"


def test_build_manual_item_none_when_absent():
    from sanitizer_core.transcript import build_manual_item

    segments = sanitize_transcript(
        [Seg(0, 1, "nothing here")], _declared("Zzz")
    ).segments
    assert build_manual_item("Karen", segments, existing_placeholders=set()) is None


# --- on-demand windowed suggestions -----------------------------------------
def test_suggest_items_locates_a_windowed_find_across_segments():
    from sanitizer_core.transcript import suggest_items

    segments = sanitize_transcript(
        [Seg(0, 1, "Councillor Sarah Chen spoke"), Seg(1, 2, "then Sarah Chen left")],
        _declared("Zzz"),
    ).segments
    items = suggest_items(
        segments,
        _StubSuggest(("Sarah Chen", "PERSON", "person")),
        known_canonicals=set(),
    )
    assert len(items) == 1
    item = items[0]
    assert item.original == "Sarah Chen"
    assert item.tier is TrustTier.SUGGESTED
    assert item.state is DecisionState.PENDING
    assert item.placeholder == ""  # allocated only on approval
    assert item.count == 2  # both occurrences re-located, spans exact


def test_suggest_items_skips_known_canonicals():
    from sanitizer_core.transcript import suggest_items

    segments = sanitize_transcript(
        [Seg(0, 1, "Sarah Chen met Bob")], _declared("Zzz")
    ).segments
    detector = _StubSuggest(
        ("Sarah Chen", "PERSON", "person"), ("Bob", "PERSON", "person")
    )
    items = suggest_items(segments, detector, known_canonicals={"bob"})
    assert {i.original for i in items} == {"Sarah Chen"}  # Bob already handled


def test_suggest_items_drops_phantoms_not_in_any_single_segment():
    from sanitizer_core.transcript import suggest_items

    # "Sarah Chen" only exists across the window join, in no single segment.
    segments = sanitize_transcript(
        [Seg(0, 1, "Sarah"), Seg(1, 2, "Chen")], _declared("Zzz")
    ).segments
    items = suggest_items(
        segments,
        _StubSuggest(("Sarah Chen", "PERSON", "person")),
        known_canonicals=set(),
    )
    assert items == []  # re-location fails → dropped (no invalid placement)


def test_suggest_items_keeps_the_model_score():
    from sanitizer_core.transcript import suggest_items

    segments = sanitize_transcript(
        [Seg(0, 1, "Sarah Chen spoke")], _declared("Zzz")
    ).segments
    items = suggest_items(
        segments,
        _StubSuggest(("Sarah Chen", "PERSON", "person", 0.73)),
        known_canonicals=set(),
    )
    assert items[0].score == 0.73  # carried onto the review item for the triage filter


def test_suggest_items_keeps_the_highest_score_across_windows():
    from sanitizer_core.transcript import suggest_items

    # window_chars=1 → one window per segment; the same surface, seen twice, keeps its
    # most confident sighting (0.9), not whichever window happened to be first.
    segments = sanitize_transcript(
        [Seg(0, 1, "Sarah Chen here"), Seg(1, 2, "Sarah Chen again")], _declared("Zzz")
    ).segments

    class _Rising:
        tier = TrustTier.SUGGESTED

        def __init__(self):
            self._calls = 0

        def detect(self, text):
            self._calls += 1
            score = 0.4 if self._calls == 1 else 0.9
            index = text.find("Sarah Chen")
            if index < 0:
                return []
            return [
                Detection(
                    span=Span(index, index + 10),
                    value="Sarah Chen",
                    type="person",
                    label="PERSON",
                    tier=TrustTier.SUGGESTED,
                    reason="model suggestion",
                    canonical="sarah chen",
                    restore="Sarah Chen",
                    score=score,
                )
            ]

    items = suggest_items(segments, _Rising(), known_canonicals=set(), window_chars=1)
    assert len(items) == 1
    assert items[0].score == 0.9
    assert items[0].count == 2  # both sightings still re-located


def test_item_json_round_trip_preserves_score():
    from sanitizer_core.transcript import suggest_items

    segments = sanitize_transcript([Seg(0, 1, "Sarah Chen")], _declared("Zzz")).segments
    item = suggest_items(
        segments,
        _StubSuggest(("Sarah Chen", "PERSON", "person", 0.66)),
        known_canonicals=set(),
    )[0]
    assert item_from_dict(item_to_dict(item)).score == 0.66
