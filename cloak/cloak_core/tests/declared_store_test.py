"""Declared-terms store — the growable in-window declared list (US2/FR-16).

Pure core (no buzz/Qt). Terms are raw ``category: term`` / bare lines; dedupe is by
the term portion, case- and whitespace-insensitive, so a name is never declared
twice. Reads are total (missing/corrupt → empty).
"""

from __future__ import annotations

from cloak_core.declared_store import (
    add_declared_term,
    read_declared_terms,
    remove_declared_term,
    write_declared_terms,
)


def test_empty_when_absent(tmp_path):
    assert read_declared_terms(tmp_path) == []


def test_add_and_persist(tmp_path):
    add_declared_term(tmp_path, "Karen")
    assert read_declared_terms(tmp_path) == ["Karen"]
    # A second store instance / read sees it (cross-transcript persistence).
    assert read_declared_terms(tmp_path) == ["Karen"]


def test_add_is_idempotent_by_canonical_term(tmp_path):
    add_declared_term(tmp_path, "Karen")
    add_declared_term(tmp_path, "  karen ")  # same term, different case/space
    assert read_declared_terms(tmp_path) == ["Karen"]


def test_add_dedupes_across_categories(tmp_path):
    add_declared_term(tmp_path, "person: Jane")
    add_declared_term(tmp_path, "Jane")  # same term portion → not added again
    assert read_declared_terms(tmp_path) == ["person: Jane"]


def test_categorized_line_is_kept_verbatim(tmp_path):
    add_declared_term(tmp_path, "project: Apollo")
    assert read_declared_terms(tmp_path) == ["project: Apollo"]


def test_remove_by_term(tmp_path):
    write_declared_terms(tmp_path, ["person: Jane", "Karen"])
    remaining = remove_declared_term(tmp_path, "jane")  # canonical, category-agnostic
    assert remaining == ["Karen"]
    assert read_declared_terms(tmp_path) == ["Karen"]


def test_write_drops_blank_lines(tmp_path):
    write_declared_terms(tmp_path, ["Karen", "  ", "", "Jane"])
    assert read_declared_terms(tmp_path) == ["Karen", "Jane"]


def test_corrupt_store_reads_empty(tmp_path):
    (tmp_path / "declared_terms.json").write_text("{bad", encoding="utf-8")
    assert read_declared_terms(tmp_path) == []
