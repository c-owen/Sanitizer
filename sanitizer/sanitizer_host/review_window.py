"""Sidecar-backed review window: the v2 UX build (Steps A-D).

**One window, three modes** (a persistent safety spine spans all three):

* **Review**: the home surface, a master-detail `QSplitter`. Left is the two-zone
  decision **tree** (▣ REMOVED guaranteed · ◇ SUGGESTIONS held w/ Approve/Reject ·
  ▸ Keeping-in-cleartext). Right is the **context / side-by-side** pane (UX-2): on
  row selection it shows the original in context vs the substitution ("Is removing
  *this* one correct?"), built from the item's ``placements``. In the empty case the
  split is replaced by a "proof it ran" panel with scan evidence (US8).
* **Send out**: one prominent *Copy scrubbed text* + a collapsed preview, then the
  **fenced key** (the secret, PG8/UX-6). Unsafe → a blocking wall, no copyable text.
* **Restore**: the mirror, paste reply → restore → result, with an **unresolved-tag
  report** (`⚠ N still unresolved`, FR-7).

Safety carries across all modes: the spine states the verdict in word+glyph (UX-5),
and when ``meta["clean"]`` is false the scrubbed text is **withheld** from every
selectable widget with no reachable copy path (PG7/US9). Edits re-derive scrubbed +
key (``apply_review``) and persist. The stored Buzz transcript is never touched.

Step D adds the polish that makes it teach and scale: the one-time "the key is the
secret" note in Send out (US6); an informed auto-apply offer that only appears once
the user has reviewed at least once (FR-12); in-window editing of the declared list,
so "add to my list" becomes a real cross-transcript term (US2); a filter over the
decision tree for the large-transcript case; and a grayscale-first stylesheet.
"""

from __future__ import annotations

import logging
import os
import re

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFontDatabase, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sanitizer_core import (
    DecisionState,
    Preferences,
    TrustTier,
    add_declared_term,
    apply_review,
    build_manual_item,
    find_miss_candidates,
    next_free_placeholder,
    persistence,
    read_declared_terms,
    read_preferences,
    remove_declared_term,
    restore,
    scan_safe_text,
    suggest_items,
    write_preferences,
)
from sanitizer_host.i18n import gettext as _

logger = logging.getLogger(__name__)

_GUARANTEED = (TrustTier.DECLARED, TrustTier.PII)
_USER_ROLE = Qt.ItemDataRole.UserRole
_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")
_MODE_INDEX = {"review": 0, "sendout": 1, "restore": 2}

# --- suggestion triage (the "run once, filter live" surface) ----------------
# The floor at which we ask the model once, so *all* candidates down to here are in
# hand and the confidence slider filters them client-side with no re-run. It matches
# the provider's own pre-filter floor; the slider default sits above it.
_SUGGESTION_FLOOR = 0.3
_SUGGESTION_MIN_DEFAULT = 0.5  # slider default (== the pre-triage detector cutoff)
# Suggestion categories in display order (``type`` value → human label). These are
# the four categories the model maps to (sanitizer_core.categories); the toggles filter
# the computed set by them.
_SUGGESTION_TYPES: tuple[tuple[str, str], ...] = (
    ("person", "People"),
    ("org", "Organizations"),
    ("place", "Places"),
    ("project", "Projects"),
)
# Sort keys offered for the pending suggestions (id → label). "Rarity" surfaces the
# rarely-named first: often the private individual in a sea of public figures.
_SUGGESTION_SORTS: tuple[tuple[str, str], ...] = (
    ("confidence", "Confidence (high → low)"),
    ("rarity", "Rarity (rare → common)"),
    ("alpha", "Name (A → Z)"),
)

# Minimal, grayscale-first accents (design tokens). Meaning is carried by words +
# glyphs + grouping; colour only reinforces (UX-5).
_SAFE = "background:#e9f1ea; color:#2f6b3d; padding:8px; border-left:7px solid #2f6b3d;"
_EMPTY = (
    "background:#eaf0f2; color:#4a6b7a; padding:8px; border-left:7px solid #4a6b7a;"
)
# Safe-but-note-this: the guaranteed path verified, yet the user has deliberately
# kept a declared/PII item in cleartext, so a copy WILL include it. Amber, not red.
_CAUTION = (
    "background:#fbf3e2; color:#7a5b00; padding:8px; border-left:7px solid #b8860b;"
)
_UNSAFE = (
    "background:#2a1414; color:#ffe6e1; padding:10px; "
    "border:2px solid #b3261e; font-weight:bold;"
)
_WALL = (
    "background:#2a1414; color:#ffe6e1; padding:18px; "
    "border:2px solid #b3261e; font-weight:bold;"
)
_KEY_HEADER = "background:#2a1414; color:#ffe6e1; padding:8px; font-weight:bold;"
_TOAST = "background:#26241f; color:#f4f2ee; padding:8px 14px; border:1px solid #000;"
_HL_ORIG = "QPlainTextEdit { background:#f3d9d4; }"
_HL_SUB = "QPlainTextEdit { background:#dfe9df; }"
_EVIDENCE = "background:#fbfbfa; border:1px solid #b9b6b1; padding:8px;"
_NOTE = "background:#eaf0f2; color:#28414c; padding:6px;"

# Grayscale-first window styling, limited to the base chrome. Semantic states (spine,
# walls, key header, highlights) keep their own inline styles, which win over this.
_WINDOW_QSS = """
QWidget#sanitizer_review_window { background:#f2f1ef; color:#1d1c1a; }
QTreeWidget { background:#ffffff; border:1px solid #b9b6b1; }
QTreeWidget::item { padding:3px 2px; }
QTreeWidget::item:selected { background:#dde6f0; color:#1d1c1a; }
QPlainTextEdit { background:#fbfbfa; border:1px solid #b9b6b1; }
QPushButton { background:#dcdad5; border:1px solid #9a968f; padding:5px 12px; }
QPushButton:disabled { color:#8a8680; }
QToolButton { background:#dcdad5; border:1px solid #9a968f; padding:4px 10px; }
QToolButton:checked { background:#dde6f0; border:1px solid #6f6b65; }
QLineEdit { background:#ffffff; border:1px solid #b9b6b1; padding:3px 6px; }
"""


def _default_suggestion_provider():
    """Build the real (vendored GLiNER, via Buzz) suggestion provider. Imported here
    so it stays lazy: the heavy path is only touched when the user runs suggestions.
    """
    from sanitizer_host.model_provider_buzz import BuzzGlinerProvider

    return BuzzGlinerProvider()


