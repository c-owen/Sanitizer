# Sanitizer — UX/GUI Design Brief (hand-off to a design agent)

**Status:** kickoff brief for an independent design/UX pass.
**Audience:** a design-focused agent asked to *critique the current UI and propose a
coherent UX direction* for Sanitizer's user-facing surfaces. You are encouraged to be
**adversarial** — challenge our assumptions, not just polish them.
**You are NOT being asked to write production code.** Output is design thinking:
critique, directions, information architecture, textual wireframes, an interaction
model, and a phased recommendation. (See **§10 What we want back**.)

---

## 0. How to use this brief

1. Read this document end to end first — it is self-contained enough to start.
2. Then go deeper in the canonical sources (paths in **§11**): the product brief
   (`buzz-sanitizer-spec.md`, esp. §8 UX requirements), the developer notes
   (`sanitizer/DEV_NOTES.md`), and the two existing windows
   (`sanitizer/sanitizer_host/review_window.py`, `sanitizer/sanitizer_host/demo_window.py`).
3. Treat every "we currently…" statement as a *starting point to interrogate*, not a
   spec. The spec IDs (FR-/PG-/UX-/US-) **are** binding; our current screens are not.

---

## 1. The product in one paragraph

**Sanitizer** is an offline, reversible *sensitive-information sanitizer* that runs as a
plugin inside **Buzz** (a PyQt6 desktop transcription app). After a transcription
finishes, Sanitizer replaces sensitive items — the user's **declared terms** (people,
projects, codenames, clients), **structured PII** (email, phone, credit card, SSN, IP,
URL), and model-**suggested** undeclared names/orgs/locations — with readable,
reversible placeholders like `{{PERSON-A}}`, `{{EMAIL-1}}`, `{{PROJECT-A}}`. The user
**copies the scrubbed text** into a cloud LLM, works with it, **pastes the reply back**,
and Sanitizer **restores** the real values from a local **key**. The mental model we must
teach: **the key is the secret** — the scrubbed text is safe to share; the key is the
thing to protect.

## 2. Who it's for and the job to be done

**Primary persona — the privacy-bound offloader:** a paralegal, clinician, analyst,
journalist, or founder who wants an LLM's help on a transcript but cannot let names,
PII, or internal codenames reach a third party. They are careful, possibly non-technical,
and the cost of a single leak is high.

The end-to-end job (condensed user stories):
- **Declare** their own sensitive terms so the items *they* know about are always
  removed (US2).
- **Trust but verify**: see what was removed, catch anything **missed**, in a finite
  countable list — not a 10,000-word transcript hunt (US5, UX-1).
- **Copy out** scrubbed text, **paste back** the reply, **restore** exactly (US1, US3).
- Get **suggestions** for things they forgot, held for one-click review, never
  auto-trusted (US4).
- Understand the **key is the secret** (US6); see a **clear empty state** when nothing
  is found (US8); and **fail loudly** when removal can't be guaranteed (US9).

## 3. Why UX here is safety-critical (read this twice)

This is not a productivity tool where a clumsy screen costs a few seconds. It is a
**privacy tool where a UX mistake can cause an irreversible leak.** Design implications
that outrank aesthetics:

- **The catastrophic failure is a false negative** — a real sensitive item that is
  *not* removed and gets shipped. So the interface **must not train the eye to skim the
  un-removed text** (UX-3). Catching a miss must be **at least as easy** as approving a
  flagged item. Most "review" UIs optimize the opposite (skim the flags, trust the
  rest) — that pattern is dangerous here.
- **Fail-closed must be legible** (PG7/US9): when Sanitizer can't confirm the declared set
  was removed, the UI must refuse to present output as clean and must not let the user
  copy it. "Looks fine" is not acceptable; the unsafe state must be loud and unmistakable.
- **The wrong-pane copy is a real, likely error** (UX-6): the user means to copy the
  scrubbed text but copies the *key* (or the original). The layout must make that
  mistake hard.
- **Absence is dangerous information** (UX-9): a wrongly-rejected item must stay visible
  and recoverable, never silently gone.
- **Color cannot carry meaning alone** (UX-5): state and tier must read in words and
  grouping, fully usable without color. This is an accessibility *requirement*, and it
  also happens to make the trust hierarchy more legible.

## 4. The three trust tiers (the core information to convey)

Everything Sanitizer flags belongs to exactly one tier, and the tier governs default
behavior. The UI's central job is making this hierarchy obvious **and** color-independent:

