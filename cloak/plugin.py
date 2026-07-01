"""Cloak — a reversible, offline sensitive-information sanitizer for Buzz.

This module is the thin :class:`BuzzPlugin` host glue: it declares Cloak's
identity + config, attaches Cloak's UI (a "Cloak" menu → review/restore) to the
main window using only public Qt APIs **without modifying Buzz**, and on
``on_complete`` runs the host-independent sanitizer over the finished transcript,
writing a sidecar keyed by ``transcription_id`` (the stored transcript is never
touched). All the safety-critical logic lives in ``cloak_core``; see ``DEV_NOTES``.

Buzz loads this file as a standalone module (``buzz_plugin_cloak``) by file
path, so the plugin's own packages (``cloak_core``, ``cloak_host``) are not
importable until the plugin root is placed on ``sys.path`` below.
"""

from __future__ import annotations

import logging
import os
import sys

# --- import bootstrap -------------------------------------------------------
# Buzz execs this file via ``importlib.spec_from_file_location`` — i.e. as a
# top-level module, not part of a package — so relative imports do not resolve.
# Putting the plugin root on ``sys.path`` lets ``import cloak_core`` /
# ``cloak_host`` work both inside Buzz and under pytest. See DEV_NOTES.md
# ("Import bootstrap & update caveat").
_PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from buzz.plugins.base import (  # noqa: E402 - import after sys.path bootstrap above
    BuzzPlugin,
    ConfigField,
    ConfigFieldType,
    PluginMetadata,
    plugin_gettext,
)

logger = logging.getLogger(__name__)

# Translator for user-facing strings (see ``cloak/locale/*.json``). Untranslated
# strings fall through unchanged, so missing entries are safe.
_ = plugin_gettext(__file__)


class CloakPlugin(BuzzPlugin):
    """Buzz plugin entry point for Cloak.

    Responsibilities:
      * declare plugin identity + config so Buzz can discover, install and list it;
      * attach Cloak's UI (menu → review/restore) to the host on the main thread;
      * on ``on_complete``, sanitize the finished transcript and write a sidecar.

    Assumes: instantiated on the Qt main thread by ``PluginManager.initialize``;
    ``on_complete`` runs on a background thread (no Qt touched there).
    Guarantees: ``__init__`` never raises (a UI-attach failure is logged and the
    plugin still loads); ``on_complete`` never raises into the host and never
    modifies the stored transcript — it only writes Cloak's own sidecar.
    """

    metadata = PluginMetadata(
        id="cloak",
        name=_("Cloak"),
        description=_(
            "Reversible, offline sanitizer for sensitive information in "
            "transcripts. Replace names, PII and codenames before sending text "
            "to a cloud LLM, then restore the originals from a local key."
        ),
        version="0.6.0",
        pip_dependencies=[],  # guaranteed path is dependency-free + offline
        config_fields=[
            ConfigField(
                key="declared_terms",
                label=_("Declared terms"),
                type=ConfigFieldType.TEXTAREA,
                default="",
                description=_(
                    "One per line. Prefix with a category for clearer placeholders, "
                    "e.g. 'person: Jane' or 'project: Apollo'."
                ),
                placeholder="person: Jane\nproject: Apollo",
            ),
            ConfigField(
                key="pii_email",
                label=_("Remove email addresses"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="pii_phone",
                label=_("Remove phone numbers"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="pii_credit_card",
                label=_("Remove credit-card numbers"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="pii_ssn",
                label=_("Remove Social Security numbers"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="pii_ip",
                label=_("Remove IP addresses"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="pii_url",
                label=_("Remove URLs"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="enable_suggestions",
                label=_("Suggest undeclared names/orgs (local model)"),
                type=ConfigFieldType.BOOL,
                default=False,
                description=_(
                    "Held for your review, never applied automatically. Downloads a "
                    "small model on first use via Buzz; requires the 'gliner' package."
                ),
            ),
        ],
    )

    def __init__(self) -> None:
        super().__init__()
        self._attach_ui()

    def on_complete(self, transcription_id, task, segments, context) -> None:
        """Sanitize the saved transcript and persist Cloak's sidecar.

        Runs on a background thread after the transcript is stored. Treats segments
        read-only and writes a sidecar keyed by ``transcription_id`` — the stored
        transcript is never modified (PG5). Any failure is contained so the host
        pipeline is never broken.
        """
        try:
            from cloak_host.pipeline import sanitize_to_sidecar
        except Exception:  # noqa: BLE001 - core/host layer may be unavailable
            logger.exception("Cloak: pipeline unavailable; skipping sanitization.")
            return
        try:
            _directory, result = sanitize_to_sidecar(
                transcription_id, segments, context.config
            )
        except Exception as exc:  # noqa: BLE001 - never break the host pipeline
            context.log.error(
                "Cloak: sanitization failed for %s: %s", transcription_id, exc
            )
            logger.exception("Cloak: sanitization failed.")
            return
        context.log.info(
            "Cloak: sanitized transcription %s — removed %d item(s), "
            "%d pending, clean=%s",
            transcription_id,
            result.removed_items,
            result.pending_items,
            result.clean,
        )

    @staticmethod
    def _attach_ui() -> None:
        """Attach Cloak's menu to Buzz's main window, if a GUI is running.

        Imported lazily so headless contexts (CLI, pytest without PyQt6) can load
        the plugin without a Qt dependency. Any failure is swallowed by design so
        plugin load never breaks.
        """
        try:
            from cloak_host.menu import attach_to_main_window
        except Exception:  # noqa: BLE001 - PyQt6/host UI may be unavailable
            logger.debug("Cloak: UI layer unavailable; running headless.")
            return
        try:
            attach_to_main_window()
        except Exception:  # noqa: BLE001 - never break plugin load on UI failure
            logger.exception("Cloak: failed to attach UI to the main window.")
