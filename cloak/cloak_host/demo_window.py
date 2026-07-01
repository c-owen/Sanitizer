"""In-Buzz demo of the sanitization core.

A throwaway "playground" reachable from the Cloak menu: paste declared terms and
text, press Sanitize, copy the scrubbed text out, then paste a reply back and
Restore — exercising the full round trip (including the markdown trip, since the
``{{…}}`` placeholders survive formatting). Proves ``cloak_core`` works inside the
real app, ahead of the full review/restore UI (Phase 5, which replaces this).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cloak_core import DeclaredListDetector, pii_detectors, restore, sanitize
from cloak_core.model import Key
from cloak_host.i18n import gettext as _

_SAMPLE_TERMS = "person: Jane\nperson: Bob\nproject: Project Apollo"
_SAMPLE_TEXT = (
    "Jane told Bob about Project Apollo. "
    "Email contact@example.com or call (415) 555-1212."
)


def _parse_terms(raw: str) -> dict[str, list[str]]:
    """Parse the terms box: ``category: term`` lines, bare lines → ``term``."""
    by_category: dict[str, list[str]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            category, term = line.split(":", 1)
            category, term = category.strip().lower(), term.strip()
        else:
            category, term = "term", line
        if term:
            by_category.setdefault(category, []).append(term)
    return by_category


class CloakDemoWindow(QWidget):
    """Sanitize → copy out → paste reply → restore, over ``cloak_core``."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("cloak_demo_window")
        self.setWindowTitle(_("Cloak — Sanitizer demo"))
        self.resize(680, 760)
        self._last_scrubbed = ""
        self._key = Key()

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(_("Declared terms — one per line, e.g. 'person: Jane':"))
        )
        self._terms_edit = QPlainTextEdit(_SAMPLE_TERMS)
        self._terms_edit.setFixedHeight(70)
        layout.addWidget(self._terms_edit)

        layout.addWidget(QLabel(_("Transcript text:")))
        self._text_edit = QPlainTextEdit(_SAMPLE_TEXT)
        self._text_edit.setFixedHeight(80)
        layout.addWidget(self._text_edit)

        top_buttons = QHBoxLayout()
        self._sanitize_button = QPushButton(_("Sanitize"))
        self._sanitize_button.clicked.connect(self._on_sanitize)
        top_buttons.addWidget(self._sanitize_button)
        self._copy_button = QPushButton(_("Copy scrubbed text"))
        self._copy_button.clicked.connect(self._on_copy)
        top_buttons.addWidget(self._copy_button)
        top_buttons.addStretch(1)
        layout.addLayout(top_buttons)

        self._status_label = QLabel()
        layout.addWidget(self._status_label)

        layout.addWidget(QLabel(_("Scrubbed (safe to paste into an LLM):")))
        self._scrubbed_edit = self._read_only(70)
        layout.addWidget(self._scrubbed_edit)

        layout.addWidget(QLabel(_("Key — the secret; keep this private:")))
        self._key_edit = self._read_only(80)
        layout.addWidget(self._key_edit)

        layout.addWidget(
            QLabel(_("Returned text (paste the reply — markdown is fine):"))
        )
        self._returned_edit = QPlainTextEdit()
        self._returned_edit.setFixedHeight(70)
        layout.addWidget(self._returned_edit)

        self._restore_button = QPushButton(_("Restore"))
        self._restore_button.clicked.connect(self._on_restore)
        layout.addWidget(self._restore_button)

        layout.addWidget(QLabel(_("Restored (originals filled back from the key):")))
        self._restored_edit = self._read_only(70)
        layout.addWidget(self._restored_edit)

        self._on_sanitize()  # populate with the sample on open

    @staticmethod
    def _read_only(height: int) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setFixedHeight(height)
        return edit

    def _on_sanitize(self) -> None:
        terms = _parse_terms(self._terms_edit.toPlainText())
        detectors = [DeclaredListDetector(terms), *pii_detectors()]
        result = sanitize(self._text_edit.toPlainText(), detectors)

        self._last_scrubbed = result.scrubbed
        self._key = result.key
        self._scrubbed_edit.setPlainText(result.scrubbed)
        key_text = "\n".join(
            f"{placeholder}  =  {original}"
            for placeholder, original in result.key.entries.items()
        )
        self._key_edit.setPlainText(key_text or _("(nothing detected)"))

        if result.clean:
            self._status_label.setText(_("✓ Clean — no declared term or PII leaked."))
        else:
            leaked = ", ".join(survivor.value for survivor in result.survivors)
            self._status_label.setText(_("✗ NOT clean — leaked: {}").format(leaked))

        # Pre-fill the reply box with the scrubbed text and show the round trip.
        self._returned_edit.setPlainText(result.scrubbed)
        self._on_restore()

    def _on_restore(self) -> None:
        restored = restore(self._returned_edit.toPlainText(), self._key)
        self._restored_edit.setPlainText(restored)

    def _on_copy(self) -> None:
        app = QApplication.instance()
        if app is None or not self._last_scrubbed:
            return
        clipboard = app.clipboard()
        if clipboard is not None:
            clipboard.setText(self._last_scrubbed)