| Tier | Source | Default | Reversible? | In the safety guarantee? |
|---|---|---|---|---|
| **Declared** | the user's own list | auto-removed | yes | yes (PG2) |
| **PII** | pattern match (email, phone, …) | auto-removed | yes | yes (PG3) |
| **Suggested** | local model (names/orgs/places/codenames) | **held — pending review** | yes | **no** (never auto-applied, FR-9) |

Predictability matters: the guaranteed tiers (declared + PII) are deterministic;
suggestions are explicitly a separate, reviewable, lower-trust band (PG6).

## 5. The binding UX requirements (from the spec, §8 — verbatim intent)

These are the design direction we converged on. You may propose *how*; the *what* is fixed.

- **UX-1 — A decision list is the home surface.** Review opens to a short, countable
  list of *item-level* decisions. Each entry shows: placeholder, original, type, **why
  flagged** ("matched your list" / "looks like a name" / "phone pattern"), occurrence
  count, and state.
- **UX-2 — Side-by-side is the *detail* view.** Selecting an entry shows the original in
  context beside the result ("is removing *this* one correct?"). The detail serves the
  list; it is not the entry point.
- **UX-3 — Emphasis points at misses.** Catching a missed item ≥ as easy as approving a
  flagged one (FR-16, deferred); the opt-in **suspicion lens** (FR-22) supports the
  scan. Do not, by design, train the eye to skim un-removed text.
- **UX-4 — Decide once per item; bulk + keyboard.** Approve/reject once, applied
  everywhere; bulk actions ("approve all phone numbers", "approve all from my list",
  "reject all dates"); fast keyboard flow to clear the list.
- **UX-5 — State and reason in words + grouping, not color alone.** Fully usable without
  color.
- **UX-6 — Outbound action design.** "Copy scrubbed text" is the single prominent
  action; the key is visually branded as the secret; guard against copying the wrong
  pane.
- **UX-7 — Mirrored restore.** Restore reuses the same surface in reverse: paste reply →
  placeholders highlighted, real values filled back, with a distinct flag for possible
  re-identification (FR-17, deferred).
- **UX-8 — Auto-apply is non-blocking, not invisible.** Even when suggestions are
  auto-applied (FR-12), show the persistent "removed N · Review · Undo" summary (FR-10).
- **UX-9 — Rejected items stay visible.** Items kept in cleartext are shown (struck
  through, in a separate "keeping in cleartext" group) and re-approvable in one action.

**Sample acceptance:** a 60-min transcript with ~12 sensitive items → review shows ~12
entries (not a 10k-word scroll), declared/PII pre-approved, only suggestions awaiting
action; "approve all from my list" clears all declared in one action.

## 6. Current state — what exists today (and why it's rough)

Sanitizer was built in vertical phases; the UI is **functional but unstyled and not yet
designed as a whole.** There are currently **three top-level windows**, reachable from a
"Sanitizer" menu Sanitizer injects into Buzz's menu bar:

1. **`ReviewWindow` — "Review & restore…"** — *the real product surface.* Sidecar-backed,
   interactive. **This is what to design around.**
2. **`SanitizerDemoWindow` — "Sanitizer (manual demo)…"** — a **developer/testing
   playground** from Phase 1 (paste terms + text, hit Sanitize, see scrubbed/key/restore).
   It exists so we could exercise the engine *without* a real transcription. It largely
   **duplicates** the real window's capabilities and is a candidate to **drop or hide**
   in the shipped product — though its "try it on arbitrary text" immediacy might have
   onboarding value. **Your call to make.**
3. **`HelloWindow` — "About Sanitizer…"** — a Phase-0 skeleton remnant; effectively an about
   box.

So: the "multiple windows" you may have heard about is a **development artifact, not a
designed information architecture.** Converging this into one coherent set of surfaces is
itself a key deliverable.

**The current `ReviewWindow` is a single tall scroll of stacked group-boxes:**

