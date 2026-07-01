"""Sidecar-backed review & restore window — Step A of the v2 UX build.

The home surface is the **decision list**, not a scrubbed-text blob: a two-zone
``QTreeWidget`` —

* **▣ REMOVED — guaranteed** (declared + PII together, provenance per row); these
  are pre-approved, so they carry no per-row buttons (FR-8);
* **◇ SUGGESTIONS** (model guesses, held): Approve/Reject buttons per row, never
  auto-applied (FR-9);
* **▸ Keeping in cleartext** (rejected items, struck through, collapsed): one-click
  re-approve (UX-9).

A guaranteed row is rejected via a keyboard-accessible **Keep in cleartext** action
(context menu + shortcut) — the full visible affordance arrives with the Step-B
detail pane. A single **Approve everything detected** action approves the lot.

Safety: a persistent **spine** shows the verdict in word + glyph, never colour alone
(UX-5). When ``meta["clean"]`` is false the scrubbed text is **withheld** — never
rendered into any selectable/copyable widget — and a loud blocking wall replaces it;
copy is a hard no-op (PG7/US9). The **key** is fenced as the secret and copying it
warns (PG8/UX-6). Edits re-derive scrubbed + key (``apply_review``) and persist to
the sidecar. The stored Buzz transcript is never touched.

Deferred to Step B/C: mode tabs (Send out / Restore split out), master-detail
context pane, the miss-catching strip, the empty-state "proof it ran" panel.
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QFontDatabase, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cloak_core import (
    DecisionState,
    TrustTier,
    apply_review,
    next_free_placeholder,
    persistence,
    restore,
)
from cloak_host.i18n import gettext as _

logger = logging.getLogger(__name__)

_GUARANTEED = (TrustTier.DECLARED, TrustTier.PII)
_USER_ROLE = Qt.ItemDataRole.UserRole

# Minimal, grayscale-first accents (from the design tokens). Meaning is carried by
# words + glyphs + grouping; colour only reinforces (UX-5).
_SAFE = "background:#e9f1ea; color:#2f6b3d; padding:8px; border-left:7px solid #2f6b3d;"
_EMPTY = (
    "background:#eaf0f2; color:#4a6b7a; padding:8px; border-left:7px solid #4a6b7a;"
)
_UNSAFE = (
    "background:#2a1414; color:#ffe6e1; padding:10px; "
    "border:2px solid #b3261e; font-weight:bold;"
)
_WALL = (
    "background:#2a1414; color:#ffe6e1; padding:20px; "
    "border:2px solid #b3261e; font-weight:bold;"
)
_KEY_HEADER = "background:#2a1414; color:#ffe6e1; padding:8px; font-weight:bold;"
_TOAST = "background:#26241f; color:#f4f2ee; padding:8px 14px; border:1px solid #000;"


class ReviewWindow(QWidget):
    """Presents and edits one transcription's sidecar: decisions, scrubbed, key.

    ``base_dir`` defaults to Cloak's real data directory; tests inject a temp dir.
    """

    def __init__(self, base_dir: str | None = None, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("cloak_review_window")
        self.setWindowTitle(_("Cloak — Review & restore"))
        self.resize(880, 860)

        if base_dir is None:
            try:
                from cloak_host.paths import cloak_data_dir

                base_dir = cloak_data_dir()
            except Exception:  # noqa: BLE001 - platformdirs absent → empty state
                logger.debug("Cloak: data dir unavailable; review opens empty.")
                base_dir = ""
        self._base_dir = base_dir
        self._sidecar = None
        self._current_dir = ""
        self._key_text = ""
        self._clean = True
        self._last_toast = ""
        self._toast_label: QLabel | None = None
        self._suggestion_buttons: dict[str, tuple[QPushButton, QPushButton]] = {}
        self._reapprove_buttons: dict[str, QPushButton] = {}
        self._mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)

        # Keyboard-accessible reject for guaranteed rows (no per-row button; the
        # visible affordance arrives with the Step-B detail pane). Surfaced in the
        # tree's context menu AND bound to a shortcut — never mouse-only.
        self._keep_action = QAction(_("Keep in cleartext"), self)
        self._keep_action.setShortcut(QKeySequence("Ctrl+K"))
        self._keep_action.triggered.connect(self._keep_selected_in_cleartext)

        layout = QVBoxLayout(self)

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel(_("Transcription:")))
        self._selector = QComboBox()
        self._selector.currentIndexChanged.connect(self._on_select)
        selector_row.addWidget(self._selector, 1)
        self._refresh_button = QPushButton(_("Refresh"))
        self._refresh_button.clicked.connect(self.reload)
        selector_row.addWidget(self._refresh_button)
        layout.addLayout(selector_row)

        # Safety spine — the verdict, always visible, word + glyph (UX-5 / PG7).
        self._spine_label = QLabel()
        self._spine_label.setWordWrap(True)
        layout.addWidget(self._spine_label)

        # Decisions — the home surface (UX-1). Gets the vertical stretch.
        decisions_box = QGroupBox(_("Decisions — what Cloak will remove"))
        decisions_layout = QVBoxLayout(decisions_box)
        bulk_row = QHBoxLayout()
        self._approve_all_button = QPushButton(_("Approve everything detected"))
        self._approve_all_button.clicked.connect(self._approve_everything)
        bulk_row.addWidget(self._approve_all_button)
        bulk_row.addStretch(1)
        decisions_layout.addLayout(bulk_row)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels([_("item"), _("was"), _("×"), _("provenance")])
        self._tree.setRootIsDecorated(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self._tree.addAction(self._keep_action)
        self._tree.itemSelectionChanged.connect(self._update_row_actions)
        decisions_layout.addWidget(self._tree, 1)
        layout.addWidget(decisions_box, 1)

        # Scrubbed transcript (safe only) OR the withholding wall (unsafe).
        self._scrubbed_group = QGroupBox(
            _("Scrubbed transcript (safe to paste into an LLM)")
        )
        scrubbed_layout = QVBoxLayout(self._scrubbed_group)
        self._scrubbed_edit = self._read_only(110)
        scrubbed_layout.addWidget(self._scrubbed_edit)
        self._copy_button = QPushButton(_("📋  Copy scrubbed text"))
        self._copy_button.clicked.connect(self._copy_scrubbed)
        scrubbed_layout.addWidget(self._copy_button)
        layout.addWidget(self._scrubbed_group)

        self._unsafe_wall = QLabel(
            _(
                "⛔  OUTPUT WITHHELD\n\nA declared item could not be confirmed "
                "removed. No scrubbed text is produced until this is resolved."
            )
        )
        self._unsafe_wall.setWordWrap(True)
        self._unsafe_wall.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._unsafe_wall.setStyleSheet(_WALL)
        self._unsafe_wall.setVisible(False)
        layout.addWidget(self._unsafe_wall)

        # The key — fenced as the secret (PG8 / UX-6).
        key_box = QGroupBox(_("The key"))
        key_layout = QVBoxLayout(key_box)
        key_header = QLabel(
            _("🔒  THE KEY — this is the secret.  Never paste this into an LLM.")
        )
        key_header.setWordWrap(True)
        key_header.setStyleSheet(_KEY_HEADER)
        key_layout.addWidget(key_header)
        key_layout.addWidget(
            QLabel(
                _(
                    "The key maps placeholders back to real values. You only need "
                    "it to restore a reply."
                )
            )
        )
        self._reveal_button = QPushButton(_("Reveal key"))
        self._reveal_button.setCheckable(True)
        self._reveal_button.toggled.connect(self._on_reveal_toggled)
        key_layout.addWidget(self._reveal_button, 0, Qt.AlignmentFlag.AlignLeft)
        self._key_edit = self._read_only(90)
        self._key_edit.setVisible(False)
        key_layout.addWidget(self._key_edit)
        self._copy_key_button = QPushButton(_("⚠  Copy the secret key"))
        self._copy_key_button.setVisible(False)
        self._copy_key_button.clicked.connect(self._copy_key)
        key_layout.addWidget(self._copy_key_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(key_box)

        # Restore (unchanged from Phase 5).
        restore_box = QGroupBox(_("Restore a returned reply"))
        restore_layout = QVBoxLayout(restore_box)
        restore_layout.addWidget(QLabel(_("Paste the LLM's reply (markdown is fine):")))
        self._returned_edit = QPlainTextEdit()
        self._returned_edit.setFixedHeight(70)
        restore_layout.addWidget(self._returned_edit)
        self._restore_button = QPushButton(_("Restore originals"))
        self._restore_button.clicked.connect(self._on_restore)
        restore_layout.addWidget(self._restore_button)
        self._restored_edit = self._read_only(70)
        restore_layout.addWidget(self._restored_edit)
        layout.addWidget(restore_box)

        self.reload()

    @staticmethod
    def _read_only(height: int | None = None) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        if height:
            edit.setFixedHeight(height)
        return edit

    # --- loading ------------------------------------------------------------
    def reload(self) -> None:
        """Re-scan the data directory and load the most recent transcription."""
        ids = persistence.list_sidecars(self._base_dir) if self._base_dir else []
        self._selector.blockSignals(True)
        self._selector.clear()
        for transcription_id in ids:
            self._selector.addItem(transcription_id, transcription_id)
        self._selector.blockSignals(False)
        if ids:
            self._selector.setCurrentIndex(0)
            self._load(ids[0])
        else:
            self._show_empty()

    def _on_select(self, index: int) -> None:
        transcription_id = self._selector.itemData(index)
        if transcription_id is not None:
            self._load(transcription_id)

    def _load(self, transcription_id) -> None:
        directory = os.path.join(self._base_dir, str(transcription_id))
        sidecar = persistence.read_sidecar(directory)
        self._sidecar = sidecar
        self._current_dir = directory
        if sidecar is None:
            self._show_empty()
            return
        self._refresh_after_edit()

    def _show_empty(self) -> None:
        self._sidecar = None
        self._current_dir = ""
        self._key_text = ""
        self._clean = True
        self._populate_tree([])
        self._scrubbed_edit.setPlainText("")
        self._scrubbed_group.setVisible(True)
        self._copy_button.setEnabled(False)
        self._unsafe_wall.setVisible(False)
        self._key_edit.setPlainText("")
        self._spine_label.setText(
            _("No sanitized transcripts yet. Transcribe with Cloak enabled.")
        )
        self._spine_label.setStyleSheet(_EMPTY)

    # --- rendering ----------------------------------------------------------
    def _refresh_after_edit(self) -> None:
        """Re-render every pane from the current sidecar state."""
        sidecar = self._sidecar
        if sidecar is None:
            return
        clean = bool(sidecar.meta.get("clean", True))
        self._clean = clean

        self._populate_tree(sidecar.items)
        self._update_spine(sidecar, clean)

        if clean:
            self._unsafe_wall.setVisible(False)
            self._scrubbed_group.setVisible(True)
            self._scrubbed_edit.setPlainText(sidecar.scrubbed_text)
            self._copy_button.setEnabled(True)
        else:
            # WITHHOLD (PG7): the scrubbed text must not reach any selectable
            # widget, and there must be no reachable copy path (see _copy_scrubbed).
            self._scrubbed_edit.setPlainText("")
            self._scrubbed_group.setVisible(False)
            self._copy_button.setEnabled(False)
            self._unsafe_wall.setVisible(True)

        self._key_text = "\n".join(
            f"{placeholder}  =  {original}"
            for placeholder, original in sidecar.key.entries.items()
        )
        if self._reveal_button.isChecked():
            self._key_edit.setPlainText(self._key_text or _("(empty)"))

    def _update_spine(self, sidecar, clean: bool) -> None:
        removed = sum(1 for i in sidecar.items if i.state == DecisionState.APPROVED)
        pending = sum(1 for i in sidecar.items if i.state == DecisionState.PENDING)
        if not clean:
            self._spine_label.setText(
                _(
                    "⛔  BLOCKED — UNSAFE — could not confirm your declared items "
                    "were removed"
                )
            )
            self._spine_label.setStyleSheet(_UNSAFE)
        elif not sidecar.items:
            self._spine_label.setText(
                _("✔  NOTHING SENSITIVE FOUND in this transcript")
            )
            self._spine_label.setStyleSheet(_EMPTY)
        else:
            self._spine_label.setText(
                _(
                    "✔  SAFE TO COPY · {removed} removed · {pending} suggestions "
                    "awaiting you"
                ).format(removed=removed, pending=pending)
            )
            self._spine_label.setStyleSheet(_SAFE)

    def _populate_tree(self, items) -> None:
        self._tree.clear()
        self._suggestion_buttons = {}
        self._reapprove_buttons = {}

        removed = [
            i
            for i in items
            if i.tier in _GUARANTEED and i.state == DecisionState.APPROVED
        ]
        suggestions = [
            i
            for i in items
            if i.tier == TrustTier.SUGGESTED and i.state != DecisionState.REJECTED
        ]
        rejected = [i for i in items if i.state == DecisionState.REJECTED]

        self._group_removed = self._add_group(
            "▣  " + _("REMOVED — guaranteed  ·  declared + detected, verified"),
            bold=True,
        )
        for item in removed:
            self._add_removed_row(item)

        self._group_suggestions = self._add_group(
            "◇  "
            + _(
                "SUGGESTIONS — model's guesses, your call  (nothing here is removed "
                "until you approve it)"
            ),
            bold=True,
            italic=True,
        )
        for item in suggestions:
            self._add_suggestion_row(item)

        self._group_cleartext = self._add_group(
            "▸  " + _("Keeping in cleartext") + f" ({len(rejected)})"
        )
        for item in rejected:
            self._add_cleartext_row(item)

        self._group_removed.setExpanded(True)
        self._group_suggestions.setExpanded(True)
        self._group_cleartext.setExpanded(False)
        self._apply_tree_widths()
        self._update_row_actions()

    def _add_group(
        self, text: str, *, bold: bool = False, italic: bool = False
    ) -> QTreeWidgetItem:
        group = QTreeWidgetItem([text])
        self._tree.addTopLevelItem(group)
        group.setFirstColumnSpanned(True)  # must follow addTopLevelItem
        font = group.font(0)
        font.setBold(bold)
        font.setItalic(italic)
        group.setFont(0, font)
        return group

    def _add_removed_row(self, item) -> None:
        row = QTreeWidgetItem(
            [
                "  " + item.placeholder,
                _("was: {}").format(item.original),
                f"{item.count}×",
                self._provenance(item),
            ]
        )
        row.setFont(0, self._mono)
        row.setData(0, _USER_ROLE, item)
        self._group_removed.addChild(row)

    def _add_suggestion_row(self, item) -> None:
        row = QTreeWidgetItem(["    " + item.original, item.type, f"{item.count}×", ""])
        row.setData(0, _USER_ROLE, item)
        self._group_suggestions.addChild(row)
        if item.state == DecisionState.PENDING:
            holder = QWidget()
            box = QHBoxLayout(holder)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(4)
            approve = QPushButton(_("Approve"))
            reject = QPushButton(_("Reject"))
            approve.clicked.connect(lambda _c=False, it=item: self._approve_item(it))
            reject.clicked.connect(lambda _c=False, it=item: self._reject_item(it))
            box.addWidget(approve)
            box.addWidget(reject)
            self._tree.setItemWidget(row, 3, holder)
            self._suggestion_buttons[item.canonical] = (approve, reject)
        else:  # an approved suggestion — decided, no buttons
            row.setText(3, _("approved · removed"))
            font = row.font(3)
            font.setItalic(True)
            row.setFont(3, font)

    def _add_cleartext_row(self, item) -> None:
        row = QTreeWidgetItem(["    " + item.original, item.type, f"{item.count}×", ""])
        font = row.font(0)
        font.setStrikeOut(True)
        row.setFont(0, font)
        row.setData(0, _USER_ROLE, item)
        self._group_cleartext.addChild(row)
        button = QPushButton(_("Remove after all"))
        button.clicked.connect(lambda _c=False, it=item: self._reapprove_item(it))
        self._tree.setItemWidget(row, 3, button)
        self._reapprove_buttons[item.canonical] = button

    @staticmethod
    def _provenance(item) -> str:
        return _("your list") if item.tier == TrustTier.DECLARED else item.type

    def _apply_tree_widths(self) -> None:
        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setDefaultSectionSize(138)
        header.resizeSection(0, 190)
        header.resizeSection(1, 150)
        header.resizeSection(2, 44)

    # --- editing ------------------------------------------------------------
    def _approve_item(self, item) -> None:
        self._set_item_approved(item, True)
        self._apply_edits()

    def _reject_item(self, item) -> None:
        self._set_item_approved(item, False)
        self._apply_edits()

    def _reapprove_item(self, item) -> None:
        self._set_item_approved(item, True)
        self._apply_edits()

    def _approve_everything(self) -> None:
        if self._sidecar is None:
            return
        for item in self._sidecar.items:
            self._set_item_approved(item, True)
        self._apply_edits()

    def _keep_selected_in_cleartext(self) -> None:
        item = self._selected_review_item()
        if item is not None and item.state != DecisionState.REJECTED:
            self._reject_item(item)

    def _selected_review_item(self):
        selected = self._tree.selectedItems()
        if not selected:
            return None
        return selected[0].data(0, _USER_ROLE)

    def _update_row_actions(self) -> None:
        item = self._selected_review_item()
        self._keep_action.setEnabled(
            item is not None and item.state != DecisionState.REJECTED
        )

    def _set_item_approved(self, item, approved: bool) -> None:
        if approved:
            item.state = DecisionState.APPROVED
            if not item.placeholder:
                existing = {i.placeholder for i in self._sidecar.items if i.placeholder}
                item.placeholder = next_free_placeholder(existing, item.label)
        else:
            item.state = DecisionState.REJECTED

    def _apply_edits(self) -> None:
        """Re-derive scrubbed + key from the item states, refresh, and persist."""
        sidecar = self._sidecar
        segments, key = apply_review(sidecar.segments, sidecar.items)
        sidecar.segments = segments
        sidecar.key = key
        self._refresh_after_edit()
        self._persist()

    def _persist(self) -> None:
        if not self._current_dir or self._sidecar is None:
            return
        sidecar = self._sidecar
        sidecar.meta["removed_items"] = sum(
            1 for i in sidecar.items if i.state == DecisionState.APPROVED
        )
        sidecar.meta["pending_items"] = sum(
            1 for i in sidecar.items if i.state == DecisionState.PENDING
        )
        try:
            persistence.write_sidecar(self._current_dir, sidecar, sidecar.meta)
        except OSError:
            logger.exception("Cloak: failed to persist review edits.")

    # --- key / restore / clipboard ------------------------------------------
    def _on_reveal_toggled(self, checked: bool) -> None:
        self._key_edit.setVisible(checked)
        self._copy_key_button.setVisible(checked)
        self._reveal_button.setText(_("Hide key") if checked else _("Reveal key"))
        if checked:
            self._key_edit.setPlainText(self._key_text or _("(empty)"))

    def _on_restore(self) -> None:
        if self._sidecar is None:
            return
        restored = restore(self._returned_edit.toPlainText(), self._sidecar.key)
        self._restored_edit.setPlainText(restored)

    def _copy_scrubbed(self) -> None:
        # PG7: while unsafe there is NO reachable copy path — the handler refuses
        # even if invoked directly, and the text isn't in a widget to begin with.
        if not self._clean:
            return
        text = self._scrubbed_edit.toPlainText()
        if not text:
            return
        self._to_clipboard(text)
        self._toast(_("✔  Scrubbed text copied — safe to paste"))

    def _copy_key(self) -> None:
        if not self._key_text:
            return
        self._to_clipboard(self._key_text)
        self._toast(_("⚠  Secret key copied — never paste this into an LLM"))

    @staticmethod
    def _to_clipboard(text: str) -> None:
        app = QApplication.instance()
        if app is None or not text:
            return
        clipboard = app.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    # --- toast --------------------------------------------------------------
    def _toast(self, message: str) -> None:
        self._last_toast = message
        if self._toast_label is None:
            label = QLabel(self)
            label.setStyleSheet(_TOAST)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._toast_label = label
        label = self._toast_label
        label.setText(message)
        label.adjustSize()
        label.move(
            max(0, (self.width() - label.width()) // 2),
            max(0, self.height() - label.height() - 24),
        )
        label.show()
        label.raise_()
        QTimer.singleShot(2400, label.hide)
