# Vendored third-party code

This directory holds third-party packages **bundled into the Cloak plugin zip** so
they import at runtime without a separate `pip install`. Cloak adds this directory to
`sys.path` before importing anything here (see
`cloak_host/model_provider_buzz.py::_ensure_vendor_on_path`).

## `gliner/` — GLiNER 0.2.27

- **Source:** `gliner-0.2.27-py3-none-any.whl` from PyPI (pure-Python wheel), unpacked
  verbatim. Upstream: https://github.com/urchade/GLiNER
- **License:** Apache-2.0 — see [`LICENSE`](LICENSE).
- **Why vendored:** GLiNER powers Cloak's optional *suggestion* tier (undeclared
  names/orgs/places). It is a small, pure-Python package, and **all of its runtime
  dependencies are already present in Buzz's environment** (`torch`, `transformers`,
  `huggingface_hub`, `tqdm`, `onnxruntime`, `sentencepiece` — confirmed in Buzz's
  `uv.lock`). Bundling the ~1 MB of GLiNER code therefore makes suggestions work in
  every Buzz deployment (frozen `.exe`, Snap, Flatpak, source) with **no pip install
  and no heavy re-download** — only the model *weights* are fetched, on demand, through
  Buzz's own HuggingFace downloader.
- **Not modified.** To update: download the new `gliner-<version>-py3-none-any.whl`,
  unpack it, and replace `gliner/` here (keep this note + the license in sync).
