"""Tests for the plugin packaging script (``tools/package.py``).

Pure standard library — runnable in any environment with pytest, no Buzz or
PyQt6 required.
"""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_package_module():
    path = _REPO_ROOT / "tools" / "package.py"
    spec = importlib.util.spec_from_file_location("cloak_package_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_zip_places_plugin_py_at_root(tmp_path: Path):
    package = _load_package_module()
    output = package.build_zip(output=tmp_path / "cloak.zip")

    assert output.is_file()
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()

    # Buzz's loader looks for plugin.py at the archive root first.
    assert "plugin.py" in names, names
    # The plugin's own packages and locale set ship with it.
    assert any(n.startswith("cloak_host/") for n in names), names
    assert any(n.startswith("cloak_core/") for n in names), names
    assert any(n.startswith("locale/") and n.endswith(".json") for n in names), names


def test_build_zip_excludes_dev_files(tmp_path: Path):
    package = _load_package_module()
    output = package.build_zip(output=tmp_path / "cloak.zip")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()

    assert not any(n.startswith("tests/") for n in names), names
    assert "pyproject.toml" not in names, names
    assert "DEV_NOTES.md" not in names, names
    assert not any(n.endswith((".pyc", ".pyo")) for n in names), names


def test_build_zip_uses_forward_slashes(tmp_path: Path):
    package = _load_package_module()
    output = package.build_zip(output=tmp_path / "cloak.zip")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()

    # Zip entries must use POSIX separators to extract cross-platform.
    assert not any("\\" in n for n in names), names


def test_build_zip_prunes_unused_vendored_server_but_keeps_imports(tmp_path: Path):
    package = _load_package_module()
    output = package.build_zip(output=tmp_path / "cloak.zip")

    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()

    # The vendored GLiNER HTTP/Ray inference server is never imported → not shipped.
    assert not any(n.startswith("_vendor/gliner/serve/") for n in names), names
    # But GLiNER's core and the subpackages model.py imports at load time must ship.
    assert "_vendor/gliner/model.py" in names, names
    assert any(n.startswith("_vendor/gliner/training/") for n in names), names
    assert any(n.startswith("_vendor/gliner/evaluation/") for n in names), names
