"""FR-14 — extensible without touching existing code.

Living proof that a third party can add a **new detector** *and* a **new format
handler** using only the public seams (the ``Detector`` and ``FormatHandler``
protocols) and have them work through the unmodified sanitizer, fail-closed gate and
restore. Nothing in ``cloak_core`` is edited to make this pass — both classes live
entirely in this test module, yet they compose with the shipped machinery.
"""

from __future__ import annotations

import re

from cloak_core.detectors.declared import DeclaredListDetector
from cloak_core.model import Detection, Span, TrustTier
from cloak_core.restore import restore
from cloak_core.sanitizer import sanitize


class MacAddressDetector:
    """A new guaranteed detector (MAC addresses) added purely by implementing the
    ``Detector`` protocol — never registered in ``detectors/pii.py``."""

    _RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")

    def detect(self, text: str) -> list[Detection]:
        return [
            Detection(
                span=Span(match.start(), match.end()),
                value=match.group(),
                type="mac",
                label="MAC",
                tier=TrustTier.PII,
                reason="looks like a MAC address",
                canonical=match.group().lower(),
                restore=match.group(),
            )
            for match in self._RE.finditer(text)
        ]


class HtmlPreHandler:
    """A new ``FormatHandler`` (HTML ``<pre>`` block) added without touching
    ``formats/`` — serialize wraps, parse unwraps, placeholders survive intact."""

    name = "html"

    def serialize(self, text: str) -> str:
        return f"<pre>{text}</pre>"

    def parse(self, text: str) -> str:
        return re.sub(r"^<pre>|</pre>$", "", text)


def test_new_detector_plugs_into_the_unmodified_sanitizer():
    result = sanitize("device 00:1A:2B:3C:4D:5E online", [MacAddressDetector()])

    assert "00:1A:2B:3C:4D:5E" not in result.scrubbed  # removed
    assert result.clean  # the fail-closed gate re-checked the brand-new detector
    assert restore(result.scrubbed, result.key) == "device 00:1A:2B:3C:4D:5E online"


def test_new_detector_composes_with_the_shipped_ones():
    result = sanitize(
        "Jane on 00:1A:2B:3C:4D:5E",
        [DeclaredListDetector(["Jane"]), MacAddressDetector()],
    )
    assert "Jane" not in result.scrubbed  # existing detector still works
    assert "00:1A:2B:3C:4D:5E" not in result.scrubbed  # new one works alongside it


def test_new_format_handler_round_trips_through_restore():
    result = sanitize("Jane shipped Apollo", [DeclaredListDetector(["Jane", "Apollo"])])
    handler = HtmlPreHandler()

    wire = handler.serialize(result.scrubbed)  # what leaves, in the new format
    assert wire.startswith("<pre>") and wire.endswith("</pre>")
    returned = handler.parse(wire)  # what comes back from the LLM

    assert restore(returned, result.key) == "Jane shipped Apollo"
