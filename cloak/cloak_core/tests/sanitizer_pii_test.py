"""Sanitizer with PII + verification — clean flag, fail-closed, overlap, PGs."""

from __future__ import annotations

from cloak_core.detectors.declared import DeclaredListDetector
from cloak_core.detectors.pii import pii_detectors
from cloak_core.model import Detection, Span, TrustTier
from cloak_core.restore import restore
from cloak_core.sanitizer import sanitize


def _all(terms):
    return [DeclaredListDetector(terms), *pii_detectors()]


def test_declared_and_pii_together_are_clean():
    text = "Jane's email is contact@example.com and phone 415-555-1212."
    result = sanitize(text, _all(["Jane"]))

    assert result.clean is True
    assert result.survivors == []
    assert "Jane" not in result.scrubbed
    assert "contact@example.com" not in result.scrubbed
    assert "415-555-1212" not in result.scrubbed
    assert {"TERM", "EMAIL", "PHONE"} <= {d.label for d in result.decisions}


def test_round_trip_with_pii():
    text = "Email contact@example.com or call 415-555-1212."
    result = sanitize(text, pii_detectors())
    assert restore(result.scrubbed, result.key) == text


def test_no_enabled_pii_survives():  # PG3
    text = "a@b.com 192.168.0.1 123-45-6789 4111 1111 1111 1111 http://x.com"
    result = sanitize(text, pii_detectors())

    assert result.clean is True
    for original in ("a@b.com", "192.168.0.1", "123-45-6789", "http://x.com"):
        assert original not in result.scrubbed


def test_determinism_with_pii():  # PG6
    text = "Jane a@b.com a@b.com 415-555-1212"
    first = sanitize(text, _all(["Jane"]))
    second = sanitize(text, _all(["Jane"]))
    assert first.scrubbed == second.scrubbed
    assert first.key.entries == second.key.entries


def test_repeated_pii_shares_one_placeholder():  # FR-3
    result = sanitize("mail a@b.com then a@b.com", pii_detectors({"email"}))
    assert result.scrubbed.count("{{EMAIL-1}}") == 2
    assert len(result.decisions) == 1


def test_disabled_type_is_left_untouched():  # FR-2
    result = sanitize("mail a@b.com call 415-555-1212", pii_detectors({"email"}))
    assert "{{EMAIL-1}}" in result.scrubbed
    assert "415-555-1212" in result.scrubbed  # phone disabled → untouched
    assert result.clean is True  # clean w.r.t. the enabled set


class _MissesSecondDetector:
    """Detects only the first 'SECRET' — a recall miss the gate must catch."""

    def detect(self, text):
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


def test_fails_closed_when_an_item_survives():  # PG7
    result = sanitize("SECRET and SECRET", [_MissesSecondDetector()])
    assert result.clean is False
    assert any(s.value == "SECRET" for s in result.survivors)


def test_name_inside_email_leaves_no_fragment():  # overlap / containment
    result = sanitize("write jane@acme.com", _all(["jane"]))
    assert result.clean is True
    assert "@acme.com" not in result.scrubbed  # the whole email won the overlap
    assert "EMAIL" in {d.label for d in result.decisions}
