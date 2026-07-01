"""ReviewWindow (v2 UX, Step B) — modes, master-detail context, withheld-unsafe.

Requires PyQt6 + pytest-qt (skips elsewhere). Drives the window against a sidecar
written by the pure core into a temp dir — no Buzz, no real cache. Keeps the PG7
guarantee (unsafe → no reachable copy path in any mode) and UX-5 (readable without
colour), and adds Step-B coverage: the three modes, the side-by-side context pane,
the empty-state scan evidence, and the restore unresolved-tag report.
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
    def __init__(self, surface, label):
        self._surface = surface
        self._label = label

    def predict(self, text, labels):
        index = text.find(self._surface)
        if index < 0:
            return []
        return [RawEntity(index, index + len(self._surface), self._label, 0.9)]


def _meta(sanitization, clean=True, **extra):
    meta = {
        "clean": clean,
        "removed_items": sanitization.removed_items,
        "pending_items": sanitization.pending_items,
        "segment_count": len(sanitization.segments),
    }
    meta.update(extra)
    return meta


def _write_sidecar(directory):
    sanitization = sanitize_transcript(
        [Seg(0, 1000, "Call Jane"), Seg(1000, 2000, "bye Jane")],
        [DeclaredListDetector(["Jane"])],
    )
    persistence.write_sidecar(directory / "5", sanitization, _meta(sanitization))
    return sanitization


def _write_with_suggestion(directory):
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


def _write_empty(directory):
    # A transcript where nothing matched → the "nothing found" result (US8).
    sanitization = sanitize_transcript(
        [Seg(0, 1, "hello world")], [DeclaredListDetector(["Zzz"])]
    )
    persistence.write_sidecar(
        directory / "3", sanitization, _meta(sanitization, detector_count=7)
    )
    return sanitization


def _write_with_miss(directory):
    # "Karen" is entity-shaped but undeclared/unflagged → a miss candidate (UX-3).
    sanitization = sanitize_transcript(
        [Seg(0, 1, "Call Jane about Karen"), Seg(1, 2, "Karen again")],
        [DeclaredListDetector(["Jane"])],
    )
    persistence.write_sidecar(directory / "6", sanitization, _meta(sanitization))
    return sanitization


def _miss_buttons(window):
    from PyQt6.QtWidgets import QPushButton

    return window._miss_container.findChildren(QPushButton)


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


# --- structure + modes ------------------------------------------------------
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


def test_mode_switching(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert window._stack.currentIndex() == 0  # review by default
    window.set_mode("sendout")
    assert window._stack.currentIndex() == 1
    assert window._tab_buttons["sendout"].isChecked()
    window.set_mode("restore")
    assert window._stack.currentIndex() == 2


def test_scrubbed_available_when_safe(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert "{{TERM-1}}" in window._scrubbed_text
    assert "Jane" not in window._scrubbed_text


def test_empty_state_when_no_sidecars(tmp_path, qtbot):
    window = _new_window(tmp_path, qtbot)

    assert window._selector.count() == 0
    assert window._group_removed.childCount() == 0
    assert "No sanitized transcripts" in window._spine_label.text()


# --- context / side-by-side (UX-2) ------------------------------------------
def test_context_pane_populates_on_selection(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._tree.setCurrentItem(window._group_removed.child(0))  # the Jane row

    assert "Jane" in window._ctx_meta.text()
    assert "{{TERM-1}}" in window._ctx_meta.text()
    assert "«Jane»" in window._ctx_orig.toPlainText()
    assert "«{{TERM-1}}»" in window._ctx_sub.toPlainText()
    assert window._ctx_after_label.text() == "AFTER SUBSTITUTION"


def test_context_for_pending_suggestion_says_if_approved(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    # Acme is the sole child of the suggestions group.
    window._tree.setCurrentItem(window._group_suggestions.child(0))

    assert window._ctx_after_label.text() == "IF APPROVED"
    # ORG is an entity label → lettered placeholder ({{ORG-A}}, not {{ORG-1}}).
    assert "«{{ORG-A}}»" in window._ctx_sub.toPlainText()  # proposed placeholder
    assert "«Acme»" in window._ctx_orig.toPlainText()


# --- restore + key ----------------------------------------------------------
def test_restore_round_trips(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._returned_edit.setPlainText(window._scrubbed_text)
    window._restore_button.click()

    assert window._restored_edit.toPlainText() == "Call Jane\nbye Jane"


def test_restore_reports_unresolved_tags(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    # {{TERM-1}} is in the key; {{ORG-9}} is not → must be surfaced (FR-7).
    window._returned_edit.setPlainText("{{TERM-1}} and {{ORG-9}}")
    window._restore_button.click()

    assert window._restored_edit.toPlainText() == "Jane and {{ORG-9}}"
    assert "1 placeholder(s) filled" in window._restore_report.text()
    assert "unresolved" in window._restore_report.text()


def test_key_is_hidden_until_revealed(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)
    window.set_mode("sendout")

    assert not window._key_edit.isVisibleTo(window)  # secret hidden by default
    window._reveal_button.setChecked(True)
    assert window._key_edit.isVisibleTo(window)
    assert "{{TERM-1}}" in window._key_edit.toPlainText()


def test_send_out_copy_and_preview(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)
    window.set_mode("sendout")

    assert window._copy_button.isEnabled()
    window._copy_button.click()
    assert "copied" in window._last_toast

    assert not window._preview_edit.isVisibleTo(window)  # collapsed by default
    window._preview_toggle.setChecked(True)
    assert window._preview_edit.isVisibleTo(window)
    assert "{{TERM-1}}" in window._preview_edit.toPlainText()


# --- suggestions (Approve/Reject; held by default) --------------------------
def test_pending_suggestion_starts_in_cleartext(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert "Jane" not in window._scrubbed_text  # declared removed
    assert "Acme" in window._scrubbed_text  # suggestion held
    assert "acme" in window._suggestion_buttons


def test_approving_a_suggestion_removes_it_and_persists(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._suggestion_buttons["acme"][0].click()  # Approve

    assert "Acme" not in window._scrubbed_text
    assert "Acme" in window._sidecar.key.entries.values()

    reopened = _new_window(tmp_path, qtbot)
    assert "Acme" not in reopened._scrubbed_text  # persisted


def test_rejecting_a_suggestion_moves_to_cleartext_and_reapproves(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._suggestion_buttons["acme"][1].click()  # Reject

    assert "Acme" in window._scrubbed_text  # kept in cleartext
    assert window._group_cleartext.childCount() == 1
    cleartext_row = window._group_cleartext.child(0)
    assert "Acme" in cleartext_row.text(0)
    assert cleartext_row.font(0).strikeOut()

    window._reapprove_buttons["acme"].click()  # Remove after all
    assert "Acme" not in window._scrubbed_text


def test_keep_action_rejects_guaranteed_row_and_is_keyboard_bound(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert not window._keep_action.shortcut().isEmpty()  # not mouse-only

    window._tree.setCurrentItem(window._group_removed.child(0))  # the Jane row
    window._keep_action.trigger()

    assert "Jane" in window._scrubbed_text  # kept in cleartext
    assert window._sidecar.key.entries == {}  # dropped from the key
    assert window._group_cleartext.childCount() == 1


def test_approve_everything_detected(tmp_path, qtbot):
    _write_with_suggestion(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._approve_all_button.click()

    assert "Jane" not in window._scrubbed_text
    assert "Acme" not in window._scrubbed_text


# --- empty-state scan evidence (US8) ----------------------------------------
def test_empty_result_shows_scan_evidence(tmp_path, qtbot):
    _write_empty(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert window._review_body.currentIndex() == 1  # the "proof it ran" panel
    assert "NOTHING SENSITIVE FOUND" in window._spine_label.text()
    evidence = window._empty_evidence.text()
    assert "Scanned 7 detectors across 1 segments" in evidence


# --- PG7: unsafe withholds the scrubbed text from every copy path -----------
def test_unsafe_withholds_scrubbed_and_blocks_every_copy_path(tmp_path, qtbot):
    sanitization = _write_unsafe(tmp_path)
    scrubbed = sanitization.scrubbed_text
    assert scrubbed  # sanity: there is something that must be withheld
    window = _new_window(tmp_path, qtbot)

    # Loud, blocking, worded (Review mode is active by default).
    assert window._review_block.isVisibleTo(window)
    assert "UNSAFE" in window._spine_label.text()

    # 1) The scrubbed text is in no selectable/copyable widget (any mode).
    assert all(scrubbed not in text for text in _selectable_texts(window))

    # 2) No reachable copy path: the handler is a hard no-op, even called direct.
    clipboard = QApplication.clipboard()
    clipboard.setText("SENTINEL-UNCHANGED")
    window._copy_scrubbed()
    assert clipboard.text() == "SENTINEL-UNCHANGED"

    # 3) Send-out shows the wall, not the copy area.
    window.set_mode("sendout")
    assert window._sendout_wall.isVisibleTo(window)
    assert not window._sendout_safe.isVisibleTo(window)
    assert not window._copy_button.isEnabled()


def test_context_is_withheld_when_unsafe(tmp_path, qtbot):
    _write_unsafe(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._tree.setCurrentItem(window._group_removed.child(0))
    assert window._ctx_withheld.isVisibleTo(window)
    assert not window._ctx_body.isVisibleTo(window)


# --- miss-catching + select-to-redact (UX-3 / FR-16) ------------------------
def test_miss_strip_surfaces_unflagged_names(tmp_path, qtbot):
    _write_with_miss(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert window._miss_strip.isVisibleTo(window)
    labels = [b.text() for b in _miss_buttons(window)]
    assert any("Karen" in label for label in labels)


def test_redacting_a_miss_removes_it_everywhere_and_records_term(tmp_path, qtbot):
    _write_with_miss(tmp_path)
    window = _new_window(tmp_path, qtbot)

    button = next(b for b in _miss_buttons(window) if "Karen" in b.text())
    button.click()

    assert "Karen" not in window._scrubbed_text  # removed everywhere
    assert "Karen" in {i.original for i in window._sidecar.items}  # now a decision
    assert window._sidecar.meta["manual_terms"] == ["Karen"]  # add-to-list recorded
    assert all(
        "Karen" not in b.text() for b in _miss_buttons(window)
    )  # no longer offered


def test_context_redact_uses_the_selection(tmp_path, qtbot):
    _write_with_miss(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._ctx_orig.setPlainText("Karen")
    window._ctx_orig.selectAll()
    window._ctx_redact_button.click()

    assert "Karen" not in window._scrubbed_text


# --- UX-5: tier + state readable without colour -----------------------------
def test_zone_headers_and_state_read_without_colour(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert "REMOVED" in window._group_removed.text(0)
    assert "SUGGESTIONS" in window._group_suggestions.text(0)
    assert "Keeping in cleartext" in window._group_cleartext.text(0)

    window._tree.setCurrentItem(window._group_removed.child(0))
    window._keep_action.trigger()
    assert window._group_cleartext.child(0).font(0).strikeOut()
