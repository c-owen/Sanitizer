"""Cloak — layout-only PyQt6 skeleton (DESIGN SPEC, not production code).

This module is the *structural handoff* for the Cloak review window. It builds the
approved v2 design as a real Qt widget tree — the two-zone decision list, the three
modes (Review / Send out / Restore), and the Safe / Unsafe / Empty states — using the
exact sample data, copy, and design tokens from the Claude-Design handoff README.

It deliberately contains **NO behaviour**: no sidecar, no ``apply_review``, no
persistence, no real sanitization. ``set_mode`` / ``set_state`` only toggle which
static widgets are visible, so every screen state can be rendered to PNG headlessly
(see ``render_states.py``). The implementing agent's job is to bind the real data
model (``ReviewItem`` / ``TrustTier`` / ``DecisionState`` / ``apply_review``) into
*this* structure — not to invent layout from a screenshot.

Region → spec-ID mapping is noted inline. Build target: PyQt6, plugin-only, offline,
keyboard-accessible, fully usable without colour (UX-5).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# --- design tokens (from the handoff README; grayscale-first, colour only reinforces) ---
T = {
    "win_bg": "#f2f1ef", "title_bg": "#e4e2de", "menu_bg": "#efeeec",
    "panel": "#ffffff", "panel2": "#fbfbfa",
    "border": "#b9b6b1", "border_mid": "#9a968f", "border_strong": "#6f6b65",
    "text": "#1d1c1a", "muted": "#6b6864", "muted2": "#8a8680",
    "sel": "#dde6f0", "btn": "#dcdad5",
    "safe_fg": "#2f6b3d", "safe_bg": "#e9f1ea",
    "empty_fg": "#4a6b7a", "empty_bg": "#eaf0f2",
    "unsafe_bg": "#2a1414", "unsafe_border": "#b3261e", "unsafe_fg": "#ffe6e1",
    "hl_orig": "#f3d9d4", "hl_sub": "#dfe9df",
}
MONO = "ui-monospace, Menlo, Consolas, monospace"

QSS = f"""
QMainWindow, QWidget {{ background: {T['win_bg']}; color: {T['text']};
    font-family: -apple-system, 'Segoe UI', Roboto, 'Symbola', sans-serif; font-size: 13px; }}
