"""The product guarantees PG1–PG8, stated once, in one build-failing suite.

Each product guarantee (PG1–PG8) is asserted here explicitly, so the whole contract
is auditable in a single file and any regression **fails the build** (the DoD
requirement). The individual phases also exercise these behaviours in context; this
module is the consolidated, labelled statement of record.

Pure core: runs on system Python, no Qt. **No network** — and PG1 proves it by rigging
every network primitive to explode while the guaranteed path runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from sanitizer_core import persistence
from sanitizer_core.detectors.declared import DeclaredListDetector
from sanitizer_core.detectors.pii import PII_TYPES, pii_detectors
from sanitizer_core.model import Detection, Span, TrustTier
from sanitizer_core.restore import restore
from sanitizer_core.sanitizer import sanitize
from sanitizer_core.transcript import sanitize_transcript


@dataclass
class _Seg:
    start: int
    end: int
    text: str


class _MissesSecond:
    """Removes only the FIRST ``SECRET`` — the second survives, so the fail-closed
    gate must refuse to call the output clean (a stand-in for any recall miss)."""

    def detect(self, text: str) -> list[Detection]:
        index = text.find("SECRET")
        if index < 0:
            return []
        return [
            Detection(
                span=Span(index, index + 6),
                value="SECRET",
                type="secret",
                label="SECRET",
                tier=TrustTier.PII,
                reason="pattern",
                canonical="secret",
                restore="SECRET",
            )
        ]


# --- PG1 — Offline ----------------------------------------------------------
def test_pg1_guaranteed_path_makes_no_network_call(monkeypatch):
    """The full guaranteed path (declared + every PII type, per segment, with the
    fail-closed gate) completes with every network primitive rigged to explode."""
    import socket
    import urllib.request

    def _explode(*_args, **_kwargs):
        raise AssertionError("PG1 violated: the guaranteed path attempted network I/O")

    monkeypatch.setattr(socket, "socket", _explode)
    monkeypatch.setattr(socket, "create_connection", _explode)
    monkeypatch.setattr(socket, "getaddrinfo", _explode)
    monkeypatch.setattr(urllib.request, "urlopen", _explode)

    segments = [
        _Seg(0, 1000, "Call Jane at Acme, email jane@example.com"),
        _Seg(1000, 2000, "or ring 415-555-1212 about project Apollo"),
    ]
    detectors = [
        DeclaredListDetector(
            {"person": ["Jane"], "org": ["Acme"], "project": ["Apollo"]}
        ),
        *pii_detectors(PII_TYPES),
    ]

    result = sanitize_transcript(segments, detectors)

    assert result.clean  # completed without a network attempt
    for leak in ("Jane", "Acme", "Apollo", "jane@example.com", "415-555-1212"):
        assert leak not in result.scrubbed_text


# --- PG2 — No declared leak -------------------------------------------------
def test_pg2_no_declared_term_survives():
    result = sanitize("Call Jane at Acme", [DeclaredListDetector(["Jane", "Acme"])])
    assert result.clean
    assert "Jane" not in result.scrubbed
    assert "Acme" not in result.scrubbed


# --- PG3 — No structured-PII leak -------------------------------------------
def test_pg3_no_enabled_pii_survives():
    text = "mail a@b.com call 415-555-1212 ssn 123-45-6789 ip 10.0.0.1"
    result = sanitize(text, pii_detectors({"email", "phone", "ssn", "ip"}))
    assert result.clean
    for leak in ("a@b.com", "415-555-1212", "123-45-6789", "10.0.0.1"):
        assert leak not in result.scrubbed


# --- PG4 — Reversible -------------------------------------------------------
def test_pg4_restore_is_exact():
    result = sanitize("Jane briefed Jane", [DeclaredListDetector(["Jane"])])
    assert restore(result.scrubbed, result.key) == "Jane briefed Jane"


def test_pg4_reversible_through_a_markdown_reply():
    result = sanitize("Jane shipped Apollo", [DeclaredListDetector(["Jane", "Apollo"])])
    # The reply comes back with a placeholder emphasised; restore still reconstructs.
    reply = result.scrubbed.replace("{{TERM-1}}", "**{{TERM-1}}**")
    assert restore(reply, result.key) == "**Jane** shipped Apollo"


# --- PG5 — Timing preserved -------------------------------------------------
def test_pg5_segment_timing_is_untouched():
    segments = [_Seg(0, 1000, "Hi Jane"), _Seg(1000, 2500, "Bye Jane")]
    result = sanitize_transcript(segments, [DeclaredListDetector(["Jane"])])
    assert [(s.start, s.end) for s in result.segments] == [(0, 1000), (1000, 2500)]


# --- PG6 — Predictable removals ---------------------------------------------
def _guaranteed(text: str):
    return sanitize(
        text, [DeclaredListDetector(["Jane", "Apollo"]), *pii_detectors({"email"})]
    )


def test_pg6_same_input_yields_identical_guaranteed_removals():
    first = _guaranteed("Jane emailed a@b.com about Apollo")
    second = _guaranteed("Jane emailed a@b.com about Apollo")
    assert first.scrubbed == second.scrubbed
    assert first.key.entries == second.key.entries
    # Golden output — catches drift, not just non-determinism.
    assert first.scrubbed == "{{TERM-1}} emailed {{EMAIL-1}} about {{TERM-2}}"


# --- PG7 — Fail-closed ------------------------------------------------------
def test_pg7_fails_closed_when_a_guaranteed_term_survives():
    result = sanitize("SECRET and SECRET", [_MissesSecond()])
    assert result.clean is False  # never presented as clean...
    assert any(s.value == "SECRET" for s in result.survivors)  # ...survivor named


def test_pg7_a_leak_in_any_segment_fails_the_whole_transcript():
    segments = [_Seg(0, 1, "nothing here"), _Seg(1, 2, "SECRET and SECRET")]
    result = sanitize_transcript(segments, [_MissesSecond()])
    assert result.clean is False


# --- PG8 — The key is the secret --------------------------------------------
def test_pg8_scrubbed_output_never_embeds_a_secret():
    result = sanitize("Jane met Acme", [DeclaredListDetector(["Jane", "Acme"])])
    assert result.key.entries  # the mapping exists...
    for original in result.key.entries.values():
        assert original not in result.scrubbed  # ...but no real value is in the text


def test_pg8_key_persists_in_its_own_file(tmp_path):
    sanitization = sanitize_transcript(
        [_Seg(0, 1, "Jane")], [DeclaredListDetector(["Jane"])]
    )
    persistence.write_sidecar(tmp_path / "1", sanitization, {"clean": True})

    assert (tmp_path / "1" / persistence.KEY_FILE).is_file()  # a separate artifact
    sidecar = persistence.read_sidecar(tmp_path / "1")
    assert "Jane" not in sidecar.scrubbed_text  # the copyable text carries no secret
    assert "Jane" in sidecar.key.entries.values()  # the secret lives in the key
