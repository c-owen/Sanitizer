"""The on_complete pipeline — detectors from config, sidecar write, no mutation.

Runs on system Python (no Qt; suggestions are off by default so no ML import). The
``on_complete`` test goes through Buzz's real loader, so it skips where ``buzz`` is
unavailable. Sidecar writes are redirected to a temp dir — never the real cache.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pytest

from cloak_core import (
    Preferences,
    add_declared_term,
    persistence,
    write_preferences,
)
from cloak_core.detectors.suggest import ModelSuggestionDetector, RawEntity
from cloak_host.pipeline import build_detectors, sanitize_to_sidecar

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLOAK_DIR = _REPO_ROOT / "cloak"


@dataclass
class _Seg:
    start: int
    end: int
    text: str


class _Ctx:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("cloak.test")
        self.transcription_service = None
        self.settings = None


# --- build_detectors --------------------------------------------------------
def test_declared_terms_become_a_detector():
    detectors = build_detectors({"declared_terms": "person: Jane\nBob"})
    names = [type(d).__name__ for d in detectors]
    assert names.count("DeclaredListDetector") == 1
    assert "EmailDetector" in names  # PII defaults on


def test_suggestions_off_by_default():
    names = [type(d).__name__ for d in build_detectors({"declared_terms": "Jane"})]
    assert "ModelSuggestionDetector" not in names


def test_suggestions_on_adds_the_detector():
    names = [type(d).__name__ for d in build_detectors({"enable_suggestions": True})]
    assert "ModelSuggestionDetector" in names


# --- sanitize_to_sidecar ----------------------------------------------------
def test_writes_a_readable_sidecar(tmp_path):
    segments = [_Seg(0, 1000, "Call Jane"), _Seg(1000, 2000, "bye Jane")]
    directory, result = sanitize_to_sidecar(
        "42", segments, {"declared_terms": "Jane"}, base_dir=str(tmp_path)
    )
    assert result.removed_items == 1
    sidecar = persistence.read_sidecar(directory)
    assert sidecar is not None
    assert "Jane" not in sidecar.scrubbed_text
    assert sidecar.meta["transcription_id"] == "42"
    assert sidecar.meta["clean"] is True
    assert sidecar.meta["segment_count"] == 2


def test_segments_are_not_mutated(tmp_path):
    segments = [_Seg(0, 1, "Call Jane now")]
    sanitize_to_sidecar(
        "1", segments, {"declared_terms": "Jane"}, base_dir=str(tmp_path)
    )
    assert segments[0].text == "Call Jane now"  # read-only (PG5)


def test_pii_toggle_disables_only_that_type(tmp_path):
    segments = [_Seg(0, 1, "mail a@b.com call 415-555-1212")]
    _dir, result = sanitize_to_sidecar(
        "1", segments, {"pii_phone": False}, base_dir=str(tmp_path)
    )
    assert "a@b.com" not in result.scrubbed_text  # email on → removed
    assert "415-555-1212" in result.scrubbed_text  # phone off → kept


def test_meta_records_settings_snapshot(tmp_path):
    _dir, _result = sanitize_to_sidecar(
        "1", [_Seg(0, 1, "x")], {"pii_url": False}, base_dir=str(tmp_path)
    )
    sidecar = persistence.read_sidecar(tmp_path / "1")
    assert "url" not in sidecar.meta["settings"]["pii"]
    assert sidecar.meta["settings"]["suggestions"] is False


# --- on_complete through the real plugin ------------------------------------
def test_on_complete_writes_sidecar_without_touching_segments(tmp_path, monkeypatch):
    loader = pytest.importorskip("buzz.plugins.loader")
    plugin = loader.load_plugin_from_dir(str(_CLOAK_DIR))

    # Redirect the real cache path to the temp dir.
    import cloak_host.paths as paths

    monkeypatch.setattr(paths, "cloak_data_dir", lambda: str(tmp_path))

    segments = [_Seg(0, 1, "Call Jane"), _Seg(1, 2, "bye")]
    plugin.on_complete("99", None, segments, _Ctx({"declared_terms": "Jane"}))

    sidecar = persistence.read_sidecar(tmp_path / "99")
    assert sidecar is not None
    assert "Jane" not in sidecar.scrubbed_text
    assert segments[0].text == "Call Jane"  # transcript never mutated


def test_on_complete_never_raises_into_host(tmp_path, monkeypatch):
    loader = pytest.importorskip("buzz.plugins.loader")
    plugin = loader.load_plugin_from_dir(str(_CLOAK_DIR))

    # Make the pipeline blow up; on_complete must swallow it.
    import cloak_host.pipeline as pipeline

    def _boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(pipeline, "sanitize_to_sidecar", _boom)
    plugin.on_complete("1", None, [_Seg(0, 1, "x")], _Ctx({}))  # must not raise


# --- Step D: unioned declared store (US2) -----------------------------------
def test_build_detectors_unions_the_declared_store(tmp_path):
    add_declared_term(tmp_path, "person: Jane")  # in Cloak's store, not the config
    detectors = build_detectors({"declared_terms": "Bob"}, data_dir=str(tmp_path))
    declared = next(d for d in detectors if type(d).__name__ == "DeclaredListDetector")
    hits = {d.value for d in declared.detect("Jane and Bob")}
    assert hits == {"Jane", "Bob"}  # config term + stored term together


def test_stored_term_is_redacted_end_to_end(tmp_path):
    add_declared_term(tmp_path, "Karen")
    _dir, result = sanitize_to_sidecar(
        "1", [_Seg(0, 1, "Call Karen")], {}, base_dir=str(tmp_path)
    )
    assert "Karen" not in result.scrubbed_text  # picked up from the store next run


# --- Step D: informed auto-apply (FR-12) ------------------------------------
class _StubProvider:
    """A tiny model stand-in: flags one fixed surface, no ML/network."""

    def __init__(self, surface, label):
        self._surface, self._label = surface, label

    def predict(self, text, labels):
        index = text.find(self._surface)
        if index < 0:
            return []
        return [RawEntity(index, index + len(self._surface), self._label, 0.9)]


def _inject_stub_suggestion(monkeypatch, surface="Acme", label="organization"):
    """Make ``build_detectors`` also emit a stub suggestion (bare-name lookup, so
    patching the module attribute reaches the internal call in sanitize_to_sidecar)."""
    import cloak_host.pipeline as pipeline

    real = pipeline.build_detectors

    def patched(config, *, data_dir=None):
        detectors = real(config, data_dir=data_dir)
        detectors.append(ModelSuggestionDetector(_StubProvider(surface, label)))
        return detectors

    monkeypatch.setattr(pipeline, "build_detectors", patched)


def test_auto_apply_off_by_default_holds_suggestion(tmp_path, monkeypatch):
    _inject_stub_suggestion(monkeypatch)
    _dir, result = sanitize_to_sidecar(
        "1",
        [_Seg(0, 1, "Jane at Acme")],
        {"declared_terms": "Jane"},
        base_dir=str(tmp_path),
    )
    assert "Acme" in result.scrubbed_text  # held, not applied (FR-9 default)
    assert result.pending_items == 1
    sidecar = persistence.read_sidecar(tmp_path / "1")
    assert sidecar.meta["auto_applied_suggestions"] == 0


def test_auto_apply_applies_when_opted_in_and_reviewed(tmp_path, monkeypatch):
    _inject_stub_suggestion(monkeypatch)
    write_preferences(
        tmp_path, Preferences(has_reviewed=True, auto_apply_suggestions=True)
    )
    _dir, result = sanitize_to_sidecar(
        "1",
        [_Seg(0, 1, "Jane at Acme")],
        {"declared_terms": "Jane"},
        base_dir=str(tmp_path),
    )
    assert "Acme" not in result.scrubbed_text  # applied on the informed opt-in
    assert "Acme" in result.key.entries.values()
    sidecar = persistence.read_sidecar(tmp_path / "1")
    assert sidecar.meta["auto_applied_suggestions"] == 1


def test_auto_apply_is_gated_on_having_reviewed(tmp_path, monkeypatch):
    _inject_stub_suggestion(monkeypatch)
    # Opted in, but never reviewed → the informed gate must still hold it.
    write_preferences(
        tmp_path, Preferences(has_reviewed=False, auto_apply_suggestions=True)
    )
    _dir, result = sanitize_to_sidecar(
        "1",
        [_Seg(0, 1, "Jane at Acme")],
        {"declared_terms": "Jane"},
        base_dir=str(tmp_path),
    )
    assert "Acme" in result.scrubbed_text  # still held — gate not satisfied
