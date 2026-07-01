"""Sidecar persistence — write/read round trip, completeness marker, listing.

Pure filesystem (uses tmp_path); no buzz/Qt. Confirms the sidecar preserves the
review items, scrubbed segments and the (separate) key, that an incomplete write
isn't seen as a sidecar, and that listing orders newest-first.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cloak_core import persistence
from cloak_core.detectors.declared import DeclaredListDetector
from cloak_core.model import DecisionState, TrustTier
from cloak_core.transcript import sanitize_transcript


@dataclass
class Seg:
    start: int
    end: int
    text: str


def _sanitize():
    segments = [Seg(0, 1, "Jane and Jane"), Seg(1, 2, "then Bob")]
    return sanitize_transcript(segments, [DeclaredListDetector(["Jane", "Bob"])])


def _meta(sanitization):
    return {
        "cloak_version": "test",
        "clean": sanitization.clean,
        "removed_items": sanitization.removed_items,
    }


def test_write_then_read_round_trips(tmp_path):
    sanitization = _sanitize()
    directory = tmp_path / "42"
    persistence.write_sidecar(directory, sanitization, _meta(sanitization))

    sidecar = persistence.read_sidecar(directory)
    assert sidecar is not None
    assert sidecar.meta["removed_items"] == 2
    assert sidecar.scrubbed_text == sanitization.scrubbed_text
    assert sidecar.key.entries == sanitization.key.entries
    assert {item.original for item in sidecar.items} == {"Jane", "Bob"}


def test_items_preserve_tier_state_and_placements(tmp_path):
    sanitization = _sanitize()
    directory = tmp_path / "1"
    persistence.write_sidecar(directory, sanitization, _meta(sanitization))

    sidecar = persistence.read_sidecar(directory)
    jane = next(i for i in sidecar.items if i.original == "Jane")
    assert jane.tier is TrustTier.DECLARED
    assert jane.state is DecisionState.APPROVED
    assert jane.count == 2  # two placements survived the round trip


def test_key_is_a_separate_file(tmp_path):
    sanitization = _sanitize()
    directory = tmp_path / "7"
    persistence.write_sidecar(directory, sanitization, _meta(sanitization))
    # PG8: the key lives in its own file, not embedded in the scrubbed segments.
    assert (directory / persistence.KEY_FILE).is_file()
    segments_text = (directory / persistence.SEGMENTS_FILE).read_text("utf-8")
    assert "Jane" in segments_text  # the 'original' field is here…
    key_text = (directory / persistence.KEY_FILE).read_text("utf-8")
    assert "{{TERM-1}}" in key_text  # …and the placeholder->original map is separate


def test_missing_sidecar_reads_as_none(tmp_path):
    assert persistence.read_sidecar(tmp_path / "nope") is None
    assert persistence.has_sidecar(tmp_path / "nope") is False


def test_meta_absence_means_no_sidecar(tmp_path):
    # A directory with the other files but no meta.json is treated as incomplete.
    directory = tmp_path / "partial"
    directory.mkdir()
    (directory / persistence.KEY_FILE).write_text("{}", encoding="utf-8")
    assert persistence.has_sidecar(directory) is False


def test_list_sidecars_orders_newest_first(tmp_path):
    sanitization = _sanitize()
    for name in ("older", "newer"):
        persistence.write_sidecar(tmp_path / name, sanitization, _meta(sanitization))
    # Force deterministic mtimes on the completeness marker.
    os.utime(tmp_path / "older" / persistence.META_FILE, (1000, 1000))
    os.utime(tmp_path / "newer" / persistence.META_FILE, (2000, 2000))
    assert persistence.list_sidecars(tmp_path) == ["newer", "older"]


def test_list_sidecars_empty_base(tmp_path):
    assert persistence.list_sidecars(tmp_path / "absent") == []
