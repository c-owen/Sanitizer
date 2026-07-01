# Cloak — Implementation Brief: test-fit → real PyQt6 plugin

**For:** the Claude Code agent working in the `buzz-plugin` repo.
**Goal:** turn the approved v2 design into the real plugin UI — natively in PyQt6, against the data model that already exists, without modifying Buzz and without touching `cloak_core`'s purity.

## How to use this brief

Read, in order: this file → `cloak-design-revision-v2.md` (the decisions) → `cloak-ux-critique-and-direction.md` §4–§6 (wireframes, visual language, interaction model) → the visual reference `Cloak Test-Fit.html` (open it; it's the picture of the target). Then read the code you'll change: `cloak/cloak_host/review_window.py`, `cloak/cloak_host/menu.py`, and the data model in `cloak/cloak_core/transcript.py` + `model.py`. Implement in the phases below, shipping and testing each before the next.

## The one rule that prevents wasted work

**Do not port the HTML.** `Cloak Test-Fit.html` is a bundled React/CSS-in-JS artifact; its DOM and styles have no Qt equivalent. It is a **visual spec only**. Rebuild the design as native Qt widgets by **evolving the existing `ReviewWindow`** (it already does sidecar loading, live re-derive, and persistence — keep that spine). The binding contract is the design docs + spec IDs, not the HTML's code.

## What already exists to build on (don't reinvent)

The data and logic behind most of the design are already in the repo:

- **`ReviewItem`** (`transcript.py`): `placeholder`, `original`, `label`, `type`, `tier`, `reason`, `state`, `count`, `placements` (segment + char span per occurrence — this is what side-by-side and highlighting bind to).
- **`TrustTier`** = `DECLARED` / `PII` / `SUGGESTED`; **`DecisionState`** = `APPROVED` / `PENDING` / `REJECTED` (`model.py`).
- **`apply_review(segments, items)`** re-derives scrubbed text + key from item states; **`next_free_placeholder`** allocates a placeholder on suggestion approval. The existing `ReviewWindow._apply_edits` / `_set_item_approved` / `_persist` already wire this up and persist to the sidecar.
- **Sidecar `meta`** carries `clean` (the fail-closed flag), removed/pending counts.

So approve/reject, live re-derive, persistence, and the unsafe `clean` flag are **done** — the work is presentation and a few new affordances, not new core logic.

## Design region → PyQt6 widget → existing data/logic

| Design region (v2) | Build as | Backed by |
|---|---|---|
| Mode tabs: Review · Send out · Restore | `QStackedWidget` + a `QPushButton`/`QTabBar` row | UI only |
| Safety spine (SAFE / BLOCKED / NOTHING FOUND) | `QFrame` + `QLabel` (glyph + word, not color) | `meta["clean"]`, counts |
| Master-detail split | `QSplitter` | UI only |
| **Two zones** list (Removed / Suggestions) + collapsed Keeping-in-cleartext | `QTreeWidget`, three top-level group items | items grouped by `tier`/`state` |
| "Removed — guaranteed" rows + provenance label | child rows; provenance from `item.type`/`reason` | `tier in {DECLARED, PII}` |
| Suggestions rows w/ Approve/Reject buttons | child rows + `QPushButton`s (not checkboxes) | `tier == SUGGESTED`, `state == PENDING`; approve → `_set_item_approved` |
| "Approve everything detected" | one `QPushButton` | approve all guaranteed + (optionally) clear pending |
| Keeping-in-cleartext (struck-through, collapsed) | collapsed group; strikethrough font | `state == REJECTED`; re-approve = existing toggle |
| Side-by-side context ("is removing this correct?") | `QSplitter` of two read-only `QTextEdit`, highlight the span | `item.placements` (already there, currently unused) |
| Send-out: one big Copy + toast | prominent `QPushButton` + transient `QLabel`/`statusBar` message | existing `_copy_scrubbed` |
| Key block (fenced, reveal, warning) | `QGroupBox` + `QToolButton` reveal | existing `_key_text` / `_on_reveal_toggled` |
| Restore (mirror) | `QVBoxLayout`: paste `QPlainTextEdit` → button → result | existing `restore()` |

## The four things that need NEW backend work (flag these; don't fake them silently)

1. **Reverse "not touched — confirm these" list (FR-22).** A bounded list of entity-shaped tokens Cloak did *not* remove. **Reuse what's there:** the `SUGGESTED` tier already proposes undeclared names/orgs/places — surface those as the core of this list, plus a light capitalized-run heuristic for the rest. It must read "candidates to confirm," never "all clear." If the model isn't available, fall back to the heuristic; never block review on it.
2. **Select-to-redact + add-to-list (FR-16).** Select text in the context pane → one action that (a) removes all occurrences and (b) offers to add it to the declared list. Removal can splice into `placements`/re-run; the add writes to wherever declared terms live (see US2 — surface declared-term management in-window, don't leave it only in Buzz settings).
3. **Empty-state scan evidence (US8).** "Scanned N detectors across M segments · 0 matches." The pipeline must record detector count + segment count into `meta` (small addition in `cloak_host/pipeline.py`); the empty state reads it back. A null result must *prove it ran*.
4. **Restore unresolved-tag report (FR-7).** After `restore()`, count any `{{…}}` placeholders still present in the output and report `⚠ N still unresolved` — don't skip silently.

Smaller: a **first-use "key is the secret" flag** (persist a "seen" marker in `meta` or a marker file — same mechanism DEV_NOTES §8 calls for FR-12) so the Send-out teaching shows once, not every run.

## Phased implementation (ship + test each; smallest trust-improving step first)

**Step A — pure UI restructure, no engine change (highest safety payoff).**
- Replace the flat `QTableWidget` with the **two-zone `QTreeWidget`** + collapsed cleartext group; provenance as a per-row label; suggestions get Approve/Reject buttons; add "Approve everything detected."
- **Loud unsafe:** when `meta["clean"]` is false, **do not render the scrubbed text into any selectable widget** — withhold it behind the blocking wall (today it renders + only disables the copy button, which `Ctrl+A`/`Ctrl+C` defeats). This is the most important single change.
- **Key fencing** + copy-confirmation toast; grayscale-safe glyphs (no color-only meaning).
- In `menu.py`, **drop the demo + About actions** from the shipped menu (keep demo behind a dev env-var if you want).

**Step B — master-detail + modes.** `QStackedWidget` for Review/Send/Restore; `QSplitter` master-detail with **side-by-side context from `placements`**; restore as the mirror mode + the unresolved-tag report; empty-state scan evidence (needs the Step-3 `meta` addition above).

**Step C — miss-catching (the headline).** The reverse "not touched" list + select-to-redact-and-add. This is the highest-value behavior change and depends on B's context pane; scope B tightly to unlock it.

**Step D — polish.** First-use teaching flag; informed auto-apply offer (FR-12, only after ≥1 reviewed run); in-window declared-list management; scale (filter/search/keyboard) for the 200-item case.

## Guardrails (these will fail the build or the design if broken)

- **Keep `cloak_core` pure** — no `buzz`/`PyQt6` imports; `boundary_test.py` AST-scans and fails the build otherwise. All UI lives in `cloak_host`.
- **Never modify Buzz**; UI is Cloak's own top-level window, attached via the existing main-thread menu marshaling (`menu.py`). Main-thread UI only.
- **PG7 is testable, so test it:** add a test that in the unsafe state the scrubbed text is *not present in any selectable widget* and copy is impossible — not merely that a button is disabled.
- **UX-5:** add a check that tier/state read without color (glyph + word + grouping). Don't let red/green carry meaning.
- **Keep the suite green and extend it.** The repo is test-heavy (193/215 tests) and the DoD requires guarantees backed by tests. Mirror `review_window_test.py` for new behaviors. Update `DEV_NOTES.md` §1 as phases close.

## Do NOT

Port the HTML's CSS/DOM · add web deps, web views, or network · bundle a model (it's fetched via Buzz's downloader, FR-13) · auto-apply suggestions by default (FR-9 — held until a click; the "aggressive" pre-select is opt-in only, FR-12-style) · move declared-term editing *out* of reach (US2).

---

### Kickoff message you can hand the Claude Code agent

> Read `cloak-implementation-brief-for-claude-code.md`, then `cloak-design-revision-v2.md` and `cloak-ux-critique-and-direction.md` §4–6, and open `Cloak Test-Fit.html` as the visual target. Implement **Step A only** first: evolve `cloak/cloak_host/review_window.py` into the two-zone tree + collapsed cleartext + "Approve everything," make the unsafe state withhold the scrubbed text (not just disable copy), fence the key with a copy-confirmation toast, and drop the demo/About actions from `menu.py`. Keep `cloak_core` pure, don't modify Buzz, add tests (including a PG7 test that copy is truly impossible when unsafe), and keep the existing suite green. Show me the diff before moving to Step B.
