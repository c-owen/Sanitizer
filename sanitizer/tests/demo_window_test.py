"""SanitizerDemoWindow: the in-Buzz Phase 1 sanitizer playground.

Requires PyQt6 + pytest-qt (skips elsewhere). Confirms sanitizer_core runs inside a
real Qt window and the sanitize → key → restore round trip works end to end.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pytestqt")


def test_demo_populates_on_open(qtbot):
    from sanitizer_host.demo_window import SanitizerDemoWindow

    window = SanitizerDemoWindow()
    qtbot.addWidget(window)

    # The constructor runs an initial sanitize over the (categorized) sample.
    assert "{{PERSON-A}}" in window._scrubbed_edit.toPlainText()
    assert window._key_edit.toPlainText() != ""


def test_demo_sanitize_and_round_trip(qtbot):
    from sanitizer_host.demo_window import SanitizerDemoWindow

    window = SanitizerDemoWindow()
    qtbot.addWidget(window)
    window._terms_edit.setPlainText("Jane\nBob")
    window._text_edit.setPlainText("Jane called Bob, not Janet.")

    window._sanitize_button.click()

    scrubbed = window._scrubbed_edit.toPlainText()
    assert "{{TERM-1}}" in scrubbed and "{{TERM-2}}" in scrubbed
    assert "Janet" in scrubbed  # substring safety: the word stays
    assert "Jane" not in scrubbed.replace("Janet", "")  # the name itself is gone
    assert window._restored_edit.toPlainText() == "Jane called Bob, not Janet."


def test_demo_empty_state(qtbot):
    from sanitizer_host.demo_window import SanitizerDemoWindow

    window = SanitizerDemoWindow()
    qtbot.addWidget(window)
    window._terms_edit.setPlainText("Jane")
    window._text_edit.setPlainText("nothing sensitive here")

    window._sanitize_button.click()

    assert window._scrubbed_edit.toPlainText() == "nothing sensitive here"
    assert "(nothing detected)" in window._key_edit.toPlainText()


def test_demo_restore_handles_markdown_wrapping(qtbot):
    from sanitizer_host.demo_window import SanitizerDemoWindow

    window = SanitizerDemoWindow()
    qtbot.addWidget(window)
    window._terms_edit.setPlainText("Jane")
    window._text_edit.setPlainText("Call Jane")
    window._sanitize_button.click()

    # A returned reply that bolded the placeholder still restores correctly.
    window._returned_edit.setPlainText("Call **{{TERM-1}}** now")
    window._restore_button.click()

    assert window._restored_edit.toPlainText() == "Call **Jane** now"


def test_demo_copy_does_not_raise(qtbot):
    from sanitizer_host.demo_window import SanitizerDemoWindow

    window = SanitizerDemoWindow()
    qtbot.addWidget(window)
    window._terms_edit.setPlainText("Jane")
    window._text_edit.setPlainText("Hi Jane")
    window._sanitize_button.click()

    window._copy_button.click()  # clipboard may be unavailable offscreen

    assert "{{TERM-1}}" in window._last_scrubbed
