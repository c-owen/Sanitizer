"""Sanitizer — declared-tier replacement, consistency, determinism, empty state."""

from __future__ import annotations

from cloak_core.detectors.declared import DeclaredListDetector
from cloak_core.model import DecisionState, TrustTier
from cloak_core.sanitizer import sanitize


def _sanitize(text, terms):
    return sanitize(text, [DeclaredListDetector(terms)])


def test_replaces_declared_term():
    result = _sanitize("Call Jane now", ["Jane"])
    assert "Jane" not in result.scrubbed
    assert result.scrubbed == "Call {{TERM-1}} now"


def test_consistent_placeholder_across_occurrences():
    result = _sanitize("Jane met Jane", ["Jane"])
    assert len(result.decisions) == 1
    placeholder = result.decisions[0].placeholder
    assert result.scrubbed == f"{placeholder} met {placeholder}"
    assert result.decisions[0].count == 2


def test_distinct_items_get_distinct_placeholders():
    result = _sanitize("Jane and Bob", ["Jane", "Bob"])
    placeholders = {d.placeholder for d in result.decisions}
    assert len(placeholders) == 2


def test_declared_is_auto_approved():
    decision = _sanitize("Jane", ["Jane"]).decisions[0]
    assert decision.state == DecisionState.APPROVED
    assert decision.tier == TrustTier.DECLARED
    assert decision.reason == "matched your list"


def test_substring_safety_end_to_end():
    result = _sanitize("Janet is not Jane", ["Jane"])
    assert "Janet" in result.scrubbed
    assert result.scrubbed == "Janet is not {{TERM-1}}"


def test_possessive_end_to_end():
    assert _sanitize("Jane's idea", ["Jane"]).scrubbed == "{{TERM-1}}'s idea"


def test_empty_state_when_nothing_detected():
    result = _sanitize("nothing sensitive here", ["Jane"])
    assert result.is_empty
    assert result.scrubbed == "nothing sensitive here"
    assert result.key.entries == {}


def test_same_input_is_deterministic():
    a = _sanitize("Jane and Bob and Jane", ["Jane", "Bob"])
    b = _sanitize("Jane and Bob and Jane", ["Jane", "Bob"])
    assert a.scrubbed == b.scrubbed
    assert a.key.entries == b.key.entries


def test_key_reverses_every_replacement():
    result = _sanitize("Jane and Bob", ["Jane", "Bob"])
    assert set(result.key.entries.values()) == {"Jane", "Bob"}
    for placeholder in result.key.entries:
        assert placeholder in result.scrubbed


def test_placeholder_order_follows_first_appearance():
    result = _sanitize("Bob then Jane", ["Jane", "Bob"])
    # Bob appears first → TERM-1; Jane second → TERM-2.
    assert result.key.entries["{{TERM-1}}"] == "Bob"
    assert result.key.entries["{{TERM-2}}"] == "Jane"


def test_shared_vault_keeps_placeholders_consistent_across_texts():
    from cloak_core.vault import Vault

    vault = Vault()
    detectors = [DeclaredListDetector(["Jane"])]
    first = sanitize("Jane here", detectors, vault=vault)
    second = sanitize("and Jane there", detectors, vault=vault)
    # Same person across two separate texts → same placeholder.
    assert first.decisions[0].placeholder == second.decisions[0].placeholder