QMenuBar {{ background: {T['menu_bg']}; border-bottom: 1px solid {T['border']}; }}
QMenuBar::item:selected {{ background: {T['sel']}; }}
QFrame#toolbar {{ background: {T['title_bg']}; border-bottom: 1px solid {T['border']}; }}
QTreeWidget {{ background: {T['panel']}; border: 1px solid {T['border']}; }}
QTreeWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:selected {{ background: {T['sel']}; color: {T['text']}; }}
QPlainTextEdit {{ background: {T['panel2']}; border: 1px solid {T['border']}; }}
QPushButton {{ background: {T['btn']}; border: 1px solid {T['border_mid']}; padding: 5px 12px; }}
QPushButton:disabled {{ color: {T['muted2']}; }}
QToolButton {{ background: {T['btn']}; border: 1px solid {T['border_mid']}; padding: 4px 10px; }}
QToolButton:checked {{ background: {T['sel']}; border: 1px solid {T['border_strong']}; }}
"""

# --- sample data (verbatim from the handoff) --------------------------------
REMOVED_ROWS = [
    ("{{PERSON-A}}", "Jane", "2×", "your list"),
    ("{{PROJECT-A}}", "Apollo", "3×", "your list"),
    ("{{CLIENT-A}}", "Northwind", "1×", "your list"),
    ("{{EMAIL-1}}", "con…@…", "1×", "email"),
    ("{{PHONE-1}}", "(415)…", "1×", "phone"),
    ("{{SSN-1}}", "•••-••-1234", "1×", "ssn"),
    ("{{IP-1}}", "192.168…", "1×", "ip"),
    ("{{URL-1}}", "intra…/…", "1×", "url"),
    ("{{CARD-1}}", "••••4242", "1×", "card"),
]
SUGGEST_ROWS = [("Riverside", "place", "1×"), ("Helix", "org", "2×")]


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color: {T['border']};")
    return f


def _ro_edit(text: str, height: int | None = None) -> QPlainTextEdit:
    e = QPlainTextEdit(text)
    e.setReadOnly(True)
    if height:
        e.setFixedHeight(height)
    return e


def _bold(item: QTreeWidgetItem, italic: bool = False) -> None:
    f = item.font(0)
    f.setBold(True)
    f.setItalic(italic)
    item.setFont(0, f)


class CloakDesignSkeleton(QMainWindow):
    """Layout-only stand-in for the real ReviewWindow. No logic; render-driven."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cloak — Review & restore")
        self.resize(940, 700)
        self.setStyleSheet(QSS)
        self._mode = "review"
        self._state = "safe"

        self._build_menubar()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())          # transcript selector + demo toggle
        self._spine = QLabel()                          # safety spine — UX-5 / PG7 / US8 / US9
        self._spine.setWordWrap(True)
        root.addWidget(self._spine)
        root.addWidget(self._build_tabstrip())          # mode tabs — Review/Send/Restore

        self._stack = QStackedWidget()                  # one window, three modes
        self._stack.addWidget(self._build_review())     # 0
        self._stack.addWidget(self._build_sendout())    # 1
        self._stack.addWidget(self._build_restore())    # 2
        root.addWidget(self._stack, 1)

        self.set_mode("review")
        self.set_state("safe")

    # --- chrome -------------------------------------------------------------
    def _build_menubar(self) -> None:
        mb = self.menuBar()
        for name in ("File", "Edit", "View", "Cloak", "Help"):
            m = mb.addMenu(name)
            if name == "Cloak":
                for a in ("Review & restore…", "About / what Cloak protects…"):
                    m.addAction(QAction(a, self))

    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("toolbar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 6, 10, 6)
        h.addWidget(QLabel("Transcript:"))
        sel = QComboBox()
        sel.addItem("Depo — Meridian v. Caldwell · Jun 30")
        h.addWidget(sel)
        h.addStretch(1)
        # demo-state toggle — PROTOTYPE ONLY. Real plugin derives state from the
        # sanitizer result; drop this (or hide behind a debug flag).
        h.addWidget(QLabel("demo state:"))
        self._state_group = QButtonGroup(self)
        for s, label in (("safe", "Safe"), ("unsafe", "Unsafe"), ("empty", "Empty")):
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            self._state_group.addButton(b)
            h.addWidget(b)
            b.clicked.connect(lambda _=False, st=s: self.set_state(st))
        return bar

    def _build_tabstrip(self) -> QWidget:
        strip = QFrame()
        h = QHBoxLayout(strip)
        h.setContentsMargins(10, 6, 10, 0)
        h.setSpacing(4)
        self._tab_btns = {}
        for m, label in (("review", "Review"), ("sendout", "Send out"), ("restore", "Restore")):
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, mm=m: self.set_mode(mm))
            self._tab_btns[m] = b
            h.addWidget(b)
        h.addStretch(1)
        return strip

    # --- mode 1: REVIEW (UX-1 home surface) ---------------------------------
    def _build_review(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(10, 8, 10, 10)

        # UNSAFE blocking strip (US9 / PG7) — hidden unless state == unsafe
        self._review_block = QLabel(
            "⛔ OUTPUT WITHHELD.  A declared item could not be confirmed removed "
            "(see ⚠ below). No scrubbed text is produced until this is resolved."
        )
        self._review_block.setWordWrap(True)
        self._review_block.setStyleSheet(
            f"background:{T['unsafe_bg']}; color:{T['unsafe_fg']}; "
            f"border:2px solid {T['unsafe_border']}; padding:8px; font-weight:bold;"
        )
        v.addWidget(self._review_block)

        # bulk action row — one button + filter (UX-4); named bulks are a filter, not groups
        bulk = QHBoxLayout()
        bulk.addWidget(QPushButton("Approve everything detected"))
        filt = QComboBox()
        filt.addItems(["all detected", "approve all from my list",
                       "approve all phone numbers", "approve all emails"])
        bulk.addWidget(filt)
        bulk.addStretch(1)
        v.addLayout(bulk)

        # review body is itself a stack: [normal master-detail] / [empty "proof it ran"]
        self._review_body = QStackedWidget()
        self._review_body.addWidget(self._build_review_normal())  # 0
        self._review_body.addWidget(self._build_review_empty())   # 1
        v.addWidget(self._review_body, 1)
        return page

    def _build_review_normal(self) -> QWidget:
        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["item", "was", "×", "provenance"])
        self._tree.setRootIsDecorated(True)

        # Zone 1 — REMOVED (guaranteed): declared + PII together, provenance per row
        g_removed = QTreeWidgetItem(["▣  REMOVED — guaranteed  ·  declared + detected, verified"])
        self._tree.addTopLevelItem(g_removed)
        g_removed.setFirstColumnSpanned(True)  # must follow addTopLevelItem
        _bold(g_removed)
        for ph, was, cnt, prov in REMOVED_ROWS:
            it = QTreeWidgetItem(["  " + ph, f"was: {was}", cnt, prov])
            it.setFont(0, QFont(MONO.split(",")[0]))
            g_removed.addChild(it)
        g_removed.setExpanded(True)

        # Zone 2 — SUGGESTIONS (held, lower trust): Approve/Reject buttons, not checkboxes
        g_sugg = QTreeWidgetItem(["◇  SUGGESTIONS — model's guesses, your call  "
                                  "(not guaranteed — nothing removed until you approve)"])
        self._tree.addTopLevelItem(g_sugg)
        g_sugg.setFirstColumnSpanned(True)
        _bold(g_sugg, italic=True)
        for name, kind, cnt in SUGGEST_ROWS:
            it = QTreeWidgetItem(["    " + name, kind, cnt, ""])
            g_sugg.addChild(it)
            btns = QWidget()
            bh = QHBoxLayout(btns)
            bh.setContentsMargins(0, 0, 0, 0)
            bh.setSpacing(4)
            bh.addWidget(QPushButton("Approve"))
            bh.addWidget(QPushButton("Reject"))
            self._tree.setItemWidget(it, 3, btns)
        g_sugg.setExpanded(True)

        # Zone 3 — Keeping in cleartext (rejected, struck-through, COLLAPSED) — UX-9
        g_clear = QTreeWidgetItem(["▸  Keeping in cleartext (1)"])
        self._tree.addTopLevelItem(g_clear)
        g_clear.setFirstColumnSpanned(True)
        struck = QTreeWidgetItem(["    Q3", "date", "2×", "Kept"])
        f = struck.font(0)
        f.setStrikeOut(True)
        struck.setFont(0, f)
        g_clear.addChild(struck)
        g_clear.setExpanded(False)

        self._tree.itemSelectionChanged.connect(self._on_row_selected)
        self._apply_tree_widths()  # re-applied post-show via set_mode (offscreen reset)
        lv.addWidget(self._tree, 1)

        # reverse "miss-catching" strip (UX-3 / FR-22) — candidates to confirm, never "all clear"
        rev = QFrame()
        rev.setStyleSheet(f"background:{T['panel2']}; border:1px solid {T['border']};")
        rh = QHBoxLayout(rev)
        rh.addWidget(QLabel("⚲ Not touched, but entity-shaped — confirm these are fine:"))
        rh.addWidget(QLabel("“Karen” (1)"))
        rh.addWidget(QPushButton("Redact + add"))
        rh.addStretch(1)
        lv.addWidget(rev)
        split.addWidget(left)

        # RIGHT — context / side-by-side (UX-2)
        self._context = self._build_context_pane()
        split.addWidget(self._context)
        split.setSizes([600, 320])
        return split

    def _build_context_pane(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self._ctx_meta = QLabel(
            "Jane  ·  person  ·  provenance: your list  ·  {{PERSON-A}}  ·  2 occurrences\n"
            "Why flagged: matched your declared list"
        )
        self._ctx_meta.setWordWrap(True)
        v.addWidget(self._ctx_meta)
        self._ctx_prompt = QLabel("Is removing this one correct?")
        v.addWidget(self._ctx_prompt)
        self._ctx_lbl_o = QLabel("ORIGINAL")
        v.addWidget(self._ctx_lbl_o)
        self._ctx_orig = _ro_edit("…the deposition of «Jane», who confirmed…", 70)
        self._ctx_orig.setStyleSheet(f"QPlainTextEdit{{background:{T['hl_orig']};}}")
        v.addWidget(self._ctx_orig)
        self._ctx_lbl_s = QLabel("AFTER SUBSTITUTION")
        v.addWidget(self._ctx_lbl_s)
        self._ctx_sub = _ro_edit("…the deposition of «{{PERSON-A}}», who confirmed…", 70)
        self._ctx_sub.setStyleSheet(f"QPlainTextEdit{{background:{T['hl_sub']};}}")
        v.addWidget(self._ctx_sub)

        v.addWidget(_hline())
        self._ctx_scan = QCheckBox("Scan for misses")            # FR-22 toggle
        v.addWidget(self._ctx_scan)
        self._ctx_red = QWidget()
        red = QHBoxLayout(self._ctx_red)
        red.setContentsMargins(0, 0, 0, 0)
        red.addWidget(QPushButton("Redact this everywhere"))      # FR-16
        red.addWidget(QCheckBox("also always treat as sensitive (add to my list)"))
        red.addStretch(1)
        v.addWidget(self._ctx_red)
        v.addStretch(1)

        # UNSAFE: the side-by-side is replaced by a withheld notice
        self._ctx_withheld = QLabel("CONTEXT WITHHELD\nNo substitution preview while a "
                                    "declared item is unconfirmed.")
        self._ctx_withheld.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ctx_withheld.setStyleSheet(f"color:{T['muted']};")
        self._ctx_withheld.setVisible(False)
        v.addWidget(self._ctx_withheld)
        return w

    def _build_review_empty(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addStretch(1)
        big = QLabel("✔")
        big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        big.setStyleSheet(f"font-size:46px; color:{T['empty_fg']};")
        v.addWidget(big)
        title = QLabel("Nothing sensitive found")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:18px;")
        v.addWidget(title)
        sub = QLabel("This is a result, not a skip")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"font-size:12px; color:{T['muted']};")
        v.addWidget(sub)
        evidence = QLabel("Scanned 14 detectors across 36 segments · 0 matches · key not needed")
        evidence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        evidence.setStyleSheet(
            f"font-family:{MONO}; background:{T['panel2']}; border:1px solid {T['border']};"
            "padding:8px;")
        v.addWidget(evidence)                                       # US8 proof-it-ran
        row = QHBoxLayout()
        row.addStretch(1)
        for b in ("Copy the transcript", "Scan for misses", "Edit my declared list"):
            row.addWidget(QPushButton(b))
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(2)
        return w

    def _on_row_selected(self) -> None:
        pass  # layout-only: selection would repopulate the context pane in the real build

    # --- mode 2: SEND OUT (UX-6) --------------------------------------------
    def _build_sendout(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(40, 18, 40, 18)

        # the safe copy area (shown when not unsafe)
        self._sendout_safe = QWidget()
        sv = QVBoxLayout(self._sendout_safe)
        copy = QPushButton("📋  Copy scrubbed text")
        copy.setMinimumHeight(46)
        cf = copy.font()
        cf.setPointSize(13)
        cf.setBold(True)
        copy.setFont(cf)
        sv.addWidget(copy)
        cap = QLabel("This is the safe thing to paste into your LLM.")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setStyleSheet(f"color:{T['muted']};")
        sv.addWidget(cap)
        disc = QToolButton()
        disc.setText("▸ Preview scrubbed text")
        disc.setStyleSheet("border:none;")
        sv.addWidget(disc, 0, Qt.AlignmentFlag.AlignLeft)
        sv.addWidget(_hline())

        # fenced key block — the secret (PG8 / UX-6)
        key_box = QFrame()
        key_box.setStyleSheet(f"border:1px solid {T['border_strong']}; background:{T['panel']};")
        kv = QVBoxLayout(key_box)
        kv.setContentsMargins(0, 0, 0, 0)
        hdr = QLabel("🔒  THE KEY — this is the secret.   Never paste this into an LLM.")
        hdr.setStyleSheet(f"background:{T['unsafe_bg']}; color:{T['unsafe_fg']}; padding:8px; "
                          "font-weight:bold;")
        kv.addWidget(hdr)
        note = QLabel("💡 First time here: remember — the key is the secret. Share the scrubbed "
                      "text freely; guard this key.   ✕")
        note.setWordWrap(True)
        note.setStyleSheet(f"background:{T['empty_bg']}; padding:6px;")
        kv.addWidget(note)                                          # first-use teaching (US6)
        kv.addWidget(QLabel("The key maps placeholders back to real values. You only need it to "
                            "restore a reply."))
        kv.addWidget(QPushButton("Reveal the key"), 0, Qt.AlignmentFlag.AlignLeft)
        sv.addWidget(key_box)
        sv.addStretch(1)
        v.addWidget(self._sendout_safe)

        # the unsafe wall (shown when unsafe) — no copyable text anywhere
        self._sendout_wall = QLabel("⛔  BLOCKED — UNSAFE\n\nCloak could not confirm your declared "
                                    "items were removed.\nThere is no scrubbed text to copy until "
                                    "this is resolved.")
        self._sendout_wall.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sendout_wall.setWordWrap(True)
        self._sendout_wall.setStyleSheet(
            f"background:{T['unsafe_bg']}; color:{T['unsafe_fg']}; "
            f"border:2px solid {T['unsafe_border']}; padding:24px; font-size:15px; font-weight:bold;")
        self._sendout_wall.setVisible(False)
        v.addWidget(self._sendout_wall)
        v.addStretch(1)
        return page

    # --- mode 3: RESTORE (UX-7 mirror) --------------------------------------
    def _build_restore(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(40, 18, 40, 18)
        v.addWidget(QLabel("Paste the LLM's reply (markdown is fine):"))
        v.addWidget(_ro_edit("{{PERSON-A}} agreed to ship {{PROJECT-A}} by Friday; "
                             "loop in {{ORG-A}}.", 64))
        v.addWidget(QPushButton("Restore originals"), 0, Qt.AlignmentFlag.AlignLeft)
        v.addWidget(QLabel("Restored (placeholders filled back from the key):"))
        res = _ro_edit("Jane Okafor agreed to ship Apollo by Friday; loop in {{ORG-A}}.", 64)
        v.addWidget(res)
        flag = QLabel("Reserved — possible re-identification flag would appear here.")
        flag.setStyleSheet(f"color:{T['muted2']};")
        v.addWidget(flag)
        foot = QLabel("2 placeholders filled  ·  ⚠ 1 still unresolved in the text")
        foot.setStyleSheet(f"color:{T['unsafe_border']};")
        v.addWidget(foot)                                           # FR-7 surface unresolved
        v.addStretch(1)
        return page

    # --- render-driving state setters (NO real logic) -----------------------
    def _apply_tree_widths(self) -> None:
        """Column sizing. The offscreen header resets sections to defaultSectionSize
        on show(); controlling THAT (not per-section resize, which loses the race) is
        what holds — verified empirically."""
        hdr = self._tree.header()
        hdr.setStretchLastSection(True)     # provenance fills the rest
        hdr.setDefaultSectionSize(138)
        hdr.resizeSection(0, 170)
        hdr.resizeSection(1, 140)
        hdr.resizeSection(2, 44)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._stack.setCurrentIndex({"review": 0, "sendout": 1, "restore": 2}[mode])
        for m, b in self._tab_btns.items():
            b.setChecked(m == mode)
        self._apply_tree_widths()

    def set_state(self, state: str) -> None:
        self._state = state
        if state == "safe":
            self._spine.setText("  ✔  SAFE TO COPY · 9 removed · 2 suggestions awaiting you")
            self._spine.setStyleSheet(
                f"background:{T['safe_bg']}; color:{T['safe_fg']}; padding:8px; "
                f"border-left:7px solid {T['safe_fg']};")
        elif state == "empty":
            self._spine.setText("  ✔  NOTHING SENSITIVE FOUND in this transcript")
            self._spine.setStyleSheet(
                f"background:{T['empty_bg']}; color:{T['empty_fg']}; padding:8px; "
                f"border-left:7px solid {T['empty_fg']};")
        else:  # unsafe
            self._spine.setText("  ⛔  BLOCKED — UNSAFE — could not confirm your declared "
                                "items were removed")
            self._spine.setStyleSheet(
                f"background:{T['unsafe_bg']}; color:{T['unsafe_fg']}; padding:10px; "
                f"border:2px solid {T['unsafe_border']}; font-weight:bold;")
        self._review_body.setCurrentIndex(1 if state == "empty" else 0)
        self._review_block.setVisible(state == "unsafe")
        unsafe = state == "unsafe"
        for wdg in (self._ctx_meta, self._ctx_prompt, self._ctx_lbl_o, self._ctx_orig,
                    self._ctx_lbl_s, self._ctx_sub, self._ctx_scan, self._ctx_red):
            wdg.setVisible(not unsafe)
        self._ctx_withheld.setVisible(unsafe)
        self._sendout_safe.setVisible(not unsafe)
        self._sendout_wall.setVisible(unsafe)
