"""Cloak's cross-transcript app state — a tiny preferences store.

Some facts outlive a single transcript *and* a single window, so they belong
neither in a per-transcript sidecar (:mod:`cloak_core.persistence`) nor in Buzz's
plugin config (which Cloak only reads). Three such facts live here:

* ``has_reviewed`` — the user has completed at least one review. This **gates**
  the informed auto-apply offer (FR-12): Cloak never offers to auto-apply
  suggestions until the user has seen how review works at least once.
* ``auto_apply_suggestions`` — the user's informed opt-in (FR-12). When set, the
  *host* auto-approves suggestions after sanitization. The core never does this
  (it still holds suggestions PENDING, FR-9); this only records the choice.
* ``key_note_dismissed`` — the one-time "the key is the secret" teaching (US6)
  has been dismissed, so it shows once and never again.

Pure filesystem + JSON; the directory is **injected by the host** (the core never
decides where Buzz's cache lives), exactly like :mod:`cloak_core.persistence`.
Reads are total — a missing or corrupt file yields defaults, never an error — so a
first run and a damaged store both behave as "nothing decided yet".
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

PREFERENCES_FILE = "preferences.json"


@dataclass
class Preferences:
    """Cloak's persistent, cross-transcript preferences (all default to off)."""

    has_reviewed: bool = False
    auto_apply_suggestions: bool = False
    key_note_dismissed: bool = False


def read_preferences(directory: str | Path) -> Preferences:
    """Load preferences from ``directory``; return defaults if absent/unreadable."""
    path = Path(directory) / PREFERENCES_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Preferences()
    if not isinstance(data, dict):
        return Preferences()
    return Preferences(
        has_reviewed=bool(data.get("has_reviewed", False)),
        auto_apply_suggestions=bool(data.get("auto_apply_suggestions", False)),
        key_note_dismissed=bool(data.get("key_note_dismissed", False)),
    )


def write_preferences(directory: str | Path, preferences: Preferences) -> None:
    """Persist ``preferences`` into ``directory`` (created if needed)."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    (path / PREFERENCES_FILE).write_text(
        json.dumps(asdict(preferences), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
