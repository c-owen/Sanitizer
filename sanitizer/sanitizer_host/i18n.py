"""Localization helper shared by Sanitizer's host-side UI.

Wraps Buzz's :func:`plugin_gettext` and points it at the plugin root's
``locale`` folder (one level up from this package) so every UI module uses a
single translator. Untranslated strings fall through unchanged, so the UI works
even with empty locale files.
"""

import os

from buzz.plugins.base import plugin_gettext

# ``plugin_gettext`` locates ``locale/`` next to the file path it is handed. This
# package lives in ``<plugin_root>/sanitizer_host/``; point it at the plugin root by
# referencing the entry module there.
_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Import as: ``from sanitizer_host.i18n import gettext as _``
gettext = plugin_gettext(os.path.join(_PLUGIN_ROOT, "plugin.py"))
