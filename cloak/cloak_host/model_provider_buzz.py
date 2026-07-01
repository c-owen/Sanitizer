"""A :class:`~cloak_core.detectors.suggest.ModelProvider` backed by GLiNER, with
the model fetched on first use through Buzz's own downloader (FR-13).

This is the **host adapter** for the suggestion tier: it is the only place that
touches an ML library or Buzz, so ``cloak_core`` stays host-independent. The model
is a small zero-shot NER model that:

* is **downloaded on first use** via Buzz's ``download_from_huggingface`` into the
  shared model cache (``~/.cache/Buzz/models``) — nothing is bundled (FR-13);
* is **reused offline** thereafter (``local_files_only``);
* runs on **CPU**, cross-platform (FR-15).

All heavy imports (``gliner``, ``buzz``, ``huggingface_hub``) are **lazy** — inside
the methods that need them — so this module imports cleanly in any environment
(headless, no ML deps) and only pays for the model when a suggestion is actually
requested. The real download + inference are exercised by the opt-in integration
test (set ``CLOAK_RUN_MODEL_TEST=1``); unit tests inject a stub provider instead.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Sequence

from cloak_core.detectors.suggest import RawEntity

logger = logging.getLogger(__name__)

# Multilingual zero-shot NER (mDeBERTa backbone) so suggestions work in whatever
# language Buzz transcribed. Swappable behind the port (FR-14). The GLiNER *code* is
# vendored in ``cloak/_vendor`` (no pip install); only these *weights* download, on
# demand, via Buzz's own HuggingFace downloader (FR-13).
DEFAULT_GLINER_REPO = "urchade/gliner_multi-v2.1"

# Files to pull for a GLiNER repo. Generous on purpose (repos are small); tune if
# the chosen model needs more. Drives both the Buzz download and the offline check.
_GLINER_PATTERNS = [
    "*.json",
    "*.txt",
    "*.bin",
    "*.safetensors",
    "*.model",
    "*.pt",
    "tokenizer*",
    "spm*",
]

# GLiNER's multilingual weights are self-contained, but its config points the
# *tokenizer* and *encoder config* at a base backbone (e.g. microsoft/mdeberta-v3-base)
# that is NOT bundled in the gliner repo. We fetch those small files (config +
# tokenizer) too — but never the base *weights* (gliner ships its own fine-tuned
# encoder). Without them, loading reaches huggingface.co for the tokenizer → the
# "couldn't connect ... couldn't find in cache" failure.
_BASE_PATTERNS = [
    "config.json",
    "tokenizer*",
    "*.model",
    "spm*",
    "sentencepiece*",
    "special_tokens_map.json",
    "added_tokens.json",
    "vocab*",
    "merges.txt",
]


def _base_model_name(gliner_dir: str) -> str | None:
    """The backbone model named in the gliner repo's config (its tokenizer + encoder
    config live there, not in the gliner repo). ``None`` if it can't be read."""
    import json

    try:
        path = os.path.join(gliner_dir, "gliner_config.json")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle).get("model_name") or None
    except (OSError, ValueError):
        return None


def _ensure_vendor_on_path() -> None:
    """Put Cloak's bundled third-party dir on ``sys.path`` so the vendored GLiNER
    imports with no pip install (see ``cloak/_vendor/``). No-op if already present
    or absent. GLiNER is pure-Python and its heavy deps (torch/transformers/…) are
    already in Buzz, so the import only needs the vendor directory on the path.
    """
    vendor = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_vendor"
    )
    if os.path.isdir(vendor) and vendor not in sys.path:
        sys.path.insert(0, vendor)


class _NullProgress:
    """Stand-in for Buzz's ``progress`` Qt signal when fetching headlessly."""

    def emit(self, *_args, **_kwargs) -> None:
        return None


