"""Shared pytest setup for Cloak's host-integration tests.

Adds the plugin root and the Buzz package root to ``sys.path`` so that
``import cloak_core`` / ``cloak_host`` (and ``import buzz...``) resolve the same
way they do when Buzz loads the plugin at runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]  # .../cloak
_REPO_ROOT = _PLUGIN_ROOT.parent  # .../buzz-plugin
_BUZZ_PKG_ROOT = _REPO_ROOT / "buzz"  # dir containing the importable ``buzz`` pkg

for _path in (_PLUGIN_ROOT, _BUZZ_PKG_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
