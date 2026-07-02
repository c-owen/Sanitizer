"""Where Sanitizer keeps its sidecars — inside Buzz's cache, beside Buzz's own data.

Host-only: this is the single place that knows the on-disk location, so the pure
core never hard-codes a path (it takes the directory injected). Mirrors Buzz's own
layout (``<user_cache_dir>/Buzz/plugins`` for plugins) with a sibling
``plugins_data/sanitizer`` for per-transcription sidecars.
"""

from __future__ import annotations

import os

# Sub-path under the Buzz cache dir; sibling of Buzz's own ``plugins`` folder.
_DATA_SUBDIR = ("plugins_data", "sanitizer")


def sanitizer_data_dir() -> str:
    """Base directory for all Sanitizer sidecars (created lazily by writers)."""
    from platformdirs import user_cache_dir  # Buzz dependency; import lazily

    return os.path.join(user_cache_dir("Buzz"), *_DATA_SUBDIR)


def sidecar_dir(transcription_id) -> str:
    """Directory holding the sidecar for one transcription."""
    return os.path.join(sanitizer_data_dir(), str(transcription_id))
