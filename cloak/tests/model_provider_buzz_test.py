"""Host adapter for the suggestion model — structure, lazy imports, degradation.

The adapter is the only host-coupled piece of the suggestion tier. These tests
verify it without an ML environment: the module must import anywhere (heavy deps
are lazy), it must satisfy the ``ModelProvider`` port, and a load failure must
surface as an exception that the detector swallows. The real download + inference
are behind an opt-in test (set ``CLOAK_RUN_MODEL_TEST=1``) so CI never hits the
network or needs a GPU/large deps.
"""

from __future__ import annotations

import os

import pytest

from cloak_core.detectors.suggest import ModelSuggestionDetector
from cloak_core.model import TrustTier


def test_module_imports_without_ml_or_buzz():
    # gliner / buzz / huggingface_hub are lazy-imported, so this loads in the
    # plain core environment with none of them installed.
    import cloak_host.model_provider_buzz as module

    assert hasattr(module, "BuzzGlinerProvider")
    assert module.DEFAULT_GLINER_REPO


def test_provider_plugs_into_the_detector_port():
    from cloak_host.model_provider_buzz import BuzzGlinerProvider

    provider = BuzzGlinerProvider()
    assert hasattr(provider, "predict")
    detector = ModelSuggestionDetector(provider)
    assert detector.tier is TrustTier.SUGGESTED


def test_predict_propagates_a_load_failure(monkeypatch):
    from cloak_host.model_provider_buzz import BuzzGlinerProvider

    provider = BuzzGlinerProvider()

    def _boom():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(provider, "_ensure_model", _boom)
    with pytest.raises(RuntimeError):
        provider.predict("hello", ["person"])


def test_detector_swallows_adapter_load_failure(monkeypatch):
    # End-to-end of the graceful-degradation contract: the adapter raises, the
    # detector returns no suggestions rather than crashing the pipeline.
    from cloak_host.model_provider_buzz import BuzzGlinerProvider

    provider = BuzzGlinerProvider()

    def _boom():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(provider, "_ensure_model", _boom)
    assert ModelSuggestionDetector(provider).detect("Dana from Acme") == []


@pytest.mark.skipif(
    not os.environ.get("CLOAK_RUN_MODEL_TEST"),
    reason="opt-in: set CLOAK_RUN_MODEL_TEST=1 to download + run the real model",
)
def test_real_model_downloads_via_buzz_and_runs():
    """Slow, opt-in: fetches the real GLiNER model through Buzz and runs it on CPU.

    Requires ``gliner`` installed and network on first run; reused offline after.
    """
    from cloak_host.model_provider_buzz import BuzzGlinerProvider

    detector = ModelSuggestionDetector(BuzzGlinerProvider())
    found = detector.detect("Dana from Acme visited Berlin about Project Falcon.")
    types = {d.type for d in found}
    assert {"person", "org", "place"} & types
    for det in found:
        assert det.tier is TrustTier.SUGGESTED
