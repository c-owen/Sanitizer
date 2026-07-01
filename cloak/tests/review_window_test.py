"""ReviewWindow (Step A v2 UX) — two-zone tree, withheld-unsafe, key, restore.

Requires PyQt6 + pytest-qt (skips elsewhere). Drives the window against a sidecar
written by the pure core into a temp dir — no Buzz, no real cache. Includes the
PG7 guarantee (unsafe → scrubbed text is unreachable to any copy path) and the
UX-5 guarantee (tier/state readable without colour).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
)

from cloak_core import persistence  # noqa: E402
from cloak_core.detectors.declared import DeclaredListDetector  # noqa: E402
from cloak_core.detectors.suggest import (  # noqa: E402
    ModelSuggestionDetector,
    RawEntity,
)
from cloak_core.transcript import sanitize_transcript  # noqa: E402


@dataclass
class Seg:
    start: int
    end: int
    text: str


class _StubProvider:
    """Locates a fixed surface in the text → a RawEntity (a fake model)."""

    def __init__(self, surface, label):
        self._surface = surface
        self._label = label

    def predict(self, text, labels):
        index = text.find(self._surface)
        if index < 0:
            return []
        return [RawEntity(index, index + len(self._surface), self._label, 0.9)]


def _meta(sanitization, clean=True):
    return {
        "clean": clean,
        "removed_items": sanitization.removed_items,
        "pending_items": sanitization.pending_items,
    }


def _write_sidecar(directory):
    sanitization = sanitize_transcript(
        [Seg(0, 1000, "Call Jane"), Seg(1000, 2000, "bye Jane")],
        [DeclaredListDetector(["Jane"])],
    )
    persistence.write_sidecar(directory / "5", sanitization, _meta(sanitization))
    return sanitization


def _write_with_suggestion(directory):
    # "Jane" declared (approved) + "Acme" suggested (pending).
    detectors = [
        DeclaredListDetector(["Jane"]),
        ModelSuggestionDetector(_StubProvider("Acme", "organization")),
    ]
    sanitization = sanitize_transcript([Seg(0, 1, "Jane at Acme")], detectors)
    persistence.write_sidecar(directory / "9", sanitization, _meta(sanitization))
    return sanitization


def _write_unsafe(directory):
    sanitization = sanitize_transcript(
        [Seg(0, 1, "Ring Jane and Bob")], [DeclaredListDetector(["Jane"])]
    )
    persistence.write_sidecar(
        directory / "7", sanitization, _meta(sanitization, clean=False)
    )
    return sanitization  # scrubbed_text == "Ring {{TERM-1}} and Bob"


def _new_window(tmp_path, qtbot):
    from cloak_host.review_window import ReviewWindow

    window = ReviewWindow(base_dir=str(tmp_path))
    qtbot.addWidget(window)
    return window


def _selectable_texts(window):
    out = []
    for widget in window.findChildren(QPlainTextEdit):
        out.append(widget.toPlainText())
    for widget in window.findChildren(QTextEdit):
        out.append(widget.toPlainText())
    for widget in window.findChildren(QLineEdit):
        out.append(widget.text())
    return out


# --- structure --------------------------------------------------------------
def test_loads_two_zone_tree(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert window._group_removed.childCount() == 1
    removed_row = window._group_removed.child(0)
    assert "{{TERM-1}}" in removed_row.text(0)
    assert "Jane" in removed_row.text(1)
    assert window._group_suggestions.childCount() == 0
    assert not window._group_cleartext.isExpanded()
    assert "SAFE" in window._spine_label.text()


def test_scrubbed_shown_when_safe(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert window._scrubbed_group.isVisibleTo(window)
    assert "{{TERM-1}}" in window._scrubbed_edit.toPlainText()
    assert "Jane" not in window._scrubbed_edit.toPlainText()


def test_empty_state_when_no_sidecars(tmp_path, qtbot):
    window = _new_window(tmp_path, qtbot)

    assert window._selector.count() == 0
    assert window._group_removed.childCount() == 0
    assert "No sanitized transcripts" in window._spine_label.text()


# --- restore + key ----------------------------------------------------------
def test_restore_round_trips(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._returned_edit.setPlainText(window._scrubbed_edit.toPlainText())
    window._restore_button.click()

    assert window._restored_edit.toPlainText() == "Call Jane\nbye Jane"


def test_restore_handles_markdown_wrapping(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._returned_edit.setPlainText("Call **{{TERM-1}}** please")
    window._restore_button.click()

    assert window._restored_edit.toPlainText() == "Call **Jane** please"


def test_key_is_hidden_until_revealed(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert not window._key_edit.isVisibleTo(window)  # secret hidden by default
    window._reveal_button.setChecked(True)
    assert window._key_edit.isVisibleTo(window)
    assert "{{TERM-1}}" in window._key_edit.toPlainText()


def test_copy_scrubbed_confirms_with_toast(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._copy_button.click()
    assert "copied" in window._last_toast


# --- suggestions (Approve/Reject buttons, held by default) ------------------
def test_pending_suggestion_starts_in_cleartext(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert "Jane" not in window._scrubbed_edit.toPlainText()  # declared removed
    assert "Acme" in window._scrubbed_edit.toPlainText()  # suggestion held
    assert "acme" in window._suggestion_buttons  # Approve/Reject present


def test_approving_a_suggestion_removes_it_and_persists(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._suggestion_buttons["acme"][0].click()  # Approve

    assert "Acme" not in window._scrubbed_edit.toPlainText()
    assert "Acme" in window._sidecar.key.entries.values()

    reopened = _new_window(tmp_path, qtbot)
    assert "Acme" not in reopened._scrubbed_edit.toPlainText()  # persisted


def test_rejecting_a_suggestion_moves_to_cleartext_and_reapproves(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._suggestion_buttons["acme"][1].click()  # Reject

    assert "Acme" in window._scrubbed_edit.toPlainText()  # kept in cleartext
    assert window._group_cleartext.childCount() == 1
    cleartext_row = window._group_cleartext.child(0)
    assert "Acme" in cleartext_row.text(0)
    assert cleartext_row.font(0).strikeOut()  # struck through (UX-9 / UX-5)

    window._reapprove_buttons["acme"].click()  # Remove after all
    assert "Acme" not in window._scrubbed_edit.toPlainText()


# --- rejecting a guaranteed row via the keyboard-accessible action ----------
def test_keep_action_rejects_guaranteed_row_and_is_keyboard_bound(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    # The action carries a shortcut → it is NOT mouse-only (context menu + key).
    assert not window._keep_action.shortcut().isEmpty()

    window._tree.setCurrentItem(window._group_removed.child(0))  # the Jane row
    window._keep_action.trigger()

    assert "Jane" in window._scrubbed_edit.toPlainText()  # kept in cleartext
    assert window._sidecar.key.entries == {}  # dropped from the key
    assert window._group_cleartext.childCount() == 1


def test_approve_everything_detected(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._approve_all_button.click()

    scrubbed = window._scrubbed_edit.toPlainText()
    assert "Jane" not in scrubbed
    assert "Acme" not in scrubbed


# --- PG7: unsafe withholds the scrubbed text from every copy path -----------
def test_unsafe_withholds_scrubbed_and_blocks_every_copy_path(tmp_path, qtbot):
    sanitization = _write_unsafe(tmp_path)
    scrubbed = sanitization.scrubbed_text
    assert scrubbed  # sanity: there is something that must be withheld
    window = _new_window(tmp_path, qtbot)

    # Loud, blocking, and worded (not colour-only).
    assert window._unsafe_wall.isVisibleTo(window)
    assert not window._scrubbed_group.isVisibleTo(window)
    assert "UNSAFE" in window._spine_label.text()

    # 1) The scrubbed text is in no selectable/copyable widget.
    assert all(scrubbed not in text for text in _selectable_texts(window))

    # 2) No reachable copy path: the handler is a hard no-op, even called direct.
    clipboard = QApplication.clipboard()
    clipboard.setText("SENTINEL-UNCHANGED")
    window._copy_scrubbed()
    assert clipboard.text() == "SENTINEL-UNCHANGED"

    # 3) The affordance itself is gone.
    assert not window._copy_button.isEnabled()


# --- UX-5: tier + state readable without colour -----------------------------
def test_zone_headers_and_state_read_without_colour(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert "REMOVED" in window._group_removed.text(0)
    assert "SUGGESTIONS" in window._group_suggestions.text(0)
    assert "Keeping in cleartext" in window._group_cleartext.text(0)

    # A rejected item is carried by strike-out + grouping, not colour.
    window._tree.setCurrentItem(window._group_removed.child(0))
    window._keep_action.trigger()
    assert window._group_cleartext.child(0).font(0).strikeOut()
