"""Main-thread UI attachment for Cloak.

Buzz has no UI-extension hook, and a plugin may be constructed on *either*
thread depending on how Buzz loads it:

* **Startup** — ``PluginManager.initialize`` runs on the **main thread**, but
  *before* Buzz installs its real menu bar: ``MainWindow.__init__`` calls
  ``initialize`` (~line 80) well ahead of ``setMenuBar`` (~line 128).
* **Add from URL** — ``PluginManager.add_from_url`` runs on a **background**
  ``QThreadPool`` thread and instantiates the plugin *twice*.

Attaching the menu directly from ``__init__`` is therefore wrong in both cases:
at startup it lands on a default menu bar Buzz then discards (→ no menu), and on
add it runs off the GUI thread (cross-thread ``QMenu`` parenting breaks dedupe →
two menus). To be correct in both, this module **posts the attach onto the main
thread's event loop**, where it runs once the window is fully built;
``build_cloak_menu`` is idempotent so repeated instantiations collapse to a
single menu. Only public Qt APIs are used — Buzz is never modified.
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QWidget,
)

from cloak_host.i18n import gettext as _

logger = logging.getLogger(__name__)

CLOAK_MENU_OBJECT_NAME = "cloak_menu"
REVIEW_ACTION_OBJECT_NAME = "cloak_review_action"
DEMO_ACTION_OBJECT_NAME = "cloak_demo_action"  # dev-only, gated by CLOAK_DEV

_MAX_ATTACH_ATTEMPTS = 40
_RETRY_INTERVAL_MS = 50

# Strong references to Cloak's top-level windows, so neither Qt nor Python
# garbage-collects them the moment the opening helper returns.
_open_windows: list[QWidget] = []


# --- main-thread marshaling -------------------------------------------------


class _MainThreadInvoker(QObject):
    """Runs a callable on this object's own thread via a queued signal.

    Created lazily and parked on the main (GUI) thread, so emitting ``_run``
    from any thread posts the callable to the main event loop. The explicit
    ``QueuedConnection`` makes the call deferred even when emitted *from* the
    main thread — so attach work never runs synchronously inside ``__init__``
    (which, at startup, is too early — the real menu bar is not set yet).
    """

    _run = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._run.connect(self._execute, Qt.ConnectionType.QueuedConnection)

    @pyqtSlot(object)
    def _execute(self, fn) -> None:
        fn()


_invoker: _MainThreadInvoker | None = None


def _post_to_main_thread(fn) -> bool:
    """Schedule ``fn`` to run on the main thread's event loop.

    Returns ``False`` (no-op) when there is no ``QApplication`` (headless / CLI /
    tests). The invoker is created lazily and moved to the main thread, so this
    works whether the caller is on the main thread (startup) or a worker thread
    (add-from-URL).
    """
    app = QApplication.instance()
    if app is None:
        return False
    global _invoker
    if _invoker is None:
        invoker = _MainThreadInvoker()
        if invoker.thread() is not app.thread():
            invoker.moveToThread(app.thread())
        _invoker = invoker
    _invoker._run.emit(fn)
    return True


def find_main_window() -> QMainWindow | None:
    """Return the host's main window, or ``None`` if absent / no GUI.

    Picks the first top-level ``QMainWindow``. Buzz runs a single main window,
    so this is unambiguous in practice.
    """
    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        if isinstance(widget, QMainWindow):
            return widget
    return None


def build_cloak_menu(main_window: QMainWindow) -> QMenu | None:
    """Add the Cloak menu to ``main_window``'s menu bar (idempotent).

    Returns the menu — existing or newly created — or ``None`` if the window has
    no menu bar. Uses only the public ``QMainWindow.menuBar()`` API. Must run on
    the main thread (callers route through ``_post_to_main_thread``).
    """
    menu_bar = main_window.menuBar()
    if menu_bar is None:
        return None

    existing = menu_bar.findChild(QMenu, CLOAK_MENU_OBJECT_NAME)
    if existing is not None:
        return existing

    menu = menu_bar.addMenu(_("Cloak"))
    menu.setObjectName(CLOAK_MENU_OBJECT_NAME)

    review_action = QAction(_("Review & restore…"), main_window)
    review_action.setObjectName(REVIEW_ACTION_OBJECT_NAME)
    review_action.triggered.connect(lambda: _safe_open(open_review_window, main_window))
    menu.addAction(review_action)

    # Developer-only: the manual sanitizer playground, hidden unless CLOAK_DEV is
    # set. It is not part of the shipped surface — the review window is the product.
    if os.environ.get("CLOAK_DEV"):
        menu.addSeparator()
        demo_action = QAction(_("Sanitizer (manual demo)…"), main_window)
        demo_action.setObjectName(DEMO_ACTION_OBJECT_NAME)
        demo_action.triggered.connect(lambda: _safe_open(open_demo_window, main_window))
        menu.addAction(demo_action)

    logger.info("Cloak: menu attached to '%s'.", main_window.windowTitle())
    return menu


def open_review_window(parent: QWidget | None = None) -> QWidget:
    """Show the sidecar-backed review & restore window (imported lazily)."""
    from cloak_host.review_window import ReviewWindow

    return _show_window(ReviewWindow(parent=parent))


def open_demo_window(parent: QWidget | None = None) -> QWidget:
    """Show the developer sanitizer playground (imported lazily; CLOAK_DEV only)."""
    from cloak_host.demo_window import CloakDemoWindow

    return _show_window(CloakDemoWindow(parent))


def _safe_open(opener, parent: QWidget | None) -> None:
    """Run a window-opener, containing any error so it can't crash the host.

    PyQt6 aborts the process on an unhandled exception raised inside a slot, so
    every menu action routes through here — a plugin must never take down Buzz.
    """
    try:
        opener(parent)
    except Exception:  # noqa: BLE001 - deliberate host-safety boundary
        logger.exception("Cloak: failed to open a window.")


def _show_window(window: QWidget) -> QWidget:
    """Show a top-level window and keep a reference so Qt doesn't GC it."""
    _open_windows.append(window)
    window.destroyed.connect(lambda *_args: _discard_window(window))
    window.show()
    window.raise_()
    window.activateWindow()
    return window


def _discard_window(window: QWidget) -> None:
    """Drop our reference once a window is destroyed."""
    try:
        _open_windows.remove(window)
    except ValueError:
        pass


def attach_to_main_window() -> None:
    """Schedule attaching the Cloak menu on the main thread's event loop.

    Safe to call from a plugin ``__init__`` on **any** thread, and at any point
    during host startup. No-op when there is no ``QApplication`` (headless / CLI
    / tests). The actual attach runs later, on the main thread, once the window
    and its menu bar exist.
    """
    if QApplication.instance() is None:
        logger.debug("Cloak: no QApplication; skipping UI attach (headless).")
        return
    _post_to_main_thread(lambda: _attach_now(attempt=0))


def _attach_now(attempt: int) -> None:
    """Attach the menu on the main thread, retrying briefly if not ready yet."""
    main_window = find_main_window()
    if main_window is not None:
        build_cloak_menu(main_window)
        return
    if attempt >= _MAX_ATTACH_ATTEMPTS:
        logger.warning(
            "Cloak: main window not found after %d attempts; UI not attached.",
            attempt,
        )
        return
    QTimer.singleShot(_RETRY_INTERVAL_MS, lambda: _attach_now(attempt + 1))
