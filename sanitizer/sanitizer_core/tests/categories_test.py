"""Semantic placeholder labels — categories + lettered entity indices (G3)."""

from __future__ import annotations

import pytest

from sanitizer_core.categories import CATEGORIES, label_for
from sanitizer_core.detectors.declared import DeclaredListDetector
from sanitizer_core.placeholders import BraceScheme
from sanitizer_core.sanitizer import sanitize


# --- category → label -------------------------------------------------------
def test_known_categories_map_to_labels():
    assert label_for("person") == "PERSON"
    assert label_for("project") == "PROJECT"
    assert label_for("org") == "ORG"
    assert label_for("place") == "PLACE"


def test_unknown_category_uppercases():
    assert label_for("vehicle") == "VEHICLE"


def test_categories_tuple():
    assert set(CATEGORIES) == {"person", "org", "project", "place"}


# --- scheme: letters for entities, numbers for the rest ---------------------
@pytest.mark.parametrize(
    "index,letters",
    [(1, "A"), (2, "B"), (26, "Z"), (27, "AA"), (52, "AZ"), (53, "BA")],
)
def test_entity_labels_use_letters(index, letters):
    assert BraceScheme().format("PERSON", index) == f"{{{{PERSON-{letters}}}}}"


def test_non_entity_labels_use_numbers():
    assert BraceScheme().format("TERM", 1) == "{{TERM-1}}"
    assert BraceScheme().format("EMAIL", 2) == "{{EMAIL-2}}"


# --- declared detector with categories --------------------------------------
def test_categorized_terms_get_category_labels():
    detector = DeclaredListDetector({"person": ["Jane"], "project": ["Apollo"]})
    by_value = {d.value: d for d in detector.detect("Jane on Apollo")}
    assert by_value["Jane"].label == "PERSON"
    assert by_value["Jane"].type == "person"
    assert by_value["Apollo"].label == "PROJECT"


def test_bare_list_stays_generic_term():
    det = DeclaredListDetector(["Jane"]).detect("Jane")[0]
    assert det.label == "TERM"
    assert det.type == "term"


# --- end to end -------------------------------------------------------------
def test_sanitize_uses_semantic_lettered_placeholders():
    terms = {"person": ["Jane", "Bob"], "project": ["Project Apollo"]}
    result = sanitize(
        "Jane told Bob about Project Apollo.", [DeclaredListDetector(terms)]
    )
    assert result.scrubbed == ("{{PERSON-A}} told {{PERSON-B}} about {{PROJECT-A}}.")
    assert result.key.entries == {
        "{{PERSON-A}}": "Jane",
        "{{PERSON-B}}": "Bob",
        "{{PROJECT-A}}": "Project Apollo",
    }
