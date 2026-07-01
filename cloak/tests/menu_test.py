"""Menu-attachment tests.

Require PyQt6 + pytest-qt, so they run in the Buzz environment (and skip cleanly
elsewhere). They validate the §2.3 integration assumption and the fix for the two
real-world failure modes:

* startup attaches *before* Buzz sets its menu bar (must defer, not run in
  ``__init__``); and
* add-from-URL constructs the plugin twice on a background thread (must marshal
  to the main thread and dedupe).
"""

from __future__ import annotations

import threading

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")


@pytest.fixture()
def main_window(qtbot):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication, QMainWindow

    # Purge any QMainWindow left by an earlier test so find_main_window() is
    # deterministic — production has exactly one main window. deleteLater alone
    # isn't enough: DeferredDelete events must be dispatched explicitly, since a
    # plain processEvents() does not flush them.
    app = QApplication.instance()
    if app is not None:
        for widget in list(app.topLevelWidgets()):
            if isinstance(widget, QMainWindow):
                widget.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)

    window = QMainWindow()
    window.setWindowTitle("Buzz (test)")
    qtbot.addWidget(window)
    return window


@pytest.fixture(autouse=True)
def _reset_menu_state():
    """Isolate module-level singletons (invoker, window refs) between tests."""
    from cloak_host import menu as menu_mod

    menu_mod._invoker = None
    menu_mod._open_windows.clear()
    yield
    menu_mod._invoker = None
    menu_mod._open_windows.clear()


def _cloak_menu(main_window):
    from PyQt6.QtWidgets import QMenu

    from cloak_host import menu as menu_mod

    return main_window.menuBar().findChild(QMenu, menu_mod.CLOAK_MENU_OBJECT_NAME)


# --- build_cloak_menu (direct, synchronous) ---------------------------------


def test_build_cloak_menu_adds_menu(main_window):
    from PyQt6.QtGui import QAction

    from cloak_host import menu as menu_mod

    created = menu_mod.build_cloak_menu(main_window)

    assert created is not None
    assert _cloak_menu(main_window) is created
    # The shipped menu is exactly the review action (no demo/About by default).
    review = main_window.findChild(QAction, menu_mod.REVIEW_ACTION_OBJECT_NAME)
    assert review is not None
    assert main_window.findChild(QAction, menu_mod.DEMO_ACTION_OBJECT_NAME) is None


def test_build_cloak_menu_is_idempotent(main_window):
    from PyQt6.QtWidgets import QMenu

    from cloak_host import menu as menu_mod

    first = menu_mod.build_cloak_menu(main_window)
    second = menu_mod.build_cloak_menu(main_window)

    assert first is second
    menus = [
        m
        for m in main_window.menuBar().findChildren(QMenu)
        if m.objectName() == menu_mod.CLOAK_MENU_OBJECT_NAME
    ]
    assert len(menus) == 1


def test_review_action_opens_window(main_window, qtbot):
    from PyQt6.QtGui import QAction

    from cloak_host import menu as menu_mod

    menu_mod.build_cloak_menu(main_window)
    action = main_window.findChild(QAction, menu_mod.REVIEW_ACTION_OBJECT_NAME)
    assert action is not None

    action.trigger()

    assert len(menu_mod._open_windows) == 1
    window = menu_mod._open_windows[-1]
    qtbot.addWidget(window)
    assert window.objectName() == "cloak_review_window"


def test_demo_hidden_unless_dev_env(main_window, monkeypatch):
    from PyQt6.QtGui import QAction

    from cloak_host import menu as menu_mod

    monkeypatch.delenv("CLOAK_DEV", raising=False)
    menu_mod.build_cloak_menu(main_window)
    assert main_window.findChild(QAction, menu_mod.DEMO_ACTION_OBJECT_NAME) is None


def test_demo_shown_with_dev_env(main_window, monkeypatch):
    from PyQt6.QtGui import QAction

    from cloak_host import menu as menu_mod

    monkeypatch.setenv("CLOAK_DEV", "1")
    menu_mod.build_cloak_menu(main_window)
    assert main_window.findChild(QAction, menu_mod.DEMO_ACTION_OBJECT_NAME) is not None


def test_find_main_window_returns_the_window(main_window):
    from cloak_host import menu as menu_mod

    assert menu_mod.find_main_window() is main_window


# --- attach_to_main_window (deferred + marshaled) ---------------------------


def test_attach_is_noop_without_app(monkeypatch):
    from PyQt6.QtWidgets import QApplication

    from cloak_host import menu as menu_mod

    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    menu_mod.attach_to_main_window()  # must return quietly, schedule nothing
    assert menu_mod._invoker is None


def test_attach_defers_then_attaches(main_window, qtbot):
    """The attach must NOT run synchronously (that's the startup bug); it lands
    on the next event-loop turn, once the real menu bar exists."""
    from cloak_host import menu as menu_mod

    menu_mod.attach_to_main_window()

    # Deferred: nothing attached yet, on this stack frame.
    assert _cloak_menu(main_window) is None

    qtbot.waitUntil(lambda: _cloak_menu(main_window) is not None, timeout=2000)


def test_repeated_attach_yields_single_menu(main_window, qtbot):
    """Double instantiation (the add-from-URL path) must collapse to one menu."""
    from PyQt6.QtWidgets import QMenu

    from cloak_host import menu as menu_mod

    menu_mod.attach_to_main_window()
    menu_mod.attach_to_main_window()

    qtbot.waitUntil(lambda: _cloak_menu(main_window) is not None, timeout=2000)
    menus = [
        m
        for m in main_window.menuBar().findChildren(QMenu)
        if m.objectName() == menu_mod.CLOAK_MENU_OBJECT_NAME
    ]
    assert len(menus) == 1


def test_attach_from_worker_thread_attaches_on_main(main_window, qtbot):
    """Calling attach off the main thread (the add path) still attaches exactly
    one menu, on the main thread, via the invoker."""
    from cloak_host import menu as menu_mod

    done = threading.Event()

    def worker():
        menu_mod.attach_to_main_window()
        done.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert done.wait(2.0)
    thread.join()

    qtbot.waitUntil(lambda: _cloak_menu(main_window) is not None, timeout=2000)
