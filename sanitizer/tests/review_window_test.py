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

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
)

_USER_ROLE = Qt.ItemDataRole.UserRole

from sanitizer_core import (  # noqa: E402
    persistence,
    read_declared_terms,
    read_preferences,
)
from sanitizer_core.detectors.declared import DeclaredListDetector  # noqa: E402
from sanitizer_core.detectors.suggest import (  # noqa: E402
    ModelSuggestionDetector,
    RawEntity,
)
from sanitizer_core.transcript import sanitize_transcript  # noqa: E402


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


def _write_two_terms(directory):
    # Two distinct declared rows, so a filter has something to narrow.
    sanitization = sanitize_transcript(
        [Seg(0, 1, "Call Jane and Bob")], [DeclaredListDetector(["Jane", "Bob"])]
    )
    persistence.write_sidecar(directory / "8", sanitization, _meta(sanitization))
    return sanitization


def _miss_buttons(window):
    from PyQt6.QtWidgets import QPushButton

    return window._miss_container.findChildren(QPushButton)


def _suggestion_rows(window):
    """Every leaf suggestion row across the per-type subgroups (grouped triage view)."""
    group = window._group_suggestions
    rows = []
    for i in range(group.childCount()):
        subgroup = group.child(i)
        for j in range(subgroup.childCount()):
            rows.append(subgroup.child(j))
    return rows


def _find_suggestion_row(window, needle):
    for row in _suggestion_rows(window):
        if needle in row.text(0):
            return row
    return None


def _subgroup_rows(window, label):
    """The ordered leaf rows under the named type subgroup (e.g. 'People')."""
    group = window._group_suggestions
    for i in range(group.childCount()):
        subgroup = group.child(i)
        if label in subgroup.text(0):
            return [subgroup.child(j) for j in range(subgroup.childCount())]
    return []


def _new_window(tmp_path, qtbot):
    from sanitizer_host.review_window import ReviewWindow

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

    # Acme is the sole suggestion row (now nested under its 'Organizations' subgroup).
    window._tree.setCurrentItem(_find_suggestion_row(window, "Acme"))

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


# --- Step D: first-use key teaching (US6) -----------------------------------
def test_first_use_key_note_shows_then_dismisses_and_persists(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)
    window.set_mode("sendout")

    assert window._key_note.isVisibleTo(window)  # shown the first time
    window._key_note_dismiss.click()
    assert not window._key_note.isVisibleTo(window)
    assert read_preferences(tmp_path).key_note_dismissed is True  # persisted

    reopened = _new_window(tmp_path, qtbot)
    reopened.set_mode("sendout")
    assert not reopened._key_note.isVisibleTo(reopened)  # never again


# --- Step D: informed auto-apply (FR-12) ------------------------------------
def test_auto_apply_offer_hidden_until_a_review_then_persists(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)

    # Never reviewed → the offer is not shown (the informed gate).
    assert not window._prefs.has_reviewed
    assert not window._auto_apply_check.isVisibleTo(window)

    window._approve_all_button.click()  # a decision edit → counts as a review

    assert window._prefs.has_reviewed is True
    assert read_preferences(tmp_path).has_reviewed is True  # persisted
    assert window._auto_apply_check.isVisibleTo(window)  # now offered

    reopened = _new_window(tmp_path, qtbot)
    assert reopened._auto_apply_check.isVisibleTo(reopened)  # stays offered


def test_toggling_auto_apply_persists_the_preference(tmp_path, qtbot):
    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)
    window._approve_all_button.click()  # unlock the offer

    window._auto_apply_check.setChecked(True)

    assert read_preferences(tmp_path).auto_apply_suggestions is True
    reopened = _new_window(tmp_path, qtbot)
    assert reopened._auto_apply_check.isChecked()  # reflects the saved choice


# --- Step D: in-window declared-list editing (US2) --------------------------
def test_declared_list_editor_adds_and_removes(tmp_path, qtbot):
    from sanitizer_host.review_window import _DeclaredListEditor

    editor = _DeclaredListEditor(str(tmp_path))
    qtbot.addWidget(editor)

    editor._input.setText("person: Jane")
    editor._add()
    assert read_declared_terms(tmp_path) == ["person: Jane"]
    assert editor._list.count() == 1

    editor._list.setCurrentRow(0)
    editor._remove()
    assert read_declared_terms(tmp_path) == []
    assert editor._list.count() == 0


