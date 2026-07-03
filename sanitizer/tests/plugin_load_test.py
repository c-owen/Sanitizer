"""Faithful load test: Buzz's own loader must accept the Sanitizer plugin folder.

Imports only the lightweight ``buzz.plugins.loader`` (no torch / PyQt6), so this
runs against the real host-loading code path without the full ML environment.
``importorskip`` keeps it green where the ``buzz`` package is unavailable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SANITIZER_DIR = _REPO_ROOT / "sanitizer"


def test_sanitizer_loads_via_buzz_loader():
    loader = pytest.importorskip("buzz.plugins.loader")

    plugin = loader.load_plugin_from_dir(str(_SANITIZER_DIR))

    assert plugin.metadata.id == "sanitizer"
    assert plugin.metadata.name  # non-empty display name
    assert plugin.metadata.version == "0.7.2"


def test_sanitizer_is_a_buzz_plugin_instance():
    loader = pytest.importorskip("buzz.plugins.loader")
    base = pytest.importorskip("buzz.plugins.base")

    # load_plugin_from_dir raises PluginLoadError unless exactly one BuzzPlugin
    # subclass is present, so a successful load already asserts uniqueness.
    plugin = loader.load_plugin_from_dir(str(_SANITIZER_DIR))

    assert isinstance(plugin, base.BuzzPlugin)


def test_sanitizer_declares_no_pip_dependencies():
    """Phase 0 must install and run fully offline: no deps to fetch."""
    loader = pytest.importorskip("buzz.plugins.loader")

    plugin = loader.load_plugin_from_dir(str(_SANITIZER_DIR))

    assert plugin.metadata.pip_dependencies == []


def test_sanitizer_installs_via_file_url(tmp_path, monkeypatch):
    """Exercise the real 'Add by URL' mechanics: build the zip, then
    download → safe-extract → validate-load → install via a ``file://`` URL,
    into a throwaway plugins dir (never the user's real cache).
    """
    import importlib.util

    loader = pytest.importorskip("buzz.plugins.loader")

    # Build a fresh zip with the packaging tool.
    pkg_path = _REPO_ROOT / "tools" / "package.py"
    spec = importlib.util.spec_from_file_location("sanitizer_package_tool", pkg_path)
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    zip_path = package.build_zip(output=tmp_path / "sanitizer.zip")

    # Redirect installs to a temp dir so the real cache is untouched.
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))

    plugin_id = loader.download_and_extract(zip_path.as_uri())

    assert plugin_id == "sanitizer"
    installed = plugins_dir / "sanitizer"
    assert (installed / "plugin.py").is_file()
    assert (installed / "sanitizer_host" / "menu.py").is_file()
    assert len(list((installed / "locale").glob("*.json"))) == 14
    # The installed copy re-loads cleanly through the host loader.
    assert loader.load_plugin_from_dir(str(installed)).metadata.id == "sanitizer"
