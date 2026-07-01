"""Package the Cloak plugin folder into ``dist/cloak.zip`` for local serving.

The archive places ``plugin.py`` at its root (Buzz's loader also accepts a
single wrapping directory). Development-only files — tests, tooling config,
notes and caches — are excluded so the distributable stays lean.

Usage::

    python tools/package.py                  # -> dist/cloak.zip
    python tools/package.py --output X.zip    # custom output path
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PLUGIN_DIR = _REPO_ROOT / "cloak"
_DEFAULT_OUTPUT = _REPO_ROOT / "dist" / "cloak.zip"

# Directory names pruned anywhere in the tree.
_EXCLUDE_DIRS = frozenset(
    {"__pycache__", "tests", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
)
# Exact top-level files excluded (dev tooling / notes).
_EXCLUDE_ROOT_FILES = frozenset({"pyproject.toml", "DEV_NOTES.md"})
# File suffixes excluded anywhere.
_EXCLUDE_SUFFIXES = frozenset({".pyc", ".pyo"})


def _should_include(path: Path, plugin_dir: Path) -> bool:
    rel = path.relative_to(plugin_dir)
    if any(part in _EXCLUDE_DIRS for part in rel.parts):
        return False
    if path.suffix in _EXCLUDE_SUFFIXES:
        return False
    if len(rel.parts) == 1 and rel.name in _EXCLUDE_ROOT_FILES:
        return False
    return True


def build_zip(plugin_dir: Path = _PLUGIN_DIR, output: Path = _DEFAULT_OUTPUT) -> Path:
    """Zip ``plugin_dir`` into ``output`` with ``plugin.py`` at the archive root.

    Returns the resolved output path. Raises ``FileNotFoundError`` if the plugin
    entry module is missing (a fast guard against packaging the wrong directory).
    """
    plugin_dir = plugin_dir.resolve()
    if not (plugin_dir / "plugin.py").is_file():
        raise FileNotFoundError(f"No plugin.py found in {plugin_dir}")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p
        for p in plugin_dir.rglob("*")
        if p.is_file() and _should_include(p, plugin_dir)
    )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            # ``as_posix`` keeps forward slashes so the zip extracts correctly on
            # every platform, regardless of the host OS path separator.
            arcname = file_path.relative_to(plugin_dir).as_posix()
            archive.write(file_path, arcname=arcname)

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Package the Cloak plugin as a zip.")
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Output zip path (default: {_DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args()
    output = build_zip(output=args.output)
    size_kib = output.stat().st_size / 1024
    print(f"Built {output} ({size_kib:.1f} KiB)")  # noqa: T201 - CLI output


if __name__ == "__main__":
    main()
