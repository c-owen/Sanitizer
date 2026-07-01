"""Render the Cloak layout skeleton to PNGs, headlessly (no display, no browser).

Run with Qt's offscreen platform:

    QT_QPA_PLATFORM=offscreen python design/render_states.py

Each (mode, state) is grabbed to ``design/renders/*.png`` — authentic native-Qt
output, the visual confirmation of the structural spec in ``cloak_layout_skeleton.py``.
"""

from __future__ import annotations

import os

from PyQt6.QtWidgets import QApplication

from cloak_layout_skeleton import CloakDesignSkeleton

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders")

# (filename, mode, demo-state)
SHOTS = [
    ("review_safe", "review", "safe"),
    ("review_unsafe", "review", "unsafe"),
    ("review_empty", "review", "empty"),
    ("sendout_safe", "sendout", "safe"),
    ("sendout_unsafe", "sendout", "unsafe"),
    ("restore", "restore", "safe"),
]


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    app = QApplication([])  # noqa: F841 - kept alive for the widget tree
    w = CloakDesignSkeleton()
    w.show()
    for name, mode, state in SHOTS:
        w.set_state(state)
        w.set_mode(mode)
        app.processEvents()
        path = os.path.join(OUT, f"{name}.png")
        ok = w.grab().save(path)
        print(f"{'ok ' if ok else 'ERR'}  {path}")


if __name__ == "__main__":
    main()