```
┌─ Sanitizer — Review & restore ─────────────────────────────┐
│ Transcription: [ 42 ▾ ]                      [Refresh]  │
│ Removed 7 item(s) · 2 pending · clean                   │
│ ┌ Scrubbed transcript (safe to paste into an LLM) ────┐ │
│ │ {{PERSON-A}} kicked off the call and handed to …    │ │
│ │                                  [ Copy scrubbed ]  │ │
│ ├ Decisions — tick to remove, untick to keep ────────┤ │
│ │ [x] Placeholder  Original  Type   Why  Count State │ │
│ │ [x] {{PERSON-A}} Jane      person …    2     removed│ │
│ │ [ ] (on approval) Acme     org   …     1     pending│ │
│ │            [Approve all suggestions] [Reset]        │ │
│ ├ Key — the secret (keep this private) ──────────────┤ │
│ │ [ Reveal key ]                                      │ │
│ ├ Restore a returned reply ──────────────────────────┤ │
│ │ [ paste reply … ] [ Restore originals ]            │ │
│ └─────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

**Honest known weaknesses (your critique should go further):**
- Everything is shown at once with no hierarchy or focus; no **detail/side-by-side**
  view (UX-2 unmet); no **grouping by tier** (declared / PII / suggested / rejected);
  state is a bare word in a table cell, not a designed, color-independent language.
- **No miss-catching affordance** (UX-3) and **no suspicion lens** (FR-22) — the hardest,
  highest-value pieces are entirely undesigned.
- **Restore** is a box bolted to the bottom, not a *mirrored surface* (UX-7).
- The **key** is a reveal toggle + monospace dump; "branded as the secret" (UX-6) is
  asserted, not designed.
- No **first-run / onboarding**, no designed **empty state** (US8) or **unsafe state**
  (US9) beyond a text label; no keyboard/bulk flow beyond two buttons (UX-4).
- Declared-terms editing currently lives only in Buzz's plugin **settings** dialog
  (separate from this window) — is that the right home?

## 7. Technical constraints the design must live within

These shape what is buildable; respect them or argue explicitly for an exception.

- **PyQt6 desktop, plugin-only.** Sanitizer must **not modify Buzz**. There is **no
  UI-extension hook** in Buzz, so Sanitizer surfaces are **its own top-level `QWidget`
  windows**, launched from a "Sanitizer" menu Sanitizer attaches to Buzz's menu bar via public
  Qt APIs. We **cannot** dock panels into Buzz's main layout or add to its main view.
  (So: one window, several windows, tabs, a wizard — all open; *embedding into Buzz's
  screen* is not.)
- **Modeless & coexisting.** Sanitizer windows float alongside Buzz's main window; the user
  may have Buzz and a Sanitizer window open together.
- **Offline, on-device, no telemetry.** No web views, no remote assets, no analytics.
- **Main-thread UI only**; sanitization already runs in the background and writes a
  **sidecar** the window reads — so the UI is presenting/editing local data, not
  computing. Reads/writes are cheap and local.
- **Cross-platform** (Windows/macOS/Linux), keyboard-accessible, **color-independent**
  (UX-5). Assume default Qt theming unless you specify a styling approach.
- **Text + markdown only** (FR-24); placeholders are ASCII- and markdown-safe by
  construction (FR-23) — they survive copy/paste and markdown rendering, which the
  restore flow depends on.

## 8. The data the UI binds to (your raw materials)

The window reads a **sidecar** per transcription and renders/edits it. Shapes:

- **`ReviewItem`** (one row): `placeholder` (empty until a suggestion is approved),
  `original`, `label` (e.g. `PERSON`, `EMAIL`, `PROJECT`), `type` (e.g. `person`,
  `email`), `tier` (`DECLARED` / `PII` / `SUGGESTED`), `reason` (human "why flagged"),
  `state` (`APPROVED` / `PENDING` / `REJECTED`), `count`, and `placements` (which
  segment + char span each occurrence sits at — enables context/highlighting).
- **Scrubbed transcript**: per-segment text (timing preserved) and the joined whole.
- **Key**: `placeholder → original` map (the secret).
- **Meta**: clean/unsafe flag, removed/pending counts, settings snapshot.

Editing a decision (approve/reject) **re-derives** the scrubbed text + key live and
persists. So the UI can offer instant, reversible toggling. Originals + placements are
available, so **in-context highlighting and side-by-side (UX-2) are feasible today.**

## 9. Open design questions — the adversarial core

Engage these directly. Where you disagree with our framing, say so and show the better
option. We *want* to be challenged here.

1. **Information architecture.** One window or several? A single workspace with
   modes/tabs (Review · Outbound · Restore · Settings)? A guided flow for first use and a
   dense surface for repeat use? What happens to the demo/about windows?
2. **The list ↔ detail relationship (UX-1/UX-2).** Master-detail split? Expandable rows?
   A focus mode? How does selecting an item reveal "is removing *this* correct?" without
   making the list feel like a transcript hunt?
3. **Conveying three tiers + four states without color (UX-5).** Design a concrete,
   color-independent visual language (labels, grouping, icons/shape, typography,
   strike-through for rejected). Show it.
4. **Miss-catching ≥ flag-approving (UX-3) — the hardest problem.** How does the UI draw
   the eye to what *wasn't* removed, given the home surface is a list of what *was*?
   How should the optional **suspicion lens** (FR-22) actually look and behave? This is
   where most privacy tools fail; we want a real answer.
5. **The key as "the secret" (UX-6) + wrong-pane guard.** How is the key visually
   branded and protected? How do you make "Copy scrubbed" the obvious safe action and
   copying the key/original an *effortful, deliberate* one?
6. **Mirrored restore (UX-7).** What does "the same surface in reverse" look like? Is
   restore a mode of the same window, a second pane, a separate window? Where does the
   (deferred) re-identification flag surface?
7. **Suggestion review (FR-9/FR-15).** How are pending suggestions presented and cleared
   fast (one action each, plus bulk), while staying visibly *lower trust* than the
   guaranteed set?
8. **Informed auto-apply (FR-12/UX-8).** It may only be *offered after* ≥1 reviewed run,
   and even when on must stay non-blocking with a persistent "removed N · Review · Undo"
   summary (FR-10). Design that offer moment and the persistent summary.
9. **Empty (US8) and unsafe (US9/PG7) states.** Design both as first-class screens, not
   afterthoughts. The unsafe state in particular must be loud and must block copy.
10. **Scale.** Make it work for ~12 items *and* for ~200 (a long, dense transcript):
    grouping, filtering, bulk, keyboard, search.
11. **Where do declared terms get managed?** In Buzz's settings dialog (current), inside
    the Sanitizer window, or both? Editing the list is core to the value (US2).
12. **First-run / onboarding.** How is the "key is the secret" model taught the first
    time, without nagging on every run?

## 10. What we want back (deliverables)

Structure your output roughly like this:

1. **Critique of the current UX** — prioritized, specific, tied to spec IDs and the
   safety framing in §3. Call out anti-patterns and UX *risks* (especially anything that
   could lead to a leak), not just cosmetics.
2. **2–3 distinct design directions** — genuinely different IA bets (e.g.
   "single adaptive workspace" vs "guided wizard + dense repeat surface" vs
   "list-first master-detail"), each with its tradeoffs, who it favors, and how it scores
   against the §3 safety pressures and §5 UX requirements. Recommend one, and say why.
3. **Recommended information architecture** — the surfaces, their relationships, and the
   fate of the demo/about windows; a simple screen/flow map.
4. **Textual wireframes** for the core screens of the recommended direction: review list
   (with tiers/states), item detail / side-by-side, outbound/copy + key, restore, the
   suggestion-review interaction, empty state, unsafe state. ASCII/markdown sketches are
   perfect — no Figma needed.
5. **A color-independent visual language** for tiers + states (words, grouping, shape,
   type), with an explicit accessibility check.
6. **Interaction + keyboard model** — selection, approve/reject, bulk, navigation,
   "clear the list quickly" (UX-4), and the miss-catching affordance (UX-3).
7. **A phased implementation recommendation** that maps onto our remaining work (the
   deferred 5b polish — suspicion lens, informed auto-apply, detail view, styling — and
   Phase 6), sequenced by value and risk, with the smallest first step that most
   improves trust.
8. **Open risks / things you'd want to user-test** before committing.

Keep recommendations **implementable in PyQt6, offline, plugin-safe** (see §7). Tie
choices to spec IDs. Where you intentionally diverge from the spec, flag it and justify it.

## 11. Reference index (read for depth)

- **Product brief (binding):** `buzz-sanitizer-spec.md` — esp. **§4** (persona/stories),
  **§6** (guarantees PG1–PG8), **§7** (requirements FR-*), **§8** (UX-1…UX-9),
  **§13** (risks).
- **Implementation plan:** `sanitizer-implementation-plan.md` — phasing, architecture, the
  §2.3 "no UI-extension hook" finding and the menu-injection resolution.
- **Developer notes (current state of the build):** `sanitizer/DEV_NOTES.md` — what's done,
  the data model, the threading/menu constraints (§6), and what's deferred (§8).
- **The actual windows to critique:**
  - `sanitizer/sanitizer_host/review_window.py` — the real review/restore surface.
  - `sanitizer/sanitizer_host/demo_window.py` — the developer playground.
  - `sanitizer/sanitizer_host/menu.py` — how Sanitizer's menu + windows attach to Buzz.
- **The data model the UI binds to:** `sanitizer/sanitizer_core/transcript.py` (`ReviewItem`,
  `Placement`, `SanitizedSegment`), `sanitizer/sanitizer_core/model.py` (`TrustTier`,
  `DecisionState`), `sanitizer/sanitizer_core/persistence.py` (the sidecar).

---

*This brief is a starting point. The spec IDs are the contract; everything else here is
ours to be argued out of. Push back hard where you see a better path.*
