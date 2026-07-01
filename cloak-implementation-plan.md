# Cloak — Phased Implementation Plan

**Plugin:** Cloak — reversible, offline sensitive-information sanitizer for Buzz
**Source brief:** [buzz-sanitizer-spec.md](buzz-sanitizer-spec.md)
**Target host:** Buzz (`buzz/` in this repo), PyQt6 desktop app, Python 3.12
**Status:** Technical implementation plan (engineering handoff)

---

## 1. How to read this plan

The brief is a *product* document; this is the *technical* plan it hands off to. It is organized into **seven self-contained phases (0–6)**. Each phase:

- delivers a coherent, independently shippable slice;
- is **statically testable** (pytest / pytest-qt, run with `uv`);
- is exercised through the **dynamic loop** (zip the plugin → serve locally → ingest into Buzz → use it), proven in Phase 0 and repeated every phase thereafter;
- lists explicit **exit criteria** and the **spec IDs** (FR-/PG-/UX-/US-) it satisfies.

The ordering front-loads the two biggest risks — *delivery/UI integration* (Phase 0) and the *guaranteed-removal core* (Phases 1–3) — and keeps all safety-critical logic **host-independent** so the brief's mandate "the sanitization logic is verifiable independently of the Buzz app" is satisfied by construction.

---

## 2. Findings from the codebase that shape the plan

All verified against the current source. Paths are clickable.

### 2.1 The plugin contract ([`buzz/buzz/plugins/base.py`](buzz/buzz/plugins/base.py), [`AGENTS.md`](buzz/buzz/plugins/AGENTS.md))

A plugin is a **folder** with a `plugin.py` defining exactly one `BuzzPlugin` subclass and a `metadata` attribute. Hooks (all optional, all headless):

| Hook | Thread | Use for Cloak |
|---|---|---|
| `check_skip` | worker | — |
| `before_transcription` | worker | — |
| `after_transcription(task, segments, ctx)` | background | **(not used to mutate)** — see §2.3 |
| `on_complete(transcription_id, task, segments, ctx)` | background | run sanitization, write sidecar |