class BuzzGlinerProvider:
    """Runs GLiNER locally; fetches the model via Buzz on first use (FR-13/FR-15).

    Guarantees: ``predict`` returns spans that index the given text, scored in
    ``[0, 1]``; the model loads once (cached) and runs on CPU. ``labels`` are the
    zero-shot entity types to look for. Raises ``RuntimeError`` if the model can't
    be fetched or loaded — the :class:`ModelSuggestionDetector` swallows that and
    degrades to no suggestions, so the guaranteed path is never affected.
    """

    def __init__(self, repo_id: str = DEFAULT_GLINER_REPO, *, floor: float = 0.3):
        self._repo_id = repo_id
        # A permissive floor: the detector applies the authoritative cutoff, this
        # only avoids shipping a flood of near-zero-score candidates to it.
        self._floor = floor
        self._model = None

    def predict(self, text: str, labels: Sequence[str]) -> list[RawEntity]:
        model = self._ensure_model()
        raw = model.predict_entities(text, list(labels), threshold=self._floor)
        entities: list[RawEntity] = []
        for item in raw:
            try:
                entities.append(
                    RawEntity(
                        start=int(item["start"]),
                        end=int(item["end"]),
                        label=str(item["label"]),
                        score=float(item.get("score", 1.0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return entities

    def model_present(self) -> bool:
        """True if the GLiNER repo is already cached (first call won't download it)."""
        try:
            self._cached(self._repo_id, _GLINER_PATTERNS)
        except Exception:  # noqa: BLE001 - any failure means "not available offline"
            return False
        return True

    # --- internals (the lazy, host-coupled bits) ----------------------------
    def _ensure_model(self):
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def _load_model(self):
        from buzz.model_loader import model_root_dir  # lazy host import

        gliner_dir = self._ensure_downloaded()
        _ensure_vendor_on_path()  # make the bundled gliner importable (no pip)
        from gliner import GLiNER  # lazy heavy import (vendored in cloak/_vendor)

        # Load the gliner files from the local snapshot dir — an existing path makes
        # GLiNER's _download_model skip all hub access for them — and let it pull the
        # *base* tokenizer + encoder config from Buzz's cache (fetched in
        # _ensure_downloaded) by threading cache_dir + local_files_only. Passing the
        # repo id instead, or omitting these, makes GLiNER re-resolve the backbone
        # online → the "couldn't connect to huggingface.co" failure.
        try:
            model = GLiNER.from_pretrained(
                gliner_dir, cache_dir=model_root_dir, local_files_only=True
            )
        except TypeError:  # older/newer GLiNER missing one of these kwargs
            model = GLiNER.from_pretrained(gliner_dir, cache_dir=model_root_dir)
        try:
            model.to("cpu")
        except Exception:  # noqa: BLE001 - some builds manage device placement
            logger.debug("GLiNER.to('cpu') not applicable for this build")
        return model

    def _ensure_downloaded(self) -> str:
        """Ensure the GLiNER repo **and** its base backbone's tokenizer/config are
        cached; return the local GLiNER snapshot directory.

        gliner_multi loads its tokenizer + encoder config from the base model named in
        ``gliner_config.json`` (not bundled), so those are fetched too — but never the
        base *weights* (the fine-tuned encoder weights ship in the gliner repo).
        """
        gliner_dir = self._ensure_repo(self._repo_id, _GLINER_PATTERNS)
        base = _base_model_name(gliner_dir)
        if base and base != self._repo_id:
            try:
                self._ensure_repo(base, _BASE_PATTERNS)
            except Exception:  # noqa: BLE001 - best-effort; a real gap surfaces at load
                logger.exception("Cloak: base backbone %s could not be fetched", base)
        return gliner_dir

    def _ensure_repo(self, repo_id: str, patterns: list[str]) -> str:
        """Local snapshot dir for ``repo_id``, fetching via Buzz if not cached."""
        try:
            return self._cached(repo_id, patterns)
        except Exception:  # noqa: BLE001 - not cached yet; fetch via Buzz below
            pass

        from buzz.model_loader import download_from_huggingface  # lazy host import

        logger.info("Cloak: fetching %s via Buzz", repo_id)
        path = download_from_huggingface(
            repo_id, allow_patterns=patterns, progress=_NullProgress()
        )
        if not path:
            raise RuntimeError(
                f"Cloak: failed to download {repo_id!r} via Buzz's downloader"
            )
        return path

    def _cached(self, repo_id: str, patterns: list[str]) -> str:
        """Local snapshot dir for ``repo_id`` if the ``patterns`` files are already
        cached; raises otherwise (``local_files_only``)."""
        import huggingface_hub  # lazy
        from buzz.model_loader import model_root_dir  # lazy host import

        return huggingface_hub.snapshot_download(
            repo_id,
            allow_patterns=patterns,
            local_files_only=True,
            cache_dir=model_root_dir,
        )
