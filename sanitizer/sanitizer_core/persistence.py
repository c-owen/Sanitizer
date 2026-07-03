"""Sidecar persistence: Sanitizer's private store, kept separate from the transcript.

Pure filesystem + JSON; the directory is **injected by the host** (the core never
decides where Buzz's cache lives). Each sanitized transcript becomes a folder with
four files:

    meta.json       version, clean flag, counts, settings snapshot, source hash
    key.json        placeholder -> original  (THE SECRET: separate file, PG8)
    decisions.json  one entry per review item (placeholder, original, why, state…)
    segments.json   per-segment original + scrubbed text, timing preserved (PG5)

The user's stored Buzz transcript is never touched: this is Sanitizer's own working
copy (the scrubbed text is the thing the user copies out). ``meta.json`` is written
**last**, so its presence marks a complete, readable sidecar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sanitizer_core.model import Key
from sanitizer_core.transcript import (
    ReviewItem,
    SanitizedSegment,
    TranscriptSanitization,
    _join_as_paragraphs,
    item_from_dict,
    item_to_dict,
    segment_from_dict,
    segment_to_dict,
)

META_FILE = "meta.json"
KEY_FILE = "key.json"
DECISIONS_FILE = "decisions.json"
SEGMENTS_FILE = "segments.json"


@dataclass
class Sidecar:
    """A loaded sidecar: the review items, the scrubbed segments, the key, meta."""

    meta: dict = field(default_factory=dict)
    segments: list[SanitizedSegment] = field(default_factory=list)
    items: list[ReviewItem] = field(default_factory=list)
    key: Key = field(default_factory=Key)

    @property
    def scrubbed_text(self) -> str:
        return _join_as_paragraphs(self.segments, lambda s: s.scrubbed)

    @property
    def original_text(self) -> str:
        return _join_as_paragraphs(self.segments, lambda s: s.original)


def has_sidecar(directory: str | Path) -> bool:
    """True if ``directory`` holds a complete sidecar (its ``meta.json`` exists)."""
    return (Path(directory) / META_FILE).is_file()


def read_meta(directory: str | Path) -> dict:
    """Read just ``meta.json`` from a sidecar directory.

    Cheaper than :func:`read_sidecar` for callers that only need meta (e.g. a
    transcription picker rendering a label) and would otherwise pay for loading
    the segments, decisions and key too.
    """
    return _read_json(Path(directory) / META_FILE, {})


def write_sidecar(
    directory: str | Path,
    sanitization: TranscriptSanitization,
    meta: dict,
) -> None:
    """Write the four sidecar files into ``directory`` (created if needed).

    ``meta.json`` is written last so a half-finished write is never seen as
    complete by :func:`has_sidecar` / :func:`read_sidecar`.
    """
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    _write_json(
        path / SEGMENTS_FILE,
        [segment_to_dict(segment) for segment in sanitization.segments],
    )
    _write_json(
        path / DECISIONS_FILE, [item_to_dict(item) for item in sanitization.items]
    )
    _write_json(path / KEY_FILE, sanitization.key.to_dict())
    _write_json(path / META_FILE, meta)


def read_sidecar(directory: str | Path) -> Sidecar | None:
    """Load a sidecar from ``directory``, or ``None`` if none is present."""
    path = Path(directory)
    if not has_sidecar(path):
        return None
    return Sidecar(
        meta=_read_json(path / META_FILE, {}),
        segments=[segment_from_dict(d) for d in _read_json(path / SEGMENTS_FILE, [])],
        items=[item_from_dict(d) for d in _read_json(path / DECISIONS_FILE, [])],
        key=Key.from_dict(_read_json(path / KEY_FILE, {})),
    )


def list_sidecars(base_directory: str | Path) -> list[str]:
    """Names of subdirectories under ``base`` that hold a sidecar, newest first."""
    base = Path(base_directory)
    if not base.is_dir():
        return []
    folders = [p for p in base.iterdir() if p.is_dir() and has_sidecar(p)]
    folders.sort(key=lambda p: (p / META_FILE).stat().st_mtime, reverse=True)
    return [p.name for p in folders]


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
