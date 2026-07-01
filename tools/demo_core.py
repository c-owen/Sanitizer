"""Tiny demo of Cloak's host-independent core — sanitize, show the key, restore.

No Buzz, no Qt, no ML deps. Run with plain system Python::

    python tools/demo_core.py
    python tools/demo_core.py --terms "Jane,Bob" --text "Jane called Bob about Jane"

This exercises the same `cloak_core` code the plugin will use, so you can watch
declared terms become consistent placeholders, see the (secret) key, and confirm
the round trip restores the original.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cloak")
)

from cloak_core import (  # noqa: E402
    DeclaredListDetector,
    DecisionState,
    ModelSuggestionDetector,
    RawEntity,
    pii_detectors,
    restore,
    sanitize,
)


class _HeuristicProvider:
    """A crude, offline stand-in for the real zero-shot model — for demoing the
    suggestion tier only. Flags capitalized words as possible names so you can see
    suggestions surface as PENDING (held for review, never auto-applied). The real
    plugin uses ``cloak_host.model_provider_buzz`` instead; this ships nowhere.
    """

    _WORD = re.compile(r"\b[A-Z][a-z]{2,}\b")

    def predict(self, text: str, labels):  # noqa: ARG002 - labels are a hint
        return [
            RawEntity(m.start(), m.end(), "person", 0.9)
            for m in self._WORD.finditer(text)
        ]


_SAMPLE_TERMS = {"person": ["Jane", "Bob"], "project": ["Project Apollo"]}
_SAMPLE_TEXT = (
    "Jane told Bob about Project Apollo. "
    "Email contact@example.com or call (415) 555-1212."
)


def _parse_terms(raw: str) -> dict[str, list[str]]:
    """Parse ``--terms``: comma-separated ``category:term`` (bare → ``term``)."""
    by_category: dict[str, list[str]] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        category, term = item.split(":", 1) if ":" in item else ("term", item)
        category, term = category.strip().lower(), term.strip()
        if term:
            by_category.setdefault(category, []).append(term)
    return by_category


def main() -> None:
    # Windows consoles default to cp1252, which can't encode the placeholder
    # brackets (⟦ ⟧). Force UTF-8 so the demo prints; the plugin's real output
    # goes to UTF-8 sinks (Qt, clipboard, markdown), so this is a console-only fix.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="Demo Cloak's sanitization core.")
    parser.add_argument("--terms", help="Comma-separated declared terms.")
    parser.add_argument("--text", help="Text to sanitize.")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Add a heuristic suggestion tier (held for review, not applied).",
    )
    args = parser.parse_args()

    terms = _parse_terms(args.terms) if args.terms else _SAMPLE_TERMS
    text = args.text if args.text else _SAMPLE_TEXT

    detectors = [DeclaredListDetector(terms), *pii_detectors()]
    if args.suggest:
        detectors.append(ModelSuggestionDetector(_HeuristicProvider()))
    result = sanitize(text, detectors)
    restored = restore(result.scrubbed, result.key)

    print("declared terms :", terms)
    print("original       :", text)
    print("scrubbed       :", result.scrubbed)
    print("key (the secret):", result.key.entries)
    print("restored       :", restored)
    print("round-trips    :", restored == text)
    print("clean (gate)   :", result.clean)
    if not result.clean:
        print("SURVIVORS      :", [s.value for s in result.survivors])
    print("decisions:")
    for decision in result.decisions:
        # PENDING suggestions are held for review: no placeholder, left in cleartext.
        token = (
            decision.placeholder
            if decision.state is DecisionState.APPROVED
            else f"[{decision.state.value}]"
        )
        print(
            f"  {token} = {decision.original!r}"
            f"  ({decision.count}x · {decision.reason})"
        )


if __name__ == "__main__":
    main()