class _SuggestionWorker(QThread):
    """Runs the suggestion model off the GUI thread (download + inference are slow).

    Emits ``status`` updates, then either ``ready`` with the found PENDING items or
    ``failed`` with a human-readable reason. Never raises into the event loop: any
    failure (model unavailable, download error, …) becomes a ``failed`` signal, so
    "no suggestions" is never silent. ``provider_factory`` is injected (tests pass a
    stub); the default builds the vendored-GLiNER provider.
    """

    ready = pyqtSignal(list)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, segments, known_canonicals, provider_factory) -> None:
        super().__init__()
        self._segments = segments
        self._known = known_canonicals
        self._provider_factory = provider_factory

    def run(self) -> None:  # executes on the worker thread
        try:
            from sanitizer_core import ModelSuggestionDetector

            provider = self._provider_factory()
            present = getattr(provider, "model_present", None)
            if callable(present) and not present():
                self.status.emit(
                    _(
                        "Downloading the suggestion model (first run — this can take a "
                        "while)…"
                    )
                )
            else:
                self.status.emit(_("Analysing the transcript…"))
            # Ask once at a low floor: pull every candidate down to _SUGGESTION_FLOOR
            # so the confidence slider can tighten the view later with no re-run.
            detector = ModelSuggestionDetector(provider, threshold=_SUGGESTION_FLOOR)
            items = suggest_items(
                self._segments, detector, known_canonicals=self._known
            )
            # The detector swallows model failures (FR-9), so distinguish "the model
            # broke" from "it ran and found nothing": never conflate the two.
            if detector.last_error:
                self.failed.emit(detector.last_error)
            else:
                self.ready.emit(items)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, never silent
            logger.exception("Sanitizer: running suggestions failed")
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ReviewWindow(QWidget):
    """Presents and edits one transcription's sidecar across Review/Send/Restore.

    ``base_dir`` defaults to Sanitizer's real data directory; tests inject a temp dir.
    """

    def __init__(self, base_dir: str | None = None, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("sanitizer_review_window")
        self.setWindowTitle(_("Sanitizer — Review & restore"))
        self.resize(940, 780)
        self.setStyleSheet(_WINDOW_QSS)

        if base_dir is None:
            try:
                from sanitizer_host.paths import sanitizer_data_dir

                base_dir = sanitizer_data_dir()
            except Exception:  # noqa: BLE001 - platformdirs absent → empty state
                logger.debug("Sanitizer: data dir unavailable; review opens empty.")
                base_dir = ""
        self._base_dir = base_dir
        self._prefs = read_preferences(base_dir) if base_dir else Preferences()
        self._sidecar = None
        self._current_dir = ""
        self._scrubbed_text = ""
        self._key_text = ""
        self._clean = True
        self._mode = "review"
        self._last_toast = ""
        self._toast_label: QLabel | None = None
        self._toast_timer: QTimer | None = None
        self._suggestion_buttons: dict[str, tuple[QPushButton, QPushButton]] = {}
        self._reapprove_buttons: dict[str, QPushButton] = {}
        self._mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        # On-demand suggestions run on a worker thread; tests inject a stub provider.
        self._provider_factory = _default_suggestion_provider
        self._suggest_worker: _SuggestionWorker | None = None
        self._suggest_source_dir = ""  # which transcript the running scan belongs to

        # Live triage state (filters the computed suggestion set client-side; no
        # re-run). Defaults reproduce the pre-triage view (everything ≥ 0.5).
        self._sugg_min_score = _SUGGESTION_MIN_DEFAULT
        self._sugg_types = {type_ for type_, _label in _SUGGESTION_TYPES}
        self._sugg_min_mentions = 1
        self._sugg_sort = _SUGGESTION_SORTS[0][0]
        self._shown_pending: list = []

        # Keyboard-accessible reject for guaranteed rows (context menu + shortcut).
        self._keep_action = QAction(_("Keep in cleartext"), self)
        self._keep_action.setShortcut(QKeySequence("Ctrl+K"))
        self._keep_action.triggered.connect(self._keep_selected_in_cleartext)
        # Bulk approve/reject the current (multi-)selection of pending suggestions.
        # Modifier shortcuts (not bare a/r) so a stray keystroke can't approve a
        # selection by accident; also reachable from the tree's context menu.
        self._approve_sel_action = QAction(_("Approve selected suggestions"), self)
        self._approve_sel_action.setShortcut(QKeySequence("Ctrl+Return"))
        self._approve_sel_action.triggered.connect(self._approve_selected_suggestions)
        self._reject_sel_action = QAction(_("Reject selected suggestions"), self)
        self._reject_sel_action.setShortcut(QKeySequence("Ctrl+Backspace"))
        self._reject_sel_action.triggered.connect(self._reject_selected_suggestions)
        for action in (
            self._keep_action,
            self._approve_sel_action,
            self._reject_sel_action,
        ):
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)

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

        self._spine_label = QLabel()
        self._spine_label.setWordWrap(True)
        layout.addWidget(self._spine_label)

        # Mode tabs: one window, three modes.
        tab_row = QHBoxLayout()
        tab_row.setSpacing(4)
        self._tab_buttons: dict[str, QToolButton] = {}
        self._tab_group = QButtonGroup(self)
        for mode, label in (
            ("review", _("Review")),
            ("sendout", _("Send out")),
            ("restore", _("Restore")),
        ):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _c=False, m=mode: self.set_mode(m))
            self._tab_group.addButton(button)
            self._tab_buttons[mode] = button
            tab_row.addWidget(button)
        tab_row.addStretch(1)
        layout.addLayout(tab_row)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_review_page())  # 0
        self._stack.addWidget(self._build_sendout_page())  # 1
        self._stack.addWidget(self._build_restore_page())  # 2
        layout.addWidget(self._stack, 1)

        self.set_mode("review")
        self.reload()

    # --- construction helpers ----------------------------------------------
    @staticmethod
    def _read_only(height: int | None = None) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        if height:
            edit.setFixedHeight(height)
        return edit

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#b9b6b1;")
        return line

    def _build_review_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        self._review_block = QLabel(
            _(
                "⛔  OUTPUT WITHHELD.  A declared item could not be confirmed "
                "removed (see the tree). No scrubbed text is produced until this "
                "is resolved."
            )
        )
        self._review_block.setWordWrap(True)
        self._review_block.setStyleSheet(_UNSAFE)
        self._review_block.setVisible(False)
        v.addWidget(self._review_block)

        bulk_row = QHBoxLayout()
        self._approve_all_button = QPushButton(_("Approve everything detected"))
        self._approve_all_button.clicked.connect(self._approve_everything)
        bulk_row.addWidget(self._approve_all_button)
        self._edit_list_button = QPushButton(_("Edit my declared list…"))
        self._edit_list_button.clicked.connect(self._open_declared_list_editor)
        bulk_row.addWidget(self._edit_list_button)
        # On-demand model suggestions, opt-in and independent of declared removal
        # (a user may want one, the other, or neither). Runs on a worker thread.
        self._suggest_button = QPushButton(_("✨ Run suggestions"))
        self._suggest_button.setToolTip(
            _(
                "Scan this transcript with the local model for undeclared "
                "names / orgs / places. Held for your review — nothing is removed "
                "automatically."
            )
        )
        self._suggest_button.clicked.connect(self._run_suggestions)
        bulk_row.addWidget(self._suggest_button)
        self._suggest_status = QLabel("")
        self._suggest_status.setStyleSheet("color:#6b6864;")
        bulk_row.addWidget(self._suggest_status)
        bulk_row.addStretch(1)
        # Informed auto-apply (FR-12): hidden until the user has reviewed at least
        # once (see _refresh_auto_apply), then it offers to skip the held step.
        self._auto_apply_check = QCheckBox(_("Auto-apply suggestions from now on"))
        self._auto_apply_check.setToolTip(
            _("Approve model suggestions automatically on future transcripts.")
        )
        self._auto_apply_check.toggled.connect(self._on_auto_apply_toggled)
        self._auto_apply_check.setVisible(False)
        bulk_row.addWidget(self._auto_apply_check)
        v.addLayout(bulk_row)

        self._review_body = QStackedWidget()
        self._review_body.addWidget(self._build_review_normal())  # 0
        self._review_body.addWidget(self._build_review_empty())  # 1
        v.addWidget(self._review_body, 1)
        return page

    def _build_review_normal(self) -> QWidget:
        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText(_("Filter decisions…"))
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._apply_filter)
        left_layout.addWidget(self._filter_edit)
        left_layout.addWidget(self._build_suggestion_controls())
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels([_("item"), _("was"), _("×"), _("provenance")])
        self._tree.setRootIsDecorated(True)
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection  # shift/ctrl multi-select
        )
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self._tree.addAction(self._approve_sel_action)
        self._tree.addAction(self._reject_sel_action)
        self._tree.addAction(self._keep_action)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._tree, 1)
        left_layout.addWidget(self._build_miss_strip())
        split.addWidget(left)

        split.addWidget(self._build_context_pane())
        split.setSizes([560, 360])
        return split

    def _build_suggestion_controls(self) -> QWidget:
        """Live triage controls over the *computed* suggestion set (no re-run).

        A confidence slider, per-type toggles and a min-mentions floor filter which
        pending suggestions are shown; a sort chooser reorders them; two bulk buttons
        act on everything currently shown. Hidden until a run produces suggestions.
        This is the ~222-item answer: compute once, then narrow interactively.
        """
        frame = QFrame()
        frame.setObjectName("sanitizer_suggestion_controls")
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        heading = QHBoxLayout()
        title = QLabel("◇ " + _("Triage suggestions"))
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        heading.addWidget(title)
        heading.addStretch(1)
        self._sugg_count_label = QLabel("")
        self._sugg_count_label.setStyleSheet("color:#4a4742;")
        heading.addWidget(self._sugg_count_label)
        outer.addLayout(heading)

        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel(_("Confidence ≥")))
        self._confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self._confidence_slider.setRange(int(_SUGGESTION_FLOOR * 100), 100)
        self._confidence_slider.setValue(int(self._sugg_min_score * 100))
        self._confidence_slider.setFixedWidth(150)
        self._confidence_slider.setToolTip(
            _("Hide suggestions the model is less sure about.")
        )
        self._confidence_slider.valueChanged.connect(self._on_confidence_changed)
        conf_row.addWidget(self._confidence_slider)
        self._confidence_label = QLabel(f"{int(self._sugg_min_score * 100)}%")
        self._confidence_label.setFixedWidth(38)
        conf_row.addWidget(self._confidence_label)
        conf_row.addWidget(QLabel(_("Min mentions")))
        self._min_mentions_spin = QSpinBox()
        self._min_mentions_spin.setRange(1, 99)
        self._min_mentions_spin.setValue(self._sugg_min_mentions)
        self._min_mentions_spin.setToolTip(
            _("Require a name to appear at least this many times.")
        )
        self._min_mentions_spin.valueChanged.connect(self._on_min_mentions_changed)
        conf_row.addWidget(self._min_mentions_spin)
        conf_row.addStretch(1)
        outer.addLayout(conf_row)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(_("Types:")))
        self._type_checks: dict[str, QCheckBox] = {}
        for type_, label in _SUGGESTION_TYPES:
            check = QCheckBox(_(label))
            check.setChecked(True)
            check.toggled.connect(
                lambda checked, tt=type_: self._on_type_toggled(tt, checked)
            )
            self._type_checks[type_] = check
            type_row.addWidget(check)
        type_row.addStretch(1)
        type_row.addWidget(QLabel(_("Sort")))
        self._sort_combo = QComboBox()
        for sort_id, sort_label in _SUGGESTION_SORTS:
            self._sort_combo.addItem(_(sort_label), sort_id)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        type_row.addWidget(self._sort_combo)
        outer.addLayout(type_row)

        bulk_row = QHBoxLayout()
        self._approve_shown_button = QPushButton(_("Approve all shown"))
        self._approve_shown_button.clicked.connect(
            lambda: self._approve_items(list(self._shown_pending))
        )
        bulk_row.addWidget(self._approve_shown_button)
        self._reject_shown_button = QPushButton(_("Reject all shown"))
        self._reject_shown_button.clicked.connect(
            lambda: self._reject_items(list(self._shown_pending))
        )
        bulk_row.addWidget(self._reject_shown_button)
        bulk_row.addStretch(1)
        outer.addLayout(bulk_row)

        frame.setStyleSheet(
            "QFrame#sanitizer_suggestion_controls "
            "{ background:#f4f2ee; border:1px solid #cfccc6; }"
        )
        self._sugg_controls = frame
        frame.setVisible(False)
        return frame

    def _build_miss_strip(self) -> QWidget:
        """The reverse 'not touched (confirm these)' strip (UX-3 / FR-22).

        Populated with entity-shaped candidates still in cleartext; clicking one
        redacts it everywhere. Reads 'candidates to confirm', never 'all clear',
        so it is simply hidden when there are none.
        """
        self._miss_strip = QFrame()
        self._miss_strip.setStyleSheet("QFrame { background:#fbfbfa; }")
        row = QHBoxLayout(self._miss_strip)
        row.setContentsMargins(6, 4, 6, 4)
        row.addWidget(
            QLabel(_("⚲ Not touched, but entity-shaped — confirm these are fine:"))
        )
        self._miss_container = QWidget()
        self._miss_row = QHBoxLayout(self._miss_container)
        self._miss_row.setContentsMargins(0, 0, 0, 0)
        self._miss_row.setSpacing(4)
        row.addWidget(self._miss_container)
        row.addStretch(1)
        self._miss_strip.setVisible(False)
        return self._miss_strip

    def _build_context_pane(self) -> QWidget:
        pane = QWidget()
        v = QVBoxLayout(pane)

        self._ctx_body = QWidget()
        body = QVBoxLayout(self._ctx_body)
        body.setContentsMargins(0, 0, 0, 0)
        self._ctx_meta = QLabel()
        self._ctx_meta.setWordWrap(True)
        body.addWidget(self._ctx_meta)
        self._ctx_prompt = QLabel()
        body.addWidget(self._ctx_prompt)
        body.addWidget(QLabel(_("ORIGINAL")))
        self._ctx_orig = self._read_only(70)
        self._ctx_orig.setStyleSheet(_HL_ORIG)
        body.addWidget(self._ctx_orig)
        self._ctx_after_label = QLabel(_("AFTER SUBSTITUTION"))
        body.addWidget(self._ctx_after_label)
        self._ctx_sub = self._read_only(70)
        self._ctx_sub.setStyleSheet(_HL_SUB)
        body.addWidget(self._ctx_sub)

        # Select-to-redact: catching a miss and growing the list are one gesture
        # (FR-16). Select text in ORIGINAL above, then redact every occurrence.
        body.addWidget(self._hline())
        redact_row = QHBoxLayout()
        self._ctx_redact_button = QPushButton(_("Redact selected text everywhere"))
        self._ctx_redact_button.clicked.connect(self._redact_selection)
        redact_row.addWidget(self._ctx_redact_button)
        self._ctx_add_checkbox = QCheckBox(_("also add to my declared list"))
        redact_row.addWidget(self._ctx_add_checkbox)
        redact_row.addStretch(1)
        body.addLayout(redact_row)
        body.addStretch(1)
        v.addWidget(self._ctx_body)

        self._ctx_withheld = QLabel(
            _(
                "CONTEXT WITHHELD\nNo substitution preview while a declared item "
                "is unconfirmed."
            )
        )
        self._ctx_withheld.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ctx_withheld.setWordWrap(True)
        self._ctx_withheld.setStyleSheet("color:#6b6864;")
        self._ctx_withheld.setVisible(False)
        v.addWidget(self._ctx_withheld)
        v.addStretch(1)
        return pane

    def _build_review_empty(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addStretch(1)
        glyph = QLabel("✔")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setStyleSheet("font-size:40px; color:#4a6b7a;")
        v.addWidget(glyph)
        title = QLabel(_("Nothing sensitive found"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:17px;")
        v.addWidget(title)
        sub = QLabel(_("This is a result, not a skip"))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color:#6b6864;")
        v.addWidget(sub)
        self._empty_evidence = QLabel()
        self._empty_evidence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_evidence.setStyleSheet(_EVIDENCE)
        v.addWidget(self._empty_evidence)
        row = QHBoxLayout()
        row.addStretch(1)
        self._empty_copy_button = QPushButton(_("Copy the transcript"))
        self._empty_copy_button.clicked.connect(self._copy_scrubbed)
        row.addWidget(self._empty_copy_button)
        empty_edit_list = QPushButton(_("Edit my declared list…"))
        empty_edit_list.clicked.connect(self._open_declared_list_editor)
        row.addWidget(empty_edit_list)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(2)
        return page

    def _build_sendout_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(40, 18, 40, 18)

        self._sendout_safe = QWidget()
        safe = QVBoxLayout(self._sendout_safe)
        self._copy_button = QPushButton(_("📋  Copy scrubbed text"))
        self._copy_button.setMinimumHeight(44)
        font = self._copy_button.font()
        font.setBold(True)
        self._copy_button.setFont(font)
        self._copy_button.clicked.connect(self._copy_scrubbed)
        safe.addWidget(self._copy_button)
        caption = QLabel(_("This is the safe thing to paste into your LLM."))
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet("color:#6b6864;")
        safe.addWidget(caption)

        self._preview_toggle = QToolButton()
        self._preview_toggle.setText(_("▸ Preview scrubbed text"))
        self._preview_toggle.setCheckable(True)
        self._preview_toggle.setStyleSheet("border:none;")
        self._preview_toggle.toggled.connect(self._on_preview_toggled)
        safe.addWidget(self._preview_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self._preview_edit = self._read_only(120)
        self._preview_edit.setVisible(False)
        safe.addWidget(self._preview_edit)
        safe.addWidget(self._hline())

        key_box = QFrame()
        key_box.setStyleSheet("QFrame { border:1px solid #6f6b65; }")
        key = QVBoxLayout(key_box)
        key.setContentsMargins(0, 0, 0, 0)
        key_header = QLabel(
            _("🔒  THE KEY — this is the secret.  Never paste this into an LLM.")
        )
        key_header.setWordWrap(True)
        key_header.setStyleSheet(_KEY_HEADER)
        key.addWidget(key_header)

        # First-use teaching (US6): shown once, dismissible, tied to Send out, not
        # an upfront modal. Visibility is driven from prefs (see _refresh_key_note).
        self._key_note = QFrame()
        note_row = QHBoxLayout(self._key_note)
        note_row.setContentsMargins(6, 4, 6, 4)
        note_label = QLabel(
            _(
                "💡  First time here: remember — the key is the secret. Share the "
                "scrubbed text freely; guard this key."
            )
        )
        note_label.setWordWrap(True)
        note_row.addWidget(note_label, 1)
        self._key_note_dismiss = QToolButton()
        self._key_note_dismiss.setText("✕")
        self._key_note_dismiss.setToolTip(_("Got it — don't show this again"))
        self._key_note_dismiss.setStyleSheet("border:none;")
        self._key_note_dismiss.clicked.connect(self._dismiss_key_note)
        note_row.addWidget(self._key_note_dismiss, 0, Qt.AlignmentFlag.AlignTop)
        self._key_note.setStyleSheet(_NOTE)
        key.addWidget(self._key_note)

        key.addWidget(
            QLabel(
                _(
                    "The key maps placeholders back to real values. You only need "
                    "it to restore a reply."
                )
            )
        )
        self._reveal_button = QPushButton(_("Reveal the key"))
        self._reveal_button.setCheckable(True)
        self._reveal_button.toggled.connect(self._on_reveal_toggled)
        key.addWidget(self._reveal_button, 0, Qt.AlignmentFlag.AlignLeft)
        self._key_edit = self._read_only(90)
        self._key_edit.setVisible(False)
        key.addWidget(self._key_edit)
        self._copy_key_button = QPushButton(_("⚠  Copy the secret key"))
        self._copy_key_button.setVisible(False)
        self._copy_key_button.clicked.connect(self._copy_key)
        key.addWidget(self._copy_key_button, 0, Qt.AlignmentFlag.AlignLeft)
        safe.addWidget(key_box)
        safe.addStretch(1)
        v.addWidget(self._sendout_safe)

        self._sendout_wall = QLabel(
            _(
                "⛔  BLOCKED — UNSAFE\n\nCould not confirm your declared items were "
                "removed.\nThere is no scrubbed text to copy until this is resolved."
            )
        )
        self._sendout_wall.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sendout_wall.setWordWrap(True)
        self._sendout_wall.setStyleSheet(_WALL)
        self._sendout_wall.setVisible(False)
        v.addWidget(self._sendout_wall)
        v.addStretch(1)
        return page

    def _build_restore_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(40, 18, 40, 18)
        v.addWidget(QLabel(_("Paste the LLM's reply (markdown is fine):")))
        self._returned_edit = QPlainTextEdit()
        self._returned_edit.setFixedHeight(90)
        v.addWidget(self._returned_edit)
        self._restore_button = QPushButton(_("Restore originals"))
        self._restore_button.clicked.connect(self._on_restore)
        v.addWidget(self._restore_button, 0, Qt.AlignmentFlag.AlignLeft)
        v.addWidget(QLabel(_("Restored (placeholders filled back from the key):")))
        self._restored_edit = self._read_only(90)
        v.addWidget(self._restored_edit)
        self._restore_report = QLabel()
        v.addWidget(self._restore_report)
        v.addStretch(1)
        return page

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._stack.setCurrentIndex(_MODE_INDEX[mode])
        for name, button in self._tab_buttons.items():
            button.setChecked(name == mode)

    # --- loading ------------------------------------------------------------
    def reload(self) -> None:
        """Re-scan the data directory and load the most recent transcription."""
        ids = persistence.list_sidecars(self._base_dir) if self._base_dir else []
        self._selector.blockSignals(True)
        self._selector.clear()
        for transcription_id in ids:
            directory = os.path.join(self._base_dir, transcription_id)
            meta = persistence.read_meta(directory)
            label = meta.get("source_name") or transcription_id
            self._selector.addItem(label, transcription_id)
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
        self._scrubbed_text = ""
        self._key_text = ""
        self._clean = True
        self._populate_tree([])
        self._clear_layout(self._miss_row)
        self._miss_strip.setVisible(False)
        self._review_body.setCurrentIndex(0)
        self._review_block.setVisible(False)
        self._sendout_safe.setVisible(True)
        self._sendout_wall.setVisible(False)
        self._preview_edit.setPlainText("")
        self._copy_button.setEnabled(False)
        self._key_edit.setPlainText("")
        self._suggest_button.setEnabled(False)  # nothing loaded to scan
        self._suggest_status.setText("")
        self._reset_context()
        self._refresh_auto_apply()
        self._refresh_key_note()
        self._spine_label.setText(
            _("No sanitized transcripts yet. Transcribe with Sanitizer enabled.")
        )
        self._spine_label.setStyleSheet(_EMPTY)

    # --- rendering ----------------------------------------------------------
    def _refresh_after_edit(self) -> None:
        """Re-render every mode from the current sidecar state."""
        sidecar = self._sidecar
        if sidecar is None:
            return
        clean = bool(sidecar.meta.get("clean", True))
        self._clean = clean
        self._scrubbed_text = sidecar.scrubbed_text if clean else ""

        self._populate_tree(sidecar.items)
        self._update_spine(sidecar, clean)

        is_empty = clean and not sidecar.items
        self._review_body.setCurrentIndex(1 if is_empty else 0)
        self._review_block.setVisible(not clean)
        if is_empty:
            self._empty_evidence.setText(self._scan_evidence(sidecar.meta))
        self._reset_context()
        self._populate_misses()
        self._refresh_auto_apply()
        self._refresh_key_note()

        # Send out: safe copy area vs the blocking wall (PG7: withhold when unsafe).
        self._sendout_safe.setVisible(clean)
        self._sendout_wall.setVisible(not clean)
        self._preview_edit.setPlainText(self._scrubbed_text if clean else "")
        self._copy_button.setEnabled(clean and bool(self._scrubbed_text))
        self._empty_copy_button.setEnabled(clean and bool(self._scrubbed_text))
        # Suggestions can run on any loaded transcript, even a "nothing found" one:
        # the model may still spot a name the guaranteed detectors don't.
        self._suggest_button.setEnabled(self._suggest_worker is None)

        self._key_text = "\n".join(
            f"{placeholder}  =  {original}"
            for placeholder, original in sidecar.key.entries.items()
        )
        if self._reveal_button.isChecked():
            self._key_edit.setPlainText(self._key_text or _("(empty)"))

    def _update_spine(self, sidecar, clean: bool) -> None:
        removed = sum(1 for i in sidecar.items if i.state == DecisionState.APPROVED)
        pending = sum(1 for i in sidecar.items if i.state == DecisionState.PENDING)
        # A declared/PII item the user chose to KEEP in cleartext (an override): the
        # verified path is still "clean" (no undetected leak), but a copy will carry
        # that original, so the spine must say so instead of a bare "SAFE".
        kept_guaranteed = sum(
            1
            for i in sidecar.items
            if i.tier in _GUARANTEED and i.state == DecisionState.REJECTED
        )
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
        elif kept_guaranteed:
            self._spine_label.setText(
                _(
                    "⚠  SAFE — but {kept} declared/PII item(s) kept in cleartext "
                    "will be copied · {removed} removed · {pending} suggestions"
                ).format(kept=kept_guaranteed, removed=removed, pending=pending)
            )
            self._spine_label.setStyleSheet(_CAUTION)
        else:
            self._spine_label.setText(
                _(
                    "✔  SAFE TO COPY · {removed} removed · {pending} suggestions "
                    "awaiting you"
                ).format(removed=removed, pending=pending)
            )
            self._spine_label.setStyleSheet(_SAFE)

    @staticmethod
    def _scan_evidence(meta) -> str:
        return _(
            "Scanned {detectors} detectors across {segments} segments · 0 matches "
            "· key not needed"
        ).format(
            detectors=meta.get("detector_count", "?"),
            segments=meta.get("segment_count", "?"),
        )

    def _populate_tree(self, items) -> None:
        self._tree.clear()
        self._suggestion_buttons = {}
        self._reapprove_buttons = {}

        removed = [
            i
            for i in items
            if i.tier in _GUARANTEED and i.state == DecisionState.APPROVED
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

        self._group_cleartext = self._add_group(
            "▸  " + _("Keeping in cleartext") + f" ({len(rejected)})"
        )
        for item in rejected:
            self._add_cleartext_row(item)

        self._group_removed.setExpanded(True)
        self._group_cleartext.setExpanded(False)
        # The SUGGESTIONS zone is a live view over the computed set: grouped, sorted,
        # and filtered by the triage controls. It also re-applies the text filter.
        self._render_suggestions(items)
        self._apply_tree_widths()
        self._update_row_actions()

    def _render_suggestions(self, items) -> None:
        """(Re)build only the SUGGESTIONS zone from the current triage filters.

        Grouped by type, sorted, with per-type and shown-wide bulk actions; the count
        reads "N of M shown". Cheap enough to call on every slider tick: it rebuilds
        just this zone, leaving REMOVED / Keeping-in-cleartext (and their state) alone.
        This is the ~222-suggestions answer: one model run, then narrow it live.
        """
        if not hasattr(self, "_group_suggestions"):
            return
        self._clear_suggestion_children()
        self._suggestion_buttons = {}

        suggestions = [
            i
            for i in items
            if i.tier == TrustTier.SUGGESTED and i.state != DecisionState.REJECTED
        ]
        pending = [i for i in suggestions if i.state == DecisionState.PENDING]
        approved = [i for i in suggestions if i.state == DecisionState.APPROVED]
        # The triage filters (score / type / min-mentions) narrow the PENDING pile.
        # APPROVED suggestions are already-made decisions: they stay visible as the
        # record of what was removed, even for a toggled-off type (an audit trail you
        # must never lose by fiddling a view control).
        shown_pending = [i for i in pending if self._passes_suggestion(i)]
        self._shown_pending = shown_pending
        keyer = self._suggestion_sort_key()

        for type_, label in _SUGGESTION_TYPES:
            type_pending = sorted(
                (i for i in shown_pending if i.type == type_), key=keyer
            )
            type_approved = sorted(
                (i for i in approved if i.type == type_),
                key=lambda i: i.original.casefold(),
            )
            if not type_pending and not type_approved:
                continue
            self._add_suggestion_subgroup(_(label), type_pending, type_approved)

        self._group_suggestions.setExpanded(True)
        self._sugg_count_label.setText(
            _("{shown} of {total} shown").format(
                shown=len(shown_pending), total=len(pending)
            )
        )
        self._sugg_controls.setVisible(bool(suggestions))
        self._approve_shown_button.setEnabled(bool(shown_pending))
        self._reject_shown_button.setEnabled(bool(shown_pending))
        if hasattr(self, "_filter_edit"):
            self._apply_filter(self._filter_edit.text())

    def _clear_suggestion_children(self) -> None:
        """Drop the suggestions subtree, removing its item-widgets (the per-row and
        per-type bulk buttons) so they don't linger in the tree's viewport.

        ``removeItemWidget`` only schedules the old widget for *deferred* deletion, so
        on a rapid rebuild (dragging the confidence slider) a stale button pair can
        paint for a frame before it is freed. Hiding it first stops that instantly.
        """
        group = self._group_suggestions
        stack = [group.child(i) for i in range(group.childCount())]
        while stack:
            node = stack.pop()
            widget = self._tree.itemWidget(node, 3)
            if widget is not None:
                widget.hide()
            self._tree.removeItemWidget(node, 3)
            stack.extend(node.child(i) for i in range(node.childCount()))
        group.takeChildren()

    def _passes_suggestion(self, item) -> bool:
        """Whether a PENDING suggestion passes the live triage filters."""
        return (
            item.type in self._sugg_types
            and item.score >= self._sugg_min_score
            and item.count >= self._sugg_min_mentions
        )

    def _suggestion_sort_key(self):
        if self._sugg_sort == "rarity":
            return lambda i: (i.count, -i.score, i.original.casefold())
        if self._sugg_sort == "alpha":
            return lambda i: i.original.casefold()
        return lambda i: (-i.score, i.original.casefold())  # confidence (default)

    def _add_suggestion_subgroup(self, label, pending_items, approved_items) -> None:
        if approved_items:
            heading = _("  {label} ({n} pending · {a} approved)").format(
                label=label, n=len(pending_items), a=len(approved_items)
            )
        else:
            heading = _("  {label} ({n} pending)").format(
                label=label, n=len(pending_items)
            )
        header = QTreeWidgetItem([heading, "", "", ""])
        font = header.font(0)
        font.setBold(True)
        header.setFont(0, font)
        self._group_suggestions.addChild(header)
        if pending_items:
            holder = QWidget()
            box = QHBoxLayout(holder)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(4)
            approve = QPushButton(_("Approve all"))
            reject = QPushButton(_("Reject all"))
            approve.clicked.connect(
                lambda _c=False, its=list(pending_items): self._approve_items(its)
            )
            reject.clicked.connect(
                lambda _c=False, its=list(pending_items): self._reject_items(its)
            )
            box.addWidget(approve)
            box.addWidget(reject)
            self._tree.setItemWidget(header, 3, holder)
        for item in pending_items:
            self._add_suggestion_row(item, header)
        for item in approved_items:
            self._add_suggestion_row(item, header)
        header.setExpanded(True)

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

    def _add_suggestion_row(self, item, parent) -> None:
        if item.state == DecisionState.PENDING:
            col1 = _("{kind} · {pct}%").format(
                kind=item.type, pct=round(item.score * 100)
            )
        else:
            col1 = item.type
        row = QTreeWidgetItem(["    " + item.original, col1, f"{item.count}×", ""])
        row.setData(0, _USER_ROLE, item)
        parent.addChild(row)
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
        else:  # an approved suggestion: decided, no buttons
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
        header.setDefaultSectionSize(128)
        header.resizeSection(0, 168)
        header.resizeSection(1, 132)
        header.resizeSection(2, 40)

    # --- context / side-by-side (UX-2) --------------------------------------
    def _on_selection_changed(self) -> None:
        self._update_row_actions()
        if not self._clean:
            return  # context stays withheld while unsafe
        item = self._selected_review_item()
        if item is None:
            self._reset_context()
        else:
            self._populate_context(item)

    def _reset_context(self) -> None:
        # Clear the side-by-side first, so an original fragment can never linger
        # across a load into an unsafe transcript (PG7).
        self._ctx_orig.setPlainText("")
        self._ctx_sub.setPlainText("")
        self._ctx_meta.setText("")
        self._ctx_prompt.setText("")
        if not self._clean:
            self._ctx_body.setVisible(False)
            self._ctx_withheld.setVisible(True)
            return
        self._ctx_withheld.setVisible(False)
        self._ctx_body.setVisible(True)
        self._ctx_meta.setText(_("Select a decision to see it in context."))

    def _populate_context(self, item) -> None:
        self._ctx_withheld.setVisible(False)
        self._ctx_body.setVisible(True)
        placeholder = item.placeholder or self._proposed_placeholder(item)
        self._ctx_meta.setText(
            _(
                "{value} · {kind} · provenance: {prov} · {ph} · "
                "{count} occurrence(s)\nWhy flagged: {why}"
            ).format(
                value=item.original,
                kind=item.type,
                prov=self._provenance(item),
                ph=placeholder,
                count=item.count,
                why=item.reason,
            )
        )
        if item.tier == TrustTier.SUGGESTED:
            self._ctx_meta.setText(
                self._ctx_meta.text()
                + _("\nModel confidence: {pct}%").format(pct=round(item.score * 100))
            )
        self._ctx_prompt.setText(_("Is removing this one correct?"))
        original, after = self._context_window(item, placeholder)
        self._ctx_orig.setPlainText(original)
        self._ctx_sub.setPlainText(after)
        pending_suggestion = (
            item.tier == TrustTier.SUGGESTED and item.state != DecisionState.APPROVED
        )
        self._ctx_after_label.setText(
            _("IF APPROVED") if pending_suggestion else _("AFTER SUBSTITUTION")
        )

    def _proposed_placeholder(self, item) -> str:
        existing = {i.placeholder for i in self._sidecar.items if i.placeholder}
        return next_free_placeholder(existing, item.label)

    def _context_window(self, item, placeholder: str) -> tuple[str, str]:
        segments = self._sidecar.segments
        placements = [p for p in item.placements if 0 <= p.segment < len(segments)]
        if not placements:
            return item.original, placeholder
        placement = placements[0]
        text = segments[placement.segment].original
        start, end = placement.start, placement.end
        lo, hi = max(0, start - 30), min(len(text), end + 30)
        prefix = ("…" if lo > 0 else "") + text[lo:start]
        suffix = text[end:hi] + ("…" if hi < len(text) else "")
        return (
            f"{prefix}«{text[start:end]}»{suffix}",
            f"{prefix}«{placeholder}»{suffix}",
        )

    # --- miss-catching / redact (UX-3 / FR-16) ------------------------------
    def _populate_misses(self) -> None:
        self._clear_layout(self._miss_row)
        if self._sidecar is None or not self._clean or not self._scrubbed_text:
            self._miss_strip.setVisible(False)
            return
        known = {i.canonical for i in self._sidecar.items}
        # scan_safe_text, NOT self._scrubbed_text: the display join can merge
        # close segments with a plain space, but the miss-scan regex must never
        # let a capitalized run cross a segment boundary (see its docstring).
        scan_text = scan_safe_text(self._sidecar.segments)
        candidates = find_miss_candidates(scan_text, known=known, limit=4)
        for candidate in candidates:
            button = QPushButton(f"{candidate.surface} ({candidate.count})")
            button.setToolTip(_("Redact this everywhere and add it to your list"))
            button.clicked.connect(
                lambda _c=False, s=candidate.surface: self._redact_surface(s, add=True)
            )
            self._miss_row.addWidget(button)
        self._miss_strip.setVisible(bool(candidates))

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)  # remove now; deleteLater alone lingers
                widget.deleteLater()

    def _redact_selection(self) -> None:
        self._redact_surface(
            self._ctx_orig.textCursor().selectedText(),
            add=self._ctx_add_checkbox.isChecked(),
        )

    def _redact_surface(self, surface: str, *, add: bool = False) -> None:
        if self._sidecar is None:
            return
        surface = surface.strip("«»").strip()
        if not surface:
            self._toast(_("Select some text in ORIGINAL to redact first."))
            return
        known = {i.canonical for i in self._sidecar.items}
        item = build_manual_item(
            surface,
            self._sidecar.segments,
            existing_placeholders={
                i.placeholder for i in self._sidecar.items if i.placeholder
            },
        )
        if item is None or item.canonical in known:
            self._toast(_("Nothing new to redact for “{}”.").format(surface))
            return
        self._sidecar.items.append(item)
        if add:
            terms = self._sidecar.meta.setdefault("manual_terms", [])
            if item.original not in terms:
                terms.append(item.original)
            self._add_to_declared_store(item.original)  # real cross-transcript term
        self._apply_edits()
        self._toast(_("Redacted “{}” everywhere.").format(item.original))

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

    def _approve_items(self, items) -> None:
        """Approve a batch of items with a single re-derive/persist (bulk triage)."""
        items = [i for i in items if i is not None]
        if not items:
            return
        for item in items:
            self._set_item_approved(item, True)
        self._apply_edits()

    def _reject_items(self, items) -> None:
        """Reject (keep-in-cleartext) a batch with a single re-derive/persist."""
        items = [i for i in items if i is not None]
        if not items:
            return
        for item in items:
            self._set_item_approved(item, False)
        self._apply_edits()

    def _approve_selected_suggestions(self) -> None:
        self._approve_items(self._selected_pending_suggestions())

    def _reject_selected_suggestions(self) -> None:
        self._reject_items(self._selected_pending_suggestions())

    def _selected_items(self) -> list:
        return [
            data
            for data in (row.data(0, _USER_ROLE) for row in self._tree.selectedItems())
            if data is not None
        ]

    def _selected_pending_suggestions(self) -> list:
        return [
            i
            for i in self._selected_items()
            if i.tier == TrustTier.SUGGESTED and i.state == DecisionState.PENDING
        ]

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
        has_pending = bool(self._selected_pending_suggestions())
        self._approve_sel_action.setEnabled(has_pending)
        self._reject_sel_action.setEnabled(has_pending)

    def _set_item_approved(self, item, approved: bool) -> None:
        if approved:
            item.state = DecisionState.APPROVED
            if not item.placeholder:
                existing = {i.placeholder for i in self._sidecar.items if i.placeholder}
                item.placeholder = next_free_placeholder(existing, item.label)
        else:
            item.state = DecisionState.REJECTED

    def _rederive_and_persist(self) -> None:
        """Re-derive scrubbed + key from the item states, refresh, and persist,
        without marking the run reviewed (used when items change but the user hasn't
        made a decision yet, e.g. suggestions just arrived)."""
        sidecar = self._sidecar
        segments, key = apply_review(sidecar.segments, sidecar.items)
        sidecar.segments = segments
        sidecar.key = key
        self._refresh_after_edit()
        self._persist()

    def _apply_edits(self) -> None:
        """A user decision edit: re-derive/persist, then mark the run reviewed."""
        self._rederive_and_persist()
        self._mark_reviewed()  # any decision edit counts as a review (gates FR-12)

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
            logger.exception("Sanitizer: failed to persist review edits.")

    # --- on-demand suggestions (worker thread) ------------------------------
    def _run_suggestions(self) -> None:
        """Scan the current transcript with the local model, off the GUI thread."""
        if self._sidecar is None or self._suggest_worker is not None:
            return
        self._suggest_button.setEnabled(False)
        self._suggest_status.setText(_("Starting…"))
        # Remember which transcript we're scanning: the model run can be slow (first-run
        # download), and the user may switch transcripts before it returns. The result
        # is located against THESE segments, so it must only ever land on this sidecar.
        self._suggest_source_dir = self._current_dir
        known = {i.canonical for i in self._sidecar.items}
        worker = _SuggestionWorker(
            list(self._sidecar.segments), known, self._provider_factory
        )
        worker.status.connect(self._suggest_status.setText)
        worker.ready.connect(self._on_suggestions_ready)
        worker.failed.connect(self._on_suggestions_failed)
        worker.finished.connect(self._suggestions_cleanup)
        self._suggest_worker = worker
        worker.start()

    def _suggest_result_is_stale(self) -> bool:
        """True if the loaded transcript changed since the scan started: the result
        was located against the old segments, so applying it would corrupt this one."""
        return self._sidecar is None or self._current_dir != self._suggest_source_dir

    def _on_suggestions_ready(self, items) -> None:
        if self._suggest_result_is_stale():
            self._suggest_status.setText("")
            return
        known = {i.canonical for i in self._sidecar.items}
        fresh = [item for item in items if item.canonical not in known]
        self._sidecar.items.extend(fresh)
        # Informed auto-apply (FR-12): if opted in after ≥1 review, approve them now;
        # otherwise they wait PENDING for the user's click (FR-9 default).
        if fresh and self._prefs.auto_apply_suggestions and self._prefs.has_reviewed:
            for item in fresh:
                self._set_item_approved(item, True)
        self._rederive_and_persist()
        if fresh:
            self._suggest_status.setText(
                _("Found {n} — see below.").format(n=len(fresh))
            )
            self._toast(
                _("✨ {n} suggestion(s) added for your review.").format(n=len(fresh))
            )
        else:
            self._suggest_status.setText(_("No new suggestions found."))

    def _on_suggestions_failed(self, reason: str) -> None:
        if self._suggest_result_is_stale():
            self._suggest_status.setText("")
            return
        # Never silent: surface *why* on screen, not only in the log.
        self._suggest_status.setText(_("Unavailable — {reason}").format(reason=reason))
        self._toast(_("Couldn't run suggestions: {reason}").format(reason=reason))

    def _suggestions_cleanup(self) -> None:
        self._suggest_button.setEnabled(True)
        worker = self._suggest_worker
        self._suggest_worker = None
        if worker is not None:
            worker.deleteLater()

    # --- live suggestion triage (filter the computed set; no re-run) ---------
    def _on_confidence_changed(self, value: int) -> None:
        self._sugg_min_score = value / 100.0
        self._confidence_label.setText(f"{value}%")
        self._rerender_suggestions_view()

    def _on_min_mentions_changed(self, value: int) -> None:
        self._sugg_min_mentions = value
        self._rerender_suggestions_view()

    def _on_type_toggled(self, type_: str, checked: bool) -> None:
        if checked:
            self._sugg_types.add(type_)
        else:
            self._sugg_types.discard(type_)
        self._rerender_suggestions_view()

    def _on_sort_changed(self, index: int) -> None:
        self._sugg_sort = self._sort_combo.itemData(index) or "confidence"
        self._rerender_suggestions_view()

    def _rerender_suggestions_view(self) -> None:
        """Re-render only the suggestions zone from the current filters: a pure view
        change (no state edit, no persist), instant even at hundreds of rows."""
        if self._sidecar is not None:
            self._render_suggestions(self._sidecar.items)

    # --- preferences · declared list · filter (Step D) ----------------------
    def _save_prefs(self) -> None:
        if not self._base_dir:
            return
        try:
            write_preferences(self._base_dir, self._prefs)
        except OSError:
            logger.exception("Sanitizer: failed to persist preferences.")

    def _mark_reviewed(self) -> None:
        """Record that the user has reviewed at least once: the gate for FR-12."""
        if not self._prefs.has_reviewed:
            self._prefs.has_reviewed = True
            self._save_prefs()
            self._refresh_auto_apply()

    def _refresh_auto_apply(self) -> None:
        """Offer auto-apply only once a review has actually happened (FR-12)."""
        self._auto_apply_check.setVisible(self._prefs.has_reviewed)
        self._auto_apply_check.blockSignals(True)
        self._auto_apply_check.setChecked(self._prefs.auto_apply_suggestions)
        self._auto_apply_check.blockSignals(False)

    def _on_auto_apply_toggled(self, checked: bool) -> None:
        self._prefs.auto_apply_suggestions = checked
        self._save_prefs()
        self._toast(
            _("Future suggestions will be applied automatically.")
            if checked
            else _("Future suggestions will be held for your review.")
        )

    def _refresh_key_note(self) -> None:
        self._key_note.setVisible(not self._prefs.key_note_dismissed)

    def _dismiss_key_note(self) -> None:
        self._prefs.key_note_dismissed = True
        self._save_prefs()
        self._key_note.setVisible(False)

    def _add_to_declared_store(self, term: str) -> None:
        if not self._base_dir:
            return
        try:
            add_declared_term(self._base_dir, term)
        except OSError:
            logger.exception("Sanitizer: failed to grow the declared list.")

    def _open_declared_list_editor(self) -> None:
        _DeclaredListEditor(self._base_dir, self).exec()

    def _apply_filter(self, text: str) -> None:
        """Hide decision rows that don't match ``text`` (zone/type headers always
        stay). Walks into the suggestion type subgroups so nested rows filter too."""
        needle = text.strip().casefold()

        def walk(node) -> None:
            for index in range(node.childCount()):
                child = node.child(index)
                if child.data(0, _USER_ROLE) is not None:  # a decision row, not header
                    child.setHidden(
                        bool(needle) and needle not in self._row_haystack(child)
                    )
                walk(child)

        for group in (
            self._group_removed,
            self._group_suggestions,
            self._group_cleartext,
        ):
            walk(group)

        # A type subgroup whose every row was filtered out would otherwise leave a
        # dangling "People (…)" header (with its bulk buttons) over nothing. Hide it.
        for index in range(self._group_suggestions.childCount()):
            subgroup = self._group_suggestions.child(index)
            visible = any(
                not subgroup.child(j).isHidden() for j in range(subgroup.childCount())
            )
            subgroup.setHidden(not visible)

    @staticmethod
    def _row_haystack(row) -> str:
        parts = [row.text(0), row.text(1), row.text(3)]
        item = row.data(0, _USER_ROLE)
        if item is not None:
            parts += [item.original, item.type, item.placeholder]
        return " ".join(parts).casefold()

    # --- send out / key / restore / clipboard -------------------------------
    def _on_preview_toggled(self, checked: bool) -> None:
        self._preview_edit.setVisible(checked)
        self._preview_toggle.setText(
            _("▾ Hide preview") if checked else _("▸ Preview scrubbed text")
        )

    def _on_reveal_toggled(self, checked: bool) -> None:
        self._key_edit.setVisible(checked)
        self._copy_key_button.setVisible(checked)
        self._reveal_button.setText(_("Hide key") if checked else _("Reveal the key"))
        if checked:
            self._key_edit.setPlainText(self._key_text or _("(empty)"))

    def _on_restore(self) -> None:
        if self._sidecar is None:
            return
        returned = self._returned_edit.toPlainText()
        restored = restore(returned, self._sidecar.key)
        self._restored_edit.setPlainText(restored)
        filled = sum(1 for ph in self._sidecar.key.entries if ph in returned)
        unresolved = len(_PLACEHOLDER_RE.findall(restored))
        report = _("{n} placeholder(s) filled").format(n=filled)
        if unresolved:
            report += _("  ·  ⚠ {n} still unresolved in the text").format(n=unresolved)
        self._restore_report.setText(report)
        self._restore_report.setStyleSheet(
            "color:#b3261e;" if unresolved else "color:#2f6b3d;"
        )

    def _copy_scrubbed(self) -> None:
        # PG7: while unsafe there is NO reachable copy path. The handler refuses
        # even if invoked directly, and the text isn't in a widget to begin with.
        if not self._clean or not self._scrubbed_text:
            return
        self._to_clipboard(self._scrubbed_text)
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
        # A window-owned single-shot timer (not a bare QTimer.singleShot) so that if the
        # window is closed within the 2.4 s, the timer is torn down with it and never
        # fires into a deleted label.
        if self._toast_timer is None:
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(self._hide_toast)
        self._toast_timer.start(2400)

    def _hide_toast(self) -> None:
        if self._toast_label is not None:
            self._toast_label.hide()


class _DeclaredListEditor(QDialog):
    """In-window editor for Sanitizer's own declared-terms list (US2).

    These are the terms Sanitizer manages itself, grown by "add to my list" while
    catching a miss and by this editor, which the pipeline **unions** with the list
    in Buzz's plugin settings on every future transcript. So editing here changes
    what Sanitizer removes going forward, not just in the current transcript. Backed by
    :mod:`sanitizer_core.declared_store`; ``base_dir`` is injected (tests pass a temp
    dir). No-ops gracefully when there is no data directory.
    """

    def __init__(self, base_dir: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Sanitizer — my declared list"))
        self.resize(440, 380)
        self._base_dir = base_dir

        layout = QVBoxLayout(self)
        intro = QLabel(
            _(
                "Terms Sanitizer always removes — on this and every future transcript. "
                "Combined with the list in Buzz's plugin settings. One per line; "
                "prefix with a category for clearer placeholders (e.g. 'person: Jane')."
            )
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._list = QListWidget()
        layout.addWidget(self._list, 1)

        add_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText(_("Add a term, e.g. 'person: Jane'"))
        self._input.returnPressed.connect(self._add)
        add_row.addWidget(self._input, 1)
        add_button = QPushButton(_("Add"))
        add_button.clicked.connect(self._add)
        add_row.addWidget(add_button)
        self._remove_button = QPushButton(_("Remove selected"))
        self._remove_button.clicked.connect(self._remove)
        add_row.addWidget(self._remove_button)
        layout.addLayout(add_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._reload()

    def _reload(self) -> None:
        self._list.clear()
        if self._base_dir:
            self._list.addItems(read_declared_terms(self._base_dir))

    def _add(self) -> None:
        term = self._input.text().strip()
        if term and self._base_dir:
            add_declared_term(self._base_dir, term)
            self._input.clear()
            self._reload()

    def _remove(self) -> None:
        item = self._list.currentItem()
        if item is not None and self._base_dir:
            remove_declared_term(self._base_dir, item.text())
            self._reload()
