"""Vault — consistent, injective, reversible placeholder allocation (FR-3, PG4)."""

from __future__ import annotations

from sanitizer_core.vault import Vault


def test_same_canonical_returns_same_placeholder():
    vault = Vault()
    first = vault.placeholder_for("jane", "TERM", "Jane")
    again = vault.placeholder_for("jane", "TERM", "Jane")
    assert first == again


def test_distinct_canonicals_get_distinct_placeholders():
    vault = Vault()
    a = vault.placeholder_for("jane", "TERM", "Jane")
    b = vault.placeholder_for("bob", "TERM", "Bob")
    assert a != b


def test_key_maps_placeholder_back_to_original():
    vault = Vault()
    placeholder = vault.placeholder_for("jane", "TERM", "Jane")
    assert vault.key().original_for(placeholder) == "Jane"


def test_counters_are_per_label():
    vault = Vault()
    p_term1 = vault.placeholder_for("jane", "TERM", "Jane")
    p_term2 = vault.placeholder_for("bob", "TERM", "Bob")
    p_phone1 = vault.placeholder_for("n", "PHONE", "n")
    assert "TERM-1" in p_term1
    assert "TERM-2" in p_term2
    assert "PHONE-1" in p_phone1


def test_default_scheme_uses_braces():
    assert Vault().placeholder_for("jane", "TERM", "Jane") == "{{TERM-1}}"


def test_key_is_a_snapshot():
    vault = Vault()
    vault.placeholder_for("jane", "TERM", "Jane")
    snapshot = vault.key()
    vault.placeholder_for("bob", "TERM", "Bob")
    # The earlier key snapshot is unaffected by later allocations.
    assert len(snapshot.entries) == 1
