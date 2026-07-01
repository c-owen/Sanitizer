"""Transcript-level sanitization — per-segment timing, shared placeholders, merge.

Covers PG5 (timing preserved), cross-segment placeholder consistency, the merged
review items, fail-closed across segments, and the apply_review re-derivation used
when the user edits decisions (Phase 5b) — plus JSON round-tripping for the sidecar.
"""

from __future__ import annotations

from dataclasses import dataclass

from cloak_core.detectors.declared import DeclaredListDetector
from cloak_core.model import DecisionState, Detection, Span, TrustTier
from cloak_core.transcript import (
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
    the text it is handed (a window), like the real model would."""

    tier = TrustTier.SUGGESTED

    def __init__(self, *surfaces):  # each: (surface, label, type)
        self._surfaces = surfaces

    def detect(self, text):
        out = []
        for surface, label, type_ in self._surfaces:
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


def test_scrubbed_text_joins_segments():
    segments = [Seg(0, 1, "Call Jane"), Seg(1, 2, "or Bob")]
    result = sanitize_transcript(segments, _declared("Jane", "Bob"))
    assert result.scrubbed_text == "Call {{TERM-1}}\nor {{TERM-2}}"
    assert result.original_text == "Call Jane\nor Bob"


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
    from cloak_core.transcript import next_free_placeholder

    existing = {"{{PERSON-A}}", "{{PERSON-B}}"}
    assert (
        next_free_placeholder(existing, "PERSON") == "{{PERSON-C}}"
    )  # entities letter
    assert next_free_placeholder(existing, "EMAIL") == "{{EMAIL-1}}"  # others number


# --- miss-catching (UX-3 / FR-22 / FR-16) -----------------------------------
def test_find_miss_candidates_ranks_by_frequency():
    from cloak_core.transcript import find_miss_candidates

    candidates = find_miss_candidates("Karen met Karen and Bobby")
    assert candidates[0].surface == "Karen"  # count 2 → first
    assert candidates[0].count == 2
    assert {c.surface for c in candidates} == {"Karen", "Bobby"}


def test_find_miss_candidates_excludes_known_and_placeholders():
    from cloak_core.transcript import find_miss_candidates

    candidates = find_miss_candidates("{{PERSON-A}} met Karen and Bob", known={"bob"})
    assert {c.surface for c in candidates} == {"Karen"}  # placeholder + Bob excluded


def test_build_manual_item_redacts_all_occurrences():
    from cloak_core.transcript import build_manual_item

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
    from cloak_core.transcript import build_manual_item

    segments = sanitize_transcript(
        [Seg(0, 1, "nothing here")], _declared("Zzz")
    ).segments
    assert build_manual_item("Karen", segments, existing_placeholders=set()) is None


# --- on-demand windowed suggestions -----------------------------------------
def test_suggest_items_locates_a_windowed_find_across_segments():
    from cloak_core.transcript import suggest_items

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
    from cloak_core.transcript import suggest_items

    segments = sanitize_transcript(
        [Seg(0, 1, "Sarah Chen met Bob")], _declared("Zzz")
    ).segments
    detector = _StubSuggest(
        ("Sarah Chen", "PERSON", "person"), ("Bob", "PERSON", "person")
    )
    items = suggest_items(segments, detector, known_canonicals={"bob"})
    assert {i.original for i in items} == {"Sarah Chen"}  # Bob already handled


def test_suggest_items_drops_phantoms_not_in_any_single_segment():
    from cloak_core.transcript import suggest_items

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