`PluginContext` exposes `config`, `transcription_service` (DB, auto-marshaled to main thread), `settings`, `log` — **no UI / main-window handle**, and **no UI-extension hook** (`register_menu`/`register_screen` don't exist). Note the contract's Qt rule is a **thread-affinity rule, not a ban on UI**: under a heading literally titled "Thread-safety contract," [`base.py`](buzz/buzz/plugins/base.py) says `before_transcription` (worker thread) "must NOT touch the database, Qt widgets or anything main-thread bound," and `after_transcription`/`on_complete` (background thread) "must never touch Qt widgets." [`AGENTS.md`](buzz/buzz/plugins/AGENTS.md) only warns "Do NOT touch the database or Qt **here**" inside the worker-thread example — it contains no blanket prohibition. Nothing forbids a plugin from building Qt UI **on the main thread**, which is exactly what §2.3 relies on. The real constraint is simply that the hooks run off-thread, so they can't render UI directly.

### 2.2 Zip install = the dynamic-test path ([`buzz/buzz/plugins/loader.py`](buzz/buzz/plugins/loader.py), [`manager.py`](buzz/buzz/plugins/manager.py))

`PluginManager.add_from_url(url)` → `loader.download_and_extract(url)` → `urlopen(url, timeout=60)` → safe-extract (zip-slip guarded) → **validate by loading** → copy to `~/.cache/Buzz/plugins/<id>/` → auto-enable. Because it uses `urlopen`, a locally served `http://localhost:8000/cloak.zip` (or `file://…`) installs exactly like a remote one. Archive may have `plugin.py` at the root or inside one wrapping folder. **This is the brief's "serve the zipped plugin locally and ingest it into the app."**

### 2.3 The headless-UI tension and its resolution (THE key design decision)

The brief needs a user-opened **review** screen and a **restore** screen (UX-1…UX-9, §14). There is no UI-extension hook, and the lifecycle hooks run off the main thread so they can't render UI directly. But the Qt rule is only thread-affinity (§2.1), so UI built **on the main thread** is allowed. Resolution, using only public APIs and **without modifying Buzz**:

- `PluginManager.initialize()` is called by `MainWindow` **on the main thread**; it imports each `plugin.py` and instantiates the `BuzzPlugin` subclass. **The plugin's `__init__` therefore runs on the main thread**, where Qt access is legal.
- In `__init__`, Cloak locates the running `QMainWindow` via `QApplication.instance().topLevelWidgets()` and attaches its own **"Cloak" menu** through the **public `QMainWindow.menuBar()` API** (the same surface any Qt app exposes — not a Buzz internal). The menu actions open Cloak's own top-level `QWidget` windows (Review, Restore).
- Sanitization itself runs in the **`on_complete`** background hook (matching §14: "runs automatically in the background right after a transcription finishes"); results are persisted as a **sidecar** (§2.4). The review window reads the sidecar — no work happens on the UI thread except presenting.

This is the single most novel integration assumption, so **Phase 0 de-risks it directly** with a trivial menu+window spike. Fallback if menu injection proves fragile across Buzz versions: Cloak shows a small always-available **floating launcher window** at startup instead (still public Qt only). The decision does not affect the host-independent core (Phases 1–4).

### 2.4 Don't mutate the transcript; persist a sidecar

`after_transcription`'s return value is **saved** to the DB. Cloak must **not** overwrite the real transcript with scrubbed text — the user's stored transcript stays pristine; the scrubbed copy is the thing they *copy out*. So Cloak treats segments **read-only** and writes a **sidecar** keyed by `transcription_id`:

```
~/.cache/Buzz/plugins_data/cloak/<transcription_id>/
   decisions.json     # detections, tiers, placeholders, per-item state
   key.json           # placeholder → original  (THE SECRET — separate file, PG8)
   meta.json          # version, source hash, settings snapshot
```

Segment timing is never touched ⇒ **PG5 holds by construction**. Scrubbing is computed **per segment** (text in, scrubbed text out, same `start`/`end`) so a future scrubbed `.srt`/`.vtt` export (P2) stays in sync. The plugin owns this directory itself (via `platformdirs.user_cache_dir("Buzz")`, already a Buzz dependency). The key is **never** written into the scrubbed output (PG8).

### 2.5 Model download is general enough ([`buzz/buzz/model_loader.py`](buzz/buzz/model_loader.py))

`TranscriptionModel(model_type=ModelType.HUGGING_FACE, hugging_face_model_id="owner/repo")` + `get_local_model_path()` will **auto-download any HF repo** into the shared cache `~/.cache/Buzz/models/`, write a `.buzz_complete` marker, and reuse it offline (`local_files_only`) thereafter. `ModelDownloader(QRunnable)` emits `finished/progress/error` Qt signals; `download_from_huggingface(repo_id, allow_patterns, …)` is model-agnostic. `huggingface_hub` and `transformers` are already importable. ⇒ FR-13 ("downloaded on first use through Buzz's built-in mechanism, nothing bundled, cached model reused") is directly achievable.

### 2.6 Data model & tests

- `Segment(start, end, text, translation="")`, times in **ms** ([`buzz/buzz/transcriber/transcriber.py`](buzz/buzz/transcriber/transcriber.py)). DB entity `TranscriptionSegment(start_time, end_time, text, translation, transcription_id, id)`.
- Text assembly for export is in [`buzz/buzz/transcriber/file_transcriber.py`](buzz/buzz/transcriber/file_transcriber.py) `write_output()` — reference for how a transcript becomes flat text.
- Tests: **pytest + pytest-qt** (`qt_api=pyqt6`), `pytest-mock`, `pytest-timeout`, `pytest-xvfb`. Run with `uv run make test` (full, coverage-gated) or scoped `uv run pytest tests/plugins/...`. In-memory DB fixtures exist: `db`, `transcription_segment_dao`, `transcription_service` ([`buzz/tests/conftest.py`](buzz/tests/conftest.py)). GUI tests use `qtbot`. Plugin test patterns: [`buzz/tests/plugins/`](buzz/tests/plugins/plugin_system_test.py).
- Clipboard pattern: `QApplication.instance().clipboard().setText(...)` (guard for `None`).

### 2.7 Reference plugins to model Cloak on

- [`ai_summary/plugin.py`](buzz/buzz/plugins/ai_summary/plugin.py) — the documented reference: `on_complete`, config fields incl. `PASSWORD`, localization, reuse of a bundled lib.
- [`deep_filter_net/plugin.py`](buzz/buzz/plugins/deep_filter_net/plugin.py) — a plugin that uses an **ML model** + declares a `pip_dependencies` entry; deferred heavy import inside the hook.

---

## 3. Target architecture (component map)

Two layers, deliberately separated so the safety core never depends on Buzz or Qt.

```
cloak/                                  # the distributable plugin folder (zipped as cloak.zip)
  plugin.py                             # BuzzPlugin subclass — THIN host glue only (§Phase 5)
  cloak_core/                           # HOST-INDEPENDENT library (pure Python; no buzz/no Qt)
    model.py        # Detection, Decision, TrustTier, Span, SanitizationResult, Key
    detectors/
      base.py       # Detector protocol  (assumes/guarantees documented)
      declared.py   # DeclaredListDetector            (FR-1)
      pii.py        # Per-type PII detectors, toggleable (FR-2)
      suggest.py    # ModelSuggestionDetector + ModelProvider port (FR-15)
    vault.py        # Vault: consistent placeholders ↔ key, reversible (FR-3, PG4, PG8)
    placeholders.py # Placeholder style/format, robustness rules (FR-23)
    sanitizer.py    # Sanitizer: detect→decide→substitute orchestration
    verify.py       # VerificationGate: re-scan, fail-closed (FR-6, PG2/3/7)
    formats/
      base.py       # FormatHandler protocol
      text.py       # plain text in/out
      markdown.py   # markdown in/out + round-trip safety (FR-24, FR-23)
    restore.py      # restore from returned text + key, skip-unmatched (FR-7)
    persistence.py  # sidecar read/write (pure fs; path injected)        (PG8)
  cloak_host/                           # Buzz/Qt adapters (imported only inside the app)
    model_provider_buzz.py # ModelProvider impl backed by Buzz's downloader (FR-13)
    ui/ review_window.py, restore_window.py, summary_bar.py, decision_list.py …
    menu.py         # main-thread menu attachment (§2.3)
  locale/*.json                         # 14 locales (bundled-plugin requirement)
```

**Design principles realized (brief §5):** every box above is an independently replaceable unit behind a small documented interface (`Detector`, `FormatHandler`, `ModelProvider`, `Vault`); each interface states *assumes / guarantees* in its docstring and is backed by contract tests that fail the build (Phase 6). "Offline by default" and "fail-closed" are enforced in `verify.py` + the PG1 network test.

---

## 4. The two test tracks (apply to every phase)

### 4.1 Static testing (primary, every phase)

- **`cloak_core` suite** — pure-Python pytest, **no Buzz, no Qt imports**. Runnable standalone (`uv run pytest cloak/cloak_core/tests`) so the core is "verifiable independently of Buzz" (DoD). Fast; this is where the guarantees live.
- **Host/integration suite** — under Buzz's `tests/plugins/` conventions, uses `qtbot` + the in-memory DB fixtures. Covers the hook wiring, sidecar, menu attachment, and the review/restore windows.
- **Guarantee tests (PG1–PG8)** — a dedicated module asserting each product guarantee; wired into CI so a violation **fails the build** (DoD). Highlights:
  - **PG1 (offline):** monkeypatch `socket.socket`/`urllib`/`huggingface_hub` to raise, run the full guaranteed path, assert success and zero network attempts.
  - **PG2/PG3 (no leak):** after sanitize, gate finds no declared term / enabled-PII survivor.
  - **PG4 (reversible):** `restore(sanitize(x)) == x` round-trips, incl. markdown.
  - **PG6 (predictable):** same input → identical guaranteed removals (golden test).
  - **PG7 (fail-closed):** inject a survivor, assert "clean" is refused and auto-copy is blocked.
- **Property-based tests** (substring-safety FR-1, reversibility FR-7) via `hypothesis` — a **test-only** dependency of `cloak_core`, never shipped.

### 4.2 Dynamic testing (the zip → serve → ingest loop)

A `make`-style target / script (`tools/package.py`) produces `dist/cloak.zip` (contents = the `cloak/` folder). Canonical loop:

```bash
# 1. build the zip
uv run python tools/package.py            # -> dist/cloak.zip

# 2. serve it locally
cd dist && uv run python -m http.server 8000

# 3. ingest in Buzz:  Help → Plugins → Add by URL → http://localhost:8000/cloak.zip
#    (auto-extracts, validates, installs to ~/.cache/Buzz/plugins/cloak, auto-enables)
```

**Fast inner loop** (skip the zip while iterating): copy `cloak/` straight into `~/.cache/Buzz/plugins/cloak/` and restart Buzz. **Re-ingest after a change:** re-add by URL (the loader `rmtree`s and recopies the dest). Each phase below names the concrete in-app action to verify.

> **Offline-deps caveat for dynamic runs:** `pip_dependencies` install on first load and need network (or a pre-seeded `~/.cache/Buzz/plugins_deps/`). Keep the guaranteed path (declared + PII) **dependency-free** so it installs and runs fully offline; only the suggestion tier (Phase 4) may pull a dep/model on first use.

---

## 5. Phases

### Phase 0 — Walking skeleton + dev/test harness

**Goal:** prove the entire delivery loop and the riskiest integration assumption (§2.3) with a no-op plugin, before any real logic.

**Deliverables**
- `cloak/plugin.py` — minimal `BuzzPlugin` (`id="cloak"`, name/description, no hooks), loads cleanly.
- `cloak_host/menu.py` — main-thread attachment that adds a **"Cloak"** menu with one action **"Cloak: Hello"** opening a trivial top-level `QWidget`. Attached from `plugin.__init__` via `QApplication.instance().topLevelWidgets()` → `menuBar()`.
- `tools/package.py` — folder → `dist/cloak.zip`.
- `locale/` seeded with the 14 required JSON files (empty maps are fine to start).
- Dev docs: the §4.2 loop written into `cloak/README-dev.md`.

**Static tests**
- Plugin imports and exposes valid `metadata.id` (mirror [`plugin_system_test.py`](buzz/tests/plugins/plugin_system_test.py)).
- `load_plugin_from_dir(cloak)` returns one `BuzzPlugin`.
- `package.py` yields a zip whose root (or single wrapping dir) contains `plugin.py`, and `download_and_extract("file://…/cloak.zip")` installs it.
- `qtbot` test: given a dummy `QMainWindow`, menu attachment adds the "Cloak" menu and the action opens the window.

**Dynamic test**
- Serve `cloak.zip`, **Add by URL** in Buzz, confirm Cloak appears in **Help → Plugins**, is enabled, the **Cloak menu** is present, and "Hello" opens. Verifies §2.3 end-to-end in the real app.

**Exit criteria:** the loop in §4.2 works; the menu spike opens a window inside Buzz. **Spec:** FR-13 (install/no-app-modification), de-risks UX entry point.

---

### Phase 1 — Core domain + declared-list sanitization (host-independent)

**Goal:** the highest-trust removal tier and the substitution/key spine, as a pure library.

**Deliverables**
- `model.py`: `Span`, `TrustTier{DECLARED, PII, SUGGESTED}`, `Detection(span, value, type, tier, reason)`, `Decision(state∈{approved,rejected,pending}, placeholder)`, `SanitizationResult(scrubbed, decisions, key, clean: bool)`.
- `detectors/base.py`: `Detector` protocol — `detect(text|segments) -> list[Detection]`; docstring states *assumes/guarantees* (e.g. "guarantees no match spans a partial word").
- `detectors/declared.py`: `DeclaredListDetector` — case/possessive/whitespace variants (FR-1); **word-boundary safe** ("Jane" never touches "Janet"); records every occurrence.
- `vault.py`: `Vault` — one placeholder per distinct canonical value, repeats share it, different values never collide (FR-3); builds the reversible key (PG4).
- `placeholders.py`: initial robust+readable style (candidate `⟦PERSON-1⟧`-class tokens; see §6) behind a swappable interface.
- `sanitizer.py`: orchestrates detect → decide(declared auto-approved) → substitute; `restore.py` stub.

**Static tests:** substring-safety table + `hypothesis` property test; consistent-placeholder/no-collision; per-occurrence key completeness; declared variants matched; round-trip on declared-only text. **No Buzz/Qt imports** (enforced by an import-linter test).

**Dynamic test:** add a hidden/debug "Sanitize sample text" item to the Cloak window; paste declared terms + text, see consistent placeholders and a key. (Manual sanity in-app; correctness is owned by static tests.)

**Exit criteria:** declared-list sanitize+restore correct & substring-safe; core importable with zero host deps. **Spec:** FR-1, FR-3, PG4 (partial), PG6, US1/US2, "verifiable independently."

---

### Phase 2 — Structured-PII detectors + verification gate + fail-closed

**Goal:** the second guaranteed tier and the safety gate that makes "clean" trustworthy.

**Deliverables**
- `detectors/pii.py`: individually toggleable detectors for **phone, email, credit card, SSN, IP, URL** (FR-2); each documents its pattern + known false-pos/neg posture; disabled types pass through untouched.
- `verify.py`: `VerificationGate.verify(scrubbed, enabled_detectors, declared)` re-scans output; **any** declared- or enabled-PII survivor ⇒ `clean=False` with the survivor list (FR-6). Suggestions are explicitly **not** gated.
- Fail-closed plumbing in `sanitizer.py`: when `clean=False`, result is marked unsafe; **no auto-copy** (PG7).
- Empty-state result when nothing is detected (FR-11).

**Static tests:** per-type positive/negative corpora; toggling a type changes only that type; **PG2/PG3** (no survivor) and **PG7** (inject a survivor → refuse clean, block copy); empty-state; PG6 golden determinism across declared+PII.

**Dynamic test:** in-app sample with emails/phones/etc.; toggles honored; a deliberately surviving token shows the **blocked/unsafe** state rather than "clean."

**Exit criteria:** all six PII types removable & toggleable; gate fails closed; empty-state correct. **Spec:** FR-2, FR-6, FR-11, PG2, PG3, PG6, PG7, US8, US9.

---

### Phase 3 — Format handlers + restore + markdown round-trip + placeholder robustness

**Goal:** the usable text **and** markdown round trip, with placeholders that survive it.

**Deliverables**
- `formats/base.py` + `text.py` + `markdown.py`: `FormatHandler` (parse/serialize) for both directions (FR-24); no file formats (NG6).
- `restore.py` (full): substitute originals back from the key; **placeholders absent from returned text are skipped silently** (FR-7).
- `placeholders.py` hardened: tokens chosen so **markdown rendering, copy/paste, and light editing cannot split/alter them** (FR-23); restore matches whole tokens tolerant of surrounding punctuation/wrapping.
- (Re-identification flag is **P1/FR-17 → deferred**; leave a seam in `restore.py`.)

**Static tests:** markdown↔text round trip; **PG4** exact reversibility incl. markdown; FR-23 robustness matrix — render markdown, simulate copy/paste normalization, light edits (wrap, adjacent punctuation, case-preserving) → tokens intact & restorable; restore-with-unmatched-placeholders is a no-error skip.

**Dynamic test:** **Copy scrubbed (markdown)** from the Cloak window → paste into a markdown renderer → copy rendered text back → **Restore** → originals returned; unmatched placeholders ignored.

**Exit criteria:** both formats round-trip; placeholders provably survive the markdown trip; restore skips cleanly. **Spec:** FR-7, FR-23, FR-24, PG4, US3.

---

### Phase 4 — Suggestion model tier (local, fetched via Buzz)

**Goal:** the lightweight, review-gated suggestion tier — additive, never auto-trusted.

**Deliverables**
- `detectors/suggest.py`: `ModelSuggestionDetector` producing **`SUGGESTED`-tier** detections (undeclared names/orgs/locations + obvious codename-type mentions) with a human-readable `reason`; **never** enters the guaranteed set, **always** held for review (FR-9, FR-15, PG6).
- `ModelProvider` **port** (in `cloak_core`) so the core stays host-free; tests inject a stub.
- `cloak_host/model_provider_buzz.py`: adapter that fetches the model on **first use** via Buzz's downloader into the shared cache and reuses it offline (FR-13). Runs on **CPU**, cross-platform.
- Model decision recorded in §6 (candidate **GLiNER** zero-shot NER; `transformers`-NER fallback if offline pip-install is a concern). Kept behind the `Detector`/`ModelProvider` seams so the exact model is non-blocking.

**Static tests:** with a **stubbed** provider, suggestions land in the `SUGGESTED` tier, are `pending` by default, and are excluded from the verification gate and from any auto-apply; guaranteed-path tests still pass with the model **absent** (degrade gracefully). One **opt-in, slow** integration test (marked, off by default) that the real model downloads into Buzz's cache and runs on CPU.

**Dynamic test:** first open triggers a one-time model download via Buzz's mechanism (progress shown); suggestions appear as a distinct lower-trust group, each with a reason, none applied without a click. Disable the plugin's suggestion toggle → guaranteed path still fully works offline.

**Exit criteria:** suggestions are local, review-gated, never auto-applied, fetched via Buzz with nothing bundled; guaranteed tiers unaffected when the model is missing. **Spec:** FR-9, FR-13, FR-15, PG6, US4.

---

### Phase 5 — Host integration: pipeline + sidecar + the review/restore UI

**Goal:** wire the core into Buzz and build the trust surface. *(Largest phase — may split 5a/5b.)*

**5a — Pipeline + persistence + minimal actions**
- `plugin.py`: `on_complete` runs sanitization on the finished transcript (read-only) and writes the **sidecar** (§2.4) keyed by `transcription_id`; saved transcript untouched (PG5, PG8). Config fields (toggles per PII type, suggestion on/off, auto-apply default-off, lens default-off) via `ConfigField`.
- `cloak_host/ui/review_window.py` (minimal): **Copy scrubbed text** (single prominent action), **paste → Restore**, key shown as the branded secret with copy-the-wrong-pane guard (UX-6, UX-7).
- Persistent, non-blocking **"removed N · Review · Undo"** summary (FR-10).

**5b — Full decision-list review UX**
- Decision list as the home surface: per-item rows (placeholder, original, type, **why-flagged**, occurrence count, state) — countable, not a transcript scroll (UX-1).
- Side-by-side detail view serving the list (UX-2); decide-once-per-item applied everywhere; **bulk** + keyboard flow (UX-4); state/type shown in **words + grouping, color-independent** (UX-5).
- **Rejected items stay visible** (struck-through, separate "keeping in cleartext" group, one-click re-approve) (UX-9).
- Emphasis-points-at-misses affordances (UX-3); **opt-in suspicion lens**, default off (FR-22).
- **Informed auto-apply** offered **only after** ≥1 completed reviewed run; still shows summary + Undo (FR-12, UX-8).
- (One-gesture "scrub this" FR-16 is **P1 → deferred**; leave a hook.)

**Static tests (pytest-qt):** `on_complete` writes a correct sidecar and never alters stored segments (assert segment text/timing unchanged via `transcription_service`); review window renders N decisions for a known fixture; bulk "approve all from my list" resolves declared entries; rejected items remain visible & re-approvable; copy writes scrubbed text to clipboard; **unsafe result disables copy** (PG7 at the UI); auto-apply hidden until a reviewed run completes; lens toggle does not gate completion.

**Dynamic test (full acceptance):** transcribe a clip seeded with ~12 sensitive items (declared + PII + a couple of names) → open **Review** → see ~12 grouped entries, declared/PII pre-approved, suggestions pending → "approve all from my list" clears declared in one action → **Copy scrubbed** → round-trip through an external markdown tool → **Restore** → originals back. Confirm the saved Buzz transcript is **unchanged**.

**Exit criteria:** automatic background sanitize + sidecar; the full review/restore surface meets UX-1…UX-9; transcript never mutated. **Spec:** FR-5, FR-8, FR-10, FR-12, FR-22, PG5, PG8, UX-1…UX-9, US5/US6/US7, §14.

---

### Phase 6 — Guarantee hardening, offline proof, extensibility demo, docs, DoD sign-off

**Goal:** lock the safety contract into CI and close the Definition of Done.

**Deliverables**
- **PG1–PG8 guarantee module** wired so any violation **fails the build**; PG1 network-block assertion runs around the whole guaranteed suite.
- **Extensibility demonstration (FR-14):** add one new detector (e.g. IBAN/MAC) *and* confirm a new format handler can be added **without touching existing detectors or the core flow** — shipped with its own test as living proof of the modular mandate.
- **README** (user-facing): what Cloak guarantees, what it explicitly does **not** (NG2 — not compliance certification, no completeness on undeclared items), and the **"the key is the secret"** model.
- Quality-bar harness for **OQ4/OQ5**: a curated sensitive-transcript set with a recall check and a review-effort/time measurement, parameterized so the agreed bar (once set) gates CI.
- Final `dist/cloak.zip`; full §4.2 acceptance pass; (optional) bundle path documented (add `cloak` to `loader.BUNDLED_PLUGIN_IDS` + `Buzz.spec`).

**Static tests:** the complete PG1–PG8 suite green and build-failing on regression; extensibility test passes; locale-completeness test (all 14 files, no empty-string values per the AGENTS.md warning).

**Dynamic test:** clean-machine run of the §4.2 loop end-to-end against the DoD checklist (offline guaranteed path; first-use model fetch; markdown round trip; rejected-item visibility).

**Exit criteria:** every brief **Definition of Done** box checked; guarantees enforced in CI. **Spec:** PG1–PG8, FR-14, NG2, DoD §11, success signals §10.

---

## 6. Decisions I'm making (non-blocking; flag if you disagree)

These resolve the brief's open questions (OQ4–OQ6) and a few implementation forks with sensible defaults so engineering isn't blocked:

| # | Decision | Rationale / brief tie |
|---|---|---|
| D1 | **UI entry point = a "Cloak" menu injected via public `QMainWindow.menuBar()` at main-thread init**, opening Cloak's own top-level windows; floating-launcher fallback. | Only way to get a user-opened screen without modifying Buzz (§2.3, §14). |
| D2 | **Sidecar persistence** (separate `key.json`), transcript never mutated. | PG5, PG8; brief §2.4 reasoning. |
| D3 | **Placeholder style:** readable core in robust, non-markdown delimiters (e.g. `⟦PERSON-1⟧`), behind a swappable interface; symbolic-only in v1 (no realistic fakes yet). | OQ6 → symbolic v1; must satisfy FR-23. |
| D4 | **Suggestion model:** GLiNER-class zero-shot NER as primary candidate, `transformers`-NER fallback; final pick in Phase 4 behind the `ModelProvider` seam. | FR-15 ("zero-shot"), CPU/cross-platform; §15 leaves specifics to engineering. |
| D5 | **Guaranteed path is dependency-free and offline**; only the suggestion tier may fetch a dep/model on first use. | PG1; offline-deps caveat (§4.2). |
| D6 | **Scope = v1/P0 only.** FR-16, FR-17 (P1) and FR-18–21, FR-25 (P2) are explicitly out, with seams left where cheap. | Brief §7, §12. |
| D7 | **OQ4/OQ5 quality bar** is built as a parameterized harness in Phase 6; the numeric targets are set by PM and then gate CI. | Brief §9 marks these non-blocking. |

---

## 7. Spec traceability (FR/PG → phase)

| Phase | Requirements | Guarantees |
|---|---|---|
| 0 | FR-13 (install path) | — |
| 1 | FR-1, FR-3 | PG4*, PG6 |
| 2 | FR-2, FR-6, FR-11 | PG2, PG3, PG6, PG7 |
| 3 | FR-7, FR-23, FR-24 | PG4 |
| 4 | FR-9, FR-13, FR-15 | PG6 |
| 5 | FR-5, FR-8, FR-10, FR-12, FR-22 | PG5, PG8 |
| 6 | FR-14 + all P0 acceptance | PG1, PG2–PG8 enforced in CI |

\*partial in Phase 1, completed in Phase 3. P1 (FR-16/17) and P2 (FR-18–21, FR-25) are out of scope for v1.

---

## 8. Top risks (carried, with the phase that retires each)

| Risk | Mitigation | Retired in |
|---|---|---|
| No UI-extension hook; hooks run off-thread (§2.3) | Main-thread menu injection via public `menuBar()` in `__init__`; launcher fallback | Phase 0 |
| Overwriting the user's transcript | Read-only segments + sidecar; assert-unchanged test | Phase 5a |
| Markdown mangles placeholders (R7/FR-23) | Robust token design + robustness matrix tests | Phase 3 |
| Offline dep/model install fails (R6) | Guaranteed path dep-free; model only on first use via Buzz cache | Phases 2, 4 |
| False negative ships (R1, catastrophic) | Combine detectors, fail-closed gate, miss-pointing UX | Phases 2, 5b |
| Host coupling / Buzz updates (R6) | Keep integration thin at the edges; core fully host-independent | Phases 1–4 |

---

*End of plan.*
