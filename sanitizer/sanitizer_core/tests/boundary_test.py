"""Guarantee: sanitizer_core is host-independent — it imports neither buzz nor Qt.

This is the brief's "verifiable independently of the Buzz app" mandate, enforced
by AST scan so a regression fails the build (G5 / DoD).
"""

from __future__ import annotations

import ast
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parents[1]  # .../sanitizer/sanitizer_core
_FORBIDDEN = frozenset({"buzz", "PyQt6", "PySide6", "PyQt5"})


def _core_source_files():
    return [p for p in _CORE_DIR.rglob("*.py") if "tests" not in p.parts]


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_core_source_imports_no_host_packages():
    offenders = {}
    for path in _core_source_files():
        bad = _top_level_imports(path) & _FORBIDDEN
        if bad:
            offenders[path.name] = sorted(bad)
    assert not offenders, f"sanitizer_core must not import host packages: {offenders}"


def test_core_imports_cleanly():
    import sanitizer_core

    assert callable(sanitizer_core.sanitize)
    assert callable(sanitizer_core.restore)
    assert sanitizer_core.__version__