def test_add_to_list_promotes_the_term_to_the_declared_store(tmp_path, qtbot):
    _write_with_miss(tmp_path)
    window = _new_window(tmp_path, qtbot)

    button = next(b for b in _miss_buttons(window) if "Karen" in b.text())
    button.click()  # miss-strip redact uses add=True

    # US2: it is now a real cross-transcript declared term, not only a meta note.
    assert "Karen" in read_declared_terms(tmp_path)


# --- Step D: scale — filter the decision tree -------------------------------
def test_filter_narrows_the_decision_rows(tmp_path, qtbot):
    _write_two_terms(tmp_path)
    window = _new_window(tmp_path, qtbot)
    assert window._group_removed.childCount() == 2

    window._filter_edit.setText("jane")

    rows = [window._group_removed.child(i) for i in range(2)]
    shown = [r for r in rows if not r.isHidden()]
    assert len(shown) == 1
    assert "Jane" in shown[0].text(1)  # the "was: Jane" row survives the filter


def test_clearing_the_filter_restores_all_rows(tmp_path, qtbot):
    _write_two_terms(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._filter_edit.setText("jane")
    window._filter_edit.setText("")

    assert all(not window._group_removed.child(i).isHidden() for i in range(2))


# --- on-demand "Run suggestions" (worker thread) ----------------------------
def _write_plain(directory):
    # Nothing declared → clean, zero items; undeclared names for the model to find.
    sanitization = sanitize_transcript(
        [Seg(0, 1, "Call Sarah Chen"), Seg(1, 2, "about the Acme deal")],
        [DeclaredListDetector(["Zzz"])],
    )
    persistence.write_sidecar(directory / "p", sanitization, _meta(sanitization))
    return sanitization


class _BoomProvider:
    """A provider whose model always fails — to prove failure is surfaced, not empty."""

    def model_present(self):
        return True

    def predict(self, text, labels):
        raise RuntimeError("model exploded")


def test_suggest_button_disabled_without_a_transcript(tmp_path, qtbot):
    window = _new_window(tmp_path, qtbot)  # empty dir, nothing loaded
    assert not window._suggest_button.isEnabled()


def test_run_suggestions_adds_pending_items(tmp_path, qtbot):
    _write_plain(tmp_path)
    window = _new_window(tmp_path, qtbot)
    window._provider_factory = lambda: _StubProvider("Sarah Chen", "person")

    window._suggest_button.click()
    qtbot.waitUntil(
        lambda: _find_suggestion_row(window, "Sarah Chen") is not None, timeout=5000
    )

    row = _find_suggestion_row(window, "Sarah Chen")
    assert "Sarah Chen" in row.text(0)
    assert "sarah chen" in window._suggestion_buttons  # Approve/Reject offered
    assert "Sarah Chen" in window._scrubbed_text  # held PENDING (FR-9), not removed


def test_run_suggestions_surfaces_failure_instead_of_a_false_empty(tmp_path, qtbot):
    _write_plain(tmp_path)
    window = _new_window(tmp_path, qtbot)
    window._provider_factory = lambda: _BoomProvider()

    window._suggest_button.click()
    qtbot.waitUntil(lambda: "exploded" in window._suggest_status.text(), timeout=5000)

    # A broken model reads as "Unavailable — <reason>", never as "found nothing".
    assert "Unavailable" in window._suggest_status.text()
    assert window._group_suggestions.childCount() == 0
    assert window._suggest_button.isEnabled()  # re-enabled after the run


def test_run_suggestions_auto_applies_when_opted_in(tmp_path, qtbot):
    from sanitizer_core import Preferences, write_preferences

    write_preferences(
        tmp_path, Preferences(has_reviewed=True, auto_apply_suggestions=True)
    )
    _write_plain(tmp_path)
    window = _new_window(tmp_path, qtbot)
    window._provider_factory = lambda: _StubProvider("Sarah Chen", "person")

    window._suggest_button.click()
    qtbot.waitUntil(lambda: "Sarah Chen" not in window._scrubbed_text, timeout=5000)

    # Opted in after a review → the found suggestion is auto-approved and removed.
    assert "Sarah Chen" in window._sidecar.key.entries.values()


# --- live suggestion triage (the ~222-item problem) -------------------------
class _ScoredProvider:
    """Finds each ``(surface, label, score)`` everywhere it appears — a richer stub
    than _StubProvider, for exercising the confidence / type / mention filters."""

    def __init__(self, *specs):
        self._specs = specs

    def predict(self, text, labels):
        out = []
        for surface, label, score in self._specs:
            start = text.find(surface)
            while start >= 0:
                out.append(RawEntity(start, start + len(surface), label, score))
                start = text.find(surface, start + len(surface))
        return out


def _write_scored_suggestions(directory):
    """A sidecar carrying four undeclared suggestions of varied score / type / count:
    Alice (person, 0.92, ×2), Bob (person, 0.40, ×1), Carol (person, 0.80, ×1),
    Globex (org, 0.60, ×1). Built through the real ``suggest_items`` so scores flow."""
    from sanitizer_core.transcript import suggest_items

    base = sanitize_transcript(
        [Seg(0, 1, "Alice met Alice and Bob"), Seg(1, 2, "then Carol at Globex")],
        [DeclaredListDetector(["Zzz"])],
    )
    detector = ModelSuggestionDetector(
        _ScoredProvider(
            ("Alice", "person", 0.92),
            ("Bob", "person", 0.40),
            ("Carol", "person", 0.80),
            ("Globex", "organization", 0.60),
        ),
        threshold=0.3,
    )
    base.items.extend(suggest_items(base.segments, detector, known_canonicals=set()))
    persistence.write_sidecar(directory / "sc", base, _meta(base))
    return base


def _pending_names(window):
    from sanitizer_core import DecisionState

    names = set()
    for row in _suggestion_rows(window):
        item = row.data(0, _USER_ROLE)
        if item is not None and item.state == DecisionState.PENDING:
            names.add(item.original)
    return names


def test_triage_controls_visible_with_a_live_count(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    assert window._sugg_controls.isVisibleTo(window)
    # Default confidence 50% hides Bob (0.40); Alice/Carol/Globex remain.
    assert "3 of 4" in window._sugg_count_label.text()
    assert _pending_names(window) == {"Alice", "Carol", "Globex"}


def test_confidence_slider_narrows_the_shown_set(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._confidence_slider.setValue(85)  # only Alice (0.92) clears the bar

    assert _pending_names(window) == {"Alice"}
    assert "1 of 4" in window._sugg_count_label.text()

    window._confidence_slider.setValue(30)  # everything down to the floor
    assert _pending_names(window) == {"Alice", "Bob", "Carol", "Globex"}
    assert "4 of 4" in window._sugg_count_label.text()


def test_type_toggle_hides_a_whole_category(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._type_checks["person"].setChecked(False)

    assert _pending_names(window) == {"Globex"}  # only the org survives


def test_min_mentions_floor_filters_rare_single_hits(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._min_mentions_spin.setValue(2)  # only Alice appears twice

    assert _pending_names(window) == {"Alice"}


def test_sort_by_rarity_puts_the_rarely_named_first(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)
    window._confidence_slider.setValue(30)  # show all People (Alice×2, Bob, Carol)

    # Confidence (default): highest score first → Alice leads.
    people = [r.text(0).strip() for r in _subgroup_rows(window, "People")]
    assert people[0] == "Alice"

    # Rarity: count-ascending → the single-mention names lead, Alice (×2) last.
    window._sort_combo.setCurrentIndex(1)
    people = [r.text(0).strip() for r in _subgroup_rows(window, "People")]
    assert people[-1] == "Alice"
    assert set(people[:2]) == {"Bob", "Carol"}


def test_approve_all_shown_leaves_filtered_out_items_untouched(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)  # default: Bob (0.40) is filtered out

    window._approve_shown_button.click()

    for approved in ("Alice", "Carol", "Globex"):
        assert approved not in window._scrubbed_text  # removed
    assert "Bob" in window._scrubbed_text  # below the floor → never approved


def test_reject_all_shown_moves_them_to_cleartext(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._reject_shown_button.click()

    # The three shown suggestions are kept in cleartext; hidden Bob stays pending.
    assert window._group_cleartext.childCount() == 3
    assert _pending_names(window) == set()  # none shown pending remain


def test_multiselect_then_keyboard_action_approves_the_selection(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    _find_suggestion_row(window, "Alice").setSelected(True)
    _find_suggestion_row(window, "Carol").setSelected(True)
    window._approve_sel_action.trigger()  # the Ctrl+Return path, minus the keypress

    assert "Alice" not in window._scrubbed_text
    assert "Carol" not in window._scrubbed_text
    assert "Globex" in window._scrubbed_text  # unselected → untouched


def test_per_type_bulk_reject_targets_only_that_type(tmp_path, qtbot):
    from PyQt6.QtWidgets import QPushButton

    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    # The 'Organizations' subgroup header carries its own Approve all / Reject all.
    group = window._group_suggestions
    org_header = next(
        group.child(i)
        for i in range(group.childCount())
        if "Organizations" in group.child(i).text(0)
    )
    holder = window._tree.itemWidget(org_header, 3)
    reject_all = next(
        b for b in holder.findChildren(QPushButton) if b.text() == "Reject all"
    )
    reject_all.click()

    assert "Globex" in window._scrubbed_text  # the org kept in cleartext
    assert _pending_names(window) == {"Alice", "Carol"}  # people untouched


def test_triage_filters_do_not_persist_or_mutate_the_sidecar(tmp_path, qtbot):
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._confidence_slider.setValue(95)  # a pure view change
    window._type_checks["org"].setChecked(False)

    # Filtering is a view, not an edit: every suggestion is still PENDING on disk.
    reopened = _new_window(tmp_path, qtbot)
    assert _pending_names(reopened) == {"Alice", "Carol", "Globex"}  # default view


def test_triage_controls_hidden_when_there_are_no_suggestions(tmp_path, qtbot):
    _write_sidecar(tmp_path)  # declared-only sidecar, zero suggestions
    window = _new_window(tmp_path, qtbot)

    assert not window._sugg_controls.isVisibleTo(window)
    assert window._group_suggestions.childCount() == 0


def test_approved_suggestion_stays_visible_when_its_type_is_toggled_off(
    tmp_path, qtbot
):
    # Approving a suggestion is a decision; toggling its type must not erase that
    # record (you'd lose the only in-tree evidence of what was removed).
    _write_scored_suggestions(tmp_path)
    window = _new_window(tmp_path, qtbot)

    window._suggestion_buttons["alice"][0].click()  # approve Alice (person)
    window._type_checks["person"].setChecked(False)  # focus away from people

    assert _find_suggestion_row(window, "Alice") is not None  # approved → still shown
    assert _find_suggestion_row(window, "Carol") is None  # pending person → hidden


def test_spine_cautions_when_a_guaranteed_item_is_kept_in_cleartext(tmp_path, qtbot):
    _write_sidecar(tmp_path)  # Jane declared + removed → clean
    window = _new_window(tmp_path, qtbot)
    assert "SAFE TO COPY" in window._spine_label.text()  # baseline

    window._tree.setCurrentItem(window._group_removed.child(0))  # the Jane row
    window._keep_action.trigger()  # override: keep the declared item in cleartext

    spine = window._spine_label.text()
    assert "kept in cleartext" in spine  # no longer a bare "SAFE TO COPY"
    assert "1" in spine
    window.set_mode("sendout")
    assert window._copy_button.isEnabled()  # still the user's choice to copy


def test_stale_suggestion_result_is_discarded_not_applied(tmp_path, qtbot):
    # A scan that started on transcript A must never land on transcript B if the user
    # switched in between (its placements index A's segments — applying corrupts B).
    from sanitizer_core import DecisionState, TrustTier
    from sanitizer_core.transcript import Placement, ReviewItem

    _write_sidecar(tmp_path)
    window = _new_window(tmp_path, qtbot)
    before = len(window._sidecar.items)
    window._suggest_source_dir = window._current_dir + "__other"  # simulate a switch

    ghost = ReviewItem(
        canonical="ghost",
        placeholder="",
        original="Ghost",
        label="PERSON",
        type="person",
        tier=TrustTier.SUGGESTED,
        reason="x",
        state=DecisionState.PENDING,
        placements=[Placement(0, 0, 5)],
    )
    window._on_suggestions_ready([ghost])

    assert len(window._sidecar.items) == before  # untouched
    assert _find_suggestion_row(window, "Ghost") is None
