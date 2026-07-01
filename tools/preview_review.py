"""Open the real Cloak ReviewWindow with sample data — a dev preview (no Buzz).

The review UI is a normal top-level Qt window backed by a sidecar directory, so it
runs standalone. This harness writes a few sample sidecars into a throwaway temp dir
and opens the live window against them, so you can click through every state —
Review / Send out / Restore, safe / unsafe / empty, the suggestions Approve/Reject,
the miss-catching strip, the first-use key note, the auto-apply offer (appears after
you make one decision), and the declared-list editor — with real fonts.

Run in the PyQt6 venv, with a real display (NOT offscreen):

    .venv-qt/Scripts/python.exe tools/preview_review.py         # from the repo root

Each run starts from fresh preferences (temp dir), so the first-use teaching shows
and auto-apply is hidden until you approve/reject something. This is a preview of the
UI only — for the end-to-end pipeline (transcribe → sidecar → menu) use the real-Buzz
build→serve→ingest loop in DEV_NOTES.md §3.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT / "cloak", _REPO_ROOT / "buzz"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from cloak_core import persistence  # noqa: E402
from cloak_core.detectors.declared import DeclaredListDetector  # noqa: E402
from cloak_core.detectors.pii import pii_detectors  # noqa: E402
from cloak_core.detectors.suggest import (  # noqa: E402
    ModelSuggestionDetector,
    RawEntity,
)
from cloak_core.transcript import sanitize_transcript  # noqa: E402


@dataclass
class _Seg:
    start: int
    end: int
    text: str


class _StubModel:
    """A tiny stand-in for the suggestion model — flags one fixed name, no ML."""

    def __init__(self, surface: str, label: str) -> None:
        self._surface, self._label = surface, label

    def predict(self, text, labels):
        index = text.find(self._surface)
        if index < 0:
            return []
        return [RawEntity(index, index + len(self._surface), self._label, 0.9)]


def _meta(sanitization, *, clean=True, **extra):
    meta = {
        "clean": clean,
        "removed_items": sanitization.removed_items,
        "pending_items": sanitization.pending_items,
        "segment_count": len(sanitization.segments),
        "detector_count": 8,
    }
    meta.update(extra)
    return meta


def _write(base: Path, tid: str, segments, detectors, *, clean=True) -> None:
    sanitization = sanitize_transcript(segments, detectors)
    persistence.write_sidecar(
        base / tid, sanitization, _meta(sanitization, clean=clean)
    )


def _seed(base: Path) -> None:
    declared = DeclaredListDetector({"person": ["Jane"], "project": ["Apollo"]})
    pii = pii_detectors({"email", "phone"})
    suggest = ModelSuggestionDetector(_StubModel("Acme", "organization"))

    # A rich, safe transcript: declared + PII removed, a held suggestion (Acme),
    # and an uncaught capitalized name (Karen ×2) for the miss-catching strip.
    _write(
        base,
        "depo-2026-06-30",
        [
            _Seg(0, 4000, "This is the deposition of Jane regarding project Apollo."),
            _Seg(4000, 8000, "Reach me at jane@example.com or 415-555-1212."),
            _Seg(
                8000,
                12000,
                "Acme was the vendor. Karen took minutes; Karen follows up.",
            ),
        ],
        [declared, *pii, suggest],
    )

    # An UNSAFE transcript — the blocking/withheld state (PG7).
    _write(
        base,
        "call-unsafe",
        [_Seg(0, 3000, "Ring Jane and also loop in Bob before Friday.")],
        [DeclaredListDetector(["Jane"])],
        clean=False,
    )

    # A transcript where nothing matched — the "nothing found, with receipts" state.
    _write(
        base,
        "standup-clean",
        [_Seg(0, 3000, "Quick sync, nothing sensitive, ship it.")],
        [DeclaredListDetector(["Zzz"])],
    )


def main() -> None:
    base = Path(tempfile.mkdtemp(prefix="cloak-preview-"))
    _seed(base)

    app = QApplication(sys.argv)
    from cloak_host.review_window import ReviewWindow

    window = ReviewWindow(base_dir=str(base))
    window.show()
    window.raise_()
    window.activateWindow()
    # ASCII-only console output — a Windows cp1252 console throws on fancy glyphs,
    # and that would kill the process before app.exec() ever runs.
    print(f"Cloak review preview - sample sidecars in:\n  {base}")
    print("Close the window to exit. (Temp dir is left behind for inspection.)")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
