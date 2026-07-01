# Cloak — UX Critique & Recommended Direction

**From:** design/UX review (adversarial pass)
**Re:** the user-facing surfaces of Cloak — the offline reversible sanitizer plugin in Buzz
**Posture:** this is a *privacy tool*, not a productivity tool. Every call below is weighed against one question first — *could this design let a real sensitive item reach a cloud LLM?* — and aesthetics second.

## 0. What I read (and the lens I'm using)

I read the UX brief end to end; the spec §4 (persona/US1–US9), §6 (PG1–PG8), §7 (FR-*), §8 (UX-1…UX-9), §13 (risks); the three windows (`review_window.py`, `demo_window.py`, and the `HelloWindow` "About" skeleton in `menu.py`); DEV_NOTES §6–§8; and the data model the UI binds to (`ReviewItem`/`Placement`/`SanitizedSegment` in `transcript.py`, `TrustTier`/`DecisionState`/`Key` in `model.py`).

The reframe I'm holding throughout (brief §3, spec R1): **the catastrophic failure is a false negative.** So the bar isn't "is the screen clear?" — it's "does the screen make catching a *miss* at least as easy as approving a *flag* (UX-3), refuse loudly when it can't guarantee removal (PG7/US9), make the key read as the secret and the wrong-pane copy hard (UX-6/PG8), keep rejected items visible (UX-9), and carry all meaning without color (UX-5)?" Against that bar, the current UI has real, specific holes — some of them leak-class.

One structural note before the critique: **the data to do this well already exists.** `ReviewItem.placements` carries every occurrence's segment + char span, and `apply_review` re-derives scrubbed text + key live. Side-by-side context (UX-2), in-context highlighting, and select-to-scrub (FR-16) are all *feasible today* and simply unbuilt. The gaps below are design/IA gaps, not engine gaps.

---

## 1. Prioritized critique of the current UX

Ordered by leak risk, not by polish. Each tied to spec IDs.

### CRITICAL — these can cause a leak

**C1 — The home surface trains the eye to skim what was *removed*, and gives no way to catch what was *missed*. (UX-3, R1, FR-16, FR-22 — the central failure.)**
The `ReviewWindow` is a flat checkable table where *every row is something Cloak already flagged*. There is no affordance anywhere that points at un-removed text: no select-to-scrub (FR-16), no suspicion lens (FR-22), no way to act on a token the detectors missed. The scrubbed transcript sits above as a passive, read-only blob you can *read* but not *act on*. So in the current UI, catching a miss is not merely harder than approving a flag — **it is impossible without leaving the window** (you'd have to notice a name in the blob, go to Buzz's settings dialog, add it to the declared list, re-transcribe). That is the exact inverse of UX-3, and it's the design pattern spec §3 explicitly calls "dangerous." This is the single most important thing to fix.

**C2 — Fail-closed is a whisper, not a wall. (PG7, US9, UX-5.)**
When verification fails, the UI does two things: it writes `"UNSAFE — a sensitive item may remain"` into the one-line summary label, and it disables the *Copy scrubbed text* button. That's it. Meanwhile the full scrubbed text remains rendered in a normal, fully-selectable `QPlainTextEdit` — the user can `Ctrl+A`/`Ctrl+C` it straight to the clipboard, bypassing the disabled button entirely. So the "block" is one greyed-out button and a sentence the user has to read and parse. Spec demands the unsafe state be "loud and unmistakable" and that the tool "refuse to present output as clean." A disabled button over a live, copyable leak is neither loud nor a refusal. **The unsafe state must physically remove the copyable text from reach, not just grey out one of the three ways to copy it.**

**C3 — Wrong-pane / wrong-thing copy is wide open. (UX-6, PG8.)**
The window contains three look-alike text panes (scrubbed, key, restored), all the same `QPlainTextEdit` styling, plus two same-styled buttons: *Copy scrubbed text* and *Copy key (secret)*. Once the key is revealed it's a plain, selectable dump sitting inches from the scrubbed text. Nothing makes copying the scrubbed text the *obvious safe* action and copying the key an *effortful, deliberate* one — they are visually peers. UX-6's "guard against copying the wrong pane" is asserted by the group-box title "(keep this private)" and nothing more. The most likely catastrophic user error — copy the key instead of the scrubbed text, paste *the secret* into the cloud LLM — is essentially unguarded.

**C4 — Three tiers are flattened into one undifferentiated list; suggestions don't read as lower-trust. (UX-1, UX-5, FR-15, PG6.)**
Declared, PII, and Suggested items are interleaved as peer rows in a single stretched table. Tier is *not even a column* — the only hint of why an item is trusted is buried in the free-text "Why flagged" cell. Spec is emphatic that suggestions are "a distinct, lower-trust band" (FR-15) and that the guaranteed/predictable set (PG6) must be visibly separate from model guesses. Right now a deterministic, guaranteed-removed declared term and a speculative model guess look identical. That erodes the entire trust hierarchy the product is built on — and it breaks the sample-acceptance promise ("approve all *from my list* in one action"): there is no "from my list" grouping to act on.

### HIGH — degrade trust, enable error, or violate a named UX requirement

**H1 — No detail / side-by-side view. (UX-2, unmet.)**
`placements` gives us segment + span for every occurrence, but the UI never renders context. The user sees `Jane · person · 2` with no surrounding sentence, so "is removing *this* one correct?" is unanswerable. They approve/reject blind. For guaranteed tiers that's tolerable; for suggestions and for spotting over-scrub (R2) it forces either rubber-stamping or fear-driven inaction.

**H2 — Rejected items don't get the UX-9 treatment.** A rejected item is just an unticked checkbox with the state word "kept in cleartext," still sitting in the same flat list — no strike-through, no separate "keeping in cleartext" group. UX-9's whole point is that *absence is dangerous information*: a wrongly-rejected sensitive item must be visually unmistakable and recoverable. Today a rejected (deliberately-left-in-cleartext) item is one glance away from a pending one. (Credit where due: re-approval *is* one click — the checkbox — so that half of UX-9 holds.)

**H3 — Restore is bolted to the bottom, not a mirrored surface. (UX-7.)** It's a small paste box + button + read-only output crammed under the outbound flow. No placeholder highlighting, no "real values filled back" visual, no home for the re-identification flag (FR-17, deferred — fine to defer, but there's no surface to put it on later). It also competes for attention with the outbound flow, when outbound and restore are two different jobs done at two different times (spec §14).

**H4 — No information hierarchy; the decision list is not the home surface. (UX-1.)** Everything — selector, summary, scrubbed blob, decisions, key, restore — is stacked in one 820×880 scroll. UX-1 wants the decision list to *be* the home; here it's the third box down, with a transcript blob above it inviting exactly the long-scroll hunt UX-1 says to avoid.

**H5 — Empty and unsafe states are not first-class screens. (US8, US9.)** "Nothing detected in *this* transcript" (US8 — a success, "you're done, nothing to do") is not distinguished from "no transcripts yet" (a cold-start) or from the unsafe state (US9 — a danger). These three carry *opposite* meanings and currently differ only by the wording of one label.

### MEDIUM — IA / scale / workflow

**M1 — Three windows are a dev artifact, not an IA — and the demo window is a latent leak surface.** `CloakDemoWindow` ships in the menu and runs a *parallel* sanitize path (`sanitize()` directly) with **none** of the sidecar, verification-gate, or review safety of the real window. A user who pastes real sensitive text into a window literally labeled "Sanitizer" — with its own "Copy scrubbed text" button — can copy out a result that never went through the fail-closed gate. That's both a brand-confusion problem (two buttons, same words, different guarantees) and a genuine leak vector. `HelloWindow` ("About Cloak") is a Phase-0 skeleton with no reason to be a top-level menu peer. The menu offers three equal-weight entries with no hierarchy.

**M2 — Declared-term editing lives in Buzz's settings dialog, disconnected from review. (US2, R4, brief §9.11.)** The declared list is the single most important adaptation lever (R4 says it's "never optional"), yet it's nowhere near the surface where the user *notices* a miss. Combined with the missing FR-16, the learn-loop ("I caught one → add it so it's caught next time") is completely broken.

**M3 — Won't scale to a dense transcript. (§9.10, UX-4.)** Stretch-mode table, no grouping, no filter, no search, no sort, no collapse. Bulk actions are only "approve all suggestions" and "reset" — UX-4 explicitly names "approve all from my list," "approve all phone numbers," "reject all dates," none of which exist. Keyboard flow is whatever Qt gives a checkbox table for free — there is no designed "clear the list fast" path (UX-4 / OQ5).

**M4 — The transcription selector shows raw `transcription_id`s** and silently loads the most recent. Minor, but it's the first thing the user touches and it's unreadable.

### What's actually right (keep it)

State is shown in *words* not just a checkbox, and the mapping is sensible (`removed` / `suggested (pending)` / `kept in cleartext`) — a real down-payment on UX-5. The copy-disable-on-unsafe wiring shows PG7 was thought about at the UI (it's just far too weak). The key is hidden behind a reveal toggle by default — the right instinct for UX-6, just under-designed. And the engine already re-derives and persists on every edit, so the interactive substrate for a much better UI is there.

---

## 2. Three design directions

Genuinely different IA bets. Scored against the §3 safety pressures and §8 UX requirements.

### Direction A — *Single list-first workspace with a master-detail body and a linear safety spine* **(recommended)**

One window. A persistent **safety spine** across the top owns the clean/unsafe verdict (loud, blocking). The body is **master-detail**: left = the decision list grouped by tier (From your list / Detected PII / Suggestions / Keeping in cleartext), each group collapsible with its own bulk action; right = the **side-by-side context** for the selected item (UX-2). The window has three **modes** via a segmented control — **Review · Send out · Restore** — so "the same surface in reverse" (UX-7) is literal: Restore is the mirror mode, not a bolted-on box. The full scrubbed-text blob is *not* shown on the home/Review surface (it trains skimming); it lives in **Send out**, behind the single prominent *Copy scrubbed text* action, with the key gated behind a deliberate disclosure. Miss-catching is a first-class mode of the context pane: a **Scan for misses** lens (FR-22) + **select-to-scrub** (FR-16).

- **Safety scorecard:** UX-3 ✔ (lens + select-to-scrub make catching a miss a 1-gesture action; the un-removed blob is only ever shown *inside* the scan affordance, where the eye is being directed at candidates, never as a passive copy-me panel). PG7/US9 ✔ (spine blocks copy by removing the path). UX-6 ✔ (one prominent action; key gated). UX-9 ✔ (separate cleartext group). UX-5 ✔ (grouping carries tier). UX-1/UX-2 ✔ (list is home, detail serves it). UX-7 ✔ (mirror mode).
- **Favors:** the repeat user and the careful first-timer equally; scales to 200 items via grouping/filter/keyboard.
- **Cost:** the most design surface to get right; the modes need clear state.

### Direction B — *Guided wizard for first run + dense power surface for repeat use*

Two surfaces. First-ever run = a stepper that teaches "the key is the secret" and walks Declared → PII → Suggestions → Copy out → Restore as discrete gated steps. Returning users get a dense single screen.

- **Safety scorecard:** strong on onboarding (US6, brief §9.12) and on *forcing* the unsafe gate. **But it fails the most important test:** a Next/Next/Next wizard *trains the click-through skim reflex* — the precise UX-3 anti-pattern, applied to a privacy decision. It also doubles the maintained surface, handles 200 items badly inside a stepper, and sits awkwardly as a modeless window floating next to Buzz.
- **Verdict:** great *onboarding idea*, wrong *primary architecture*. I'm pulling its one good part — a one-time teaching moment — into Direction A as a dismissible first-run overlay, without making the daily driver a wizard.

### Direction C — *Two focused windows: a Review/Send workspace and a separate Restore workspace*

Lean into the modeless multi-window nature, but make it intentional. Window 1 = Review & Send-out (list-first master-detail). Window 2 = Restore (mirror). Rationale: these are genuinely asynchronous jobs (spec §14 — you copy out now; the LLM replies later; you restore then).

- **Safety scorecard:** matches the real temporal split and keeps each window simple. **But** UX-7's "same surface in reverse" is weakened when restore is a *different* window; the key lives in Review yet is needed at Restore time (cross-window coupling); and two windows risk re-introducing the "which window do I trust?" confusion that the demo window already causes (M1).
- **Verdict:** its insight is right (Review/Send and Restore are temporally separate) — so I adopt it *as modes of one window* in Direction A rather than as two windows.

**Recommendation: Direction A.** It's the only one that makes miss-catching a real, first-class gesture (UX-3 — the hardest and highest-value requirement), satisfies UX-7 literally via the mirror mode, and absorbs the genuinely good parts of B (one-time teaching) and C (Review/Send/Restore as distinct phases) without their costs. The rest of this document specifies Direction A.

---

## 3. Recommended information architecture

**One top-level window, three modes, one loud safety spine.**

```
Cloak workspace  (one QWidget window, launched from the Cloak menu)
│
├── Safety spine (persistent, top)  ── owns the SAFE / BLOCKED-UNSAFE verdict; gates copy
│
├── Mode: REVIEW   ← home surface (UX-1)
│   ├── Decision list (left)  — grouped by tier + a "keeping in cleartext" group (UX-5/UX-9)
│   └── Context / side-by-side (right) — "is removing THIS correct?" (UX-2)
│       └── Scan-for-misses lens (FR-22) + select-to-scrub (FR-16)  ← UX-3 lives here
│
├── Mode: SEND OUT  ← the outbound action (UX-6)
│   ├── ONE prominent action: Copy scrubbed text
│   └── The key — gated behind a deliberate "Reveal the key" disclosure, branded as the secret
│
└── Mode: RESTORE   ← the mirror of Send-out (UX-7)
    └── paste reply → placeholders highlighted → real values filled back → (FR-17 flag home)

First-run overlay (once): teaches "the key is the secret" (US6). Dismissible, never nags.
About: folded into a Help/About affordance, not a window.
Declared-terms management: surfaced IN this window (and still editable in Buzz settings) — US2.
```

### Decision on the three current windows

- **`ReviewWindow` → becomes the workspace.** Keep and grow it into the three-mode surface above. This is the one real surface.
- **`CloakDemoWindow` → drop from the shipped menu.** It's a parallel sanitize path with none of the safety guarantees and a second "Copy scrubbed text" — a latent leak surface and brand confusion (M1). Keep it as a dev-only tool gated behind an env var / out of the packaged menu. Its "try on arbitrary text" onboarding value is real but must be served by something that carries the *real* guarantees — see the divergence note below.
- **`HelloWindow` ("About Cloak") → drop as a window.** Fold a one-line "what Cloak guarantees / what it explicitly does *not* (NG2)" into a Help/About affordance and into the first-run overlay. An about box doesn't merit a top-level menu peer.

**Net menu change:** from three peers (`Review & restore…` / `Sanitizer (manual demo)…` / `About Cloak…`) to one primary entry (`Review & restore…`) plus a lightweight `About / what Cloak protects…`.

*Divergence flagged:* if onboarding genuinely needs a sandbox to play in, build a clearly-labeled **"Sandbox — sample data, no guarantees"** mode *inside* the real window (reusing the real pipeline and the loud verdict), **not** a separate window with a separate engine. Rationale: any surface that can emit a "scrubbed" string must carry the fail-closed gate, or it's a leak vector by construction (PG7).

---

## 4. Textual wireframes (recommended direction)

All ASCII. Color is never load-bearing — every signal below is a word, a glyph that differs in *shape*, grouping/indent, or typography.

### 4.1 Review — the home surface (tiers + states)

```
┌─ Cloak ─────────────────────────────────────────────────────────── [_][▢][X] ┐
│ ╔═══════════════════════════════════════════════════════════════════════════╗ │ ← safety spine
│ ║ ✔  SAFE TO COPY   ·  9 items removed · 2 suggestions awaiting you          ║ │   (word + glyph,
│ ╚═══════════════════════════════════════════════════════════════════════════╝ │    not color)
│  Transcript:  [ Team sync — Jun 30, 14:02  ▾ ]                     [ Refresh ] │
│  ( • REVIEW )   ( Send out )   ( Restore )         ← mode segmented control     │
│ ┌──────────────────────────────────┬──────────────────────────────────────┐  │
│ │ DECISIONS                         │ CONTEXT — "is removing this correct?"│  │
│ │                                   │                                      │  │
│ │ ▣ FROM YOUR LIST — guaranteed  (4)│  Jane  →  {{PERSON-A}}      person    │  │
│ │   [Approve all from my list]      │  occurs 2× · matched your list       │  │
│ │   ▣ {{PERSON-A}}  Jane    2  Removed   …kickoff from ⟦Jane⟧, who handed…  │  │
│ │   ▣ {{PROJECT-A}} Apollo  3  Removed   …status on ⟦Project Apollo⟧ is…    │  │
│ │   ▣ {{PERSON-B}}  Bob     1  Removed   [ Scan for misses ▢ ]  [Select→scrub]│
│ │   ▣ {{ORG-A}}     Acme    1  Removed                                     │  │
│ │                                   │                                      │  │
│ │ # DETECTED PII — guaranteed    (3)│                                      │  │
│ │   [Approve all phone numbers]     │                                      │  │
│ │   ▣ {{EMAIL-1}}  cont…1  Removed  │                                      │  │
│ │   ▣ {{PHONE-1}}  (415)…1  Removed │                                      │  │
│ │   ▣ {{PHONE-2}}  (212)…1  Removed │                                      │  │
│ │                                   │                                      │  │
│ │ ◇ SUGGESTIONS — model's guesses, your call          (2 awaiting)         │  │
│ │   [Approve all]  [Reject all]     │                                      │  │
│ │   ◇ —  Riverside    1  ? place — awaiting   [Approve] [Reject]           │  │
│ │   ◇ —  Helix        2  ? org   — awaiting   [Approve] [Reject]           │  │
│ │                                   │                                      │  │
│ │ ┄ KEEPING IN CLEARTEXT ┄┄┄┄┄┄┄ (1)│  (struck-through, still visible — UX-9)│ │
│ │   ~~Q3~~  date  2  Kept   [Remove after all]                            │  │
│ └──────────────────────────────────┴──────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────┘
```

Notes: tier is the **group header + glyph shape** (`▣` filled guaranteed / `#` PII / `◇` hollow suggestion / `┄` cleartext), never a color. Guaranteed tiers are pre-approved checkboxes; **suggestions use explicit [Approve]/[Reject] buttons, not a checkbox** — see §6 for why. The scrubbed *blob* is deliberately absent here.

### 4.2 Item detail / side-by-side (UX-2)

```
│ CONTEXT — is removing this correct?                                           │
│                                                                               │
│   Item:  Acme           Type: org      Tier: FROM YOUR LIST (guaranteed)      │
│   Placeholder: {{ORG-A}}     Occurs: 1×     Why: matched your list            │
│ ┌── original (in context) ───────────┬── result (what gets sent) ──────────┐ │
│ │ …the contract with «Acme» closes   │ …the contract with {{ORG-A}} closes │ │
│ │ Friday, per Jane.                  │ Friday, per {{PERSON-A}}.           │ │
│ └────────────────────────────────────┴─────────────────────────────────────┘ │
│   [ Keep in cleartext ]      ‹ prev item ·  next item ›      (←/→ navigates)   │
│   [ Scan for misses ▢ ]   ← dims confirmed-safe text, raises residual entities │
```

The `«…»` marks the exact span from `placements`; the right pane shows the same sentence post-substitution so over-scrub (R2) is visible. "is removing this correct?" is answerable in one glance.

### 4.3 Send out — outbound + key (UX-6)

```
│ ( Review )   ( • SEND OUT )   ( Restore )                                      │
│ ╔═══════════════════════════════════════════════════════════════════════════╗ │
│ ║ ✔  SAFE TO COPY — verification passed. 9 items removed.                    ║ │
│ ╚═══════════════════════════════════════════════════════════════════════════╝ │
│                                                                               │
│              ┌─────────────────────────────────────────────┐                  │
│              │   📋  Copy scrubbed text                     │  ← one big,      │
│              └─────────────────────────────────────────────┘     primary,      │
│   This is the safe thing to paste into your LLM.                only action     │
│                                                                               │
│   ▸ Preview scrubbed text            (collapsed by default — view, not copy)   │
│                                                                               │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│ 🔒  THE KEY — this is the secret. Never paste this into an LLM.                │
│     The key maps placeholders back to the real values. Protect it like a       │
│     password. You only need it to restore a reply.                            │
│        [ Reveal the key ]   ⟵ deliberate, two-step; hidden by default          │
└───────────────────────────────────────────────────────────────────────────────┘
```

The key block is visually fenced off below a divider, lock-glyphed, with a warning sentence and a *deliberate* reveal; the copy-scrubbed action is large and alone above. Copying the right thing is effortless; copying the key is a conscious act (UX-6). When revealed, the key's own copy action carries a confirm ("Copy the secret key?").

### 4.4 Restore — the mirror (UX-7)

```
│ ( Review )   ( Send out )   ( • RESTORE )                                      │
│  Paste the LLM's reply (markdown is fine):                                     │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │ {{PERSON-A}} agreed to ship {{PROJECT-A}} by Friday; loop in {{ORG-A}}.   │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                          [ Restore originals ]                                 │
│  Restored (placeholders filled back from the key):                            │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │ ⟦Jane⟧ agreed to ship ⟦Project Apollo⟧ by Friday; loop in ⟦Acme⟧.         │ │ ← filled
│  │                                                                          │ │   spans
│  │ ⚠ Possible re-identification: "the founder who left in 2019" may         │ │   highlighted
│  │   describe a hidden item without using its placeholder.   (FR-17, later)  │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│  3 placeholders filled · 0 unmatched skipped                                  │
```

Same two-pane shape as Send-out, reversed: you paste the masked text and watch real values *return*, with filled spans highlighted (mirrors the highlighting in 4.2) and a reserved home for the FR-17 re-identification flag.

### 4.5 Suggestion review (FR-9 / FR-15)

```
│ ◇ SUGGESTIONS — model's guesses, your call             (2 awaiting · lower trust)│
│   These are NOT guaranteed. Cloak suspects them; you decide. Nothing here is    │
│   removed until you approve it.                                                  │
│   [ Approve all ]   [ Reject all ]                                               │
│ ┌─────────────────────────────────────────────────────────────────────────────┐│
│ │ ◇ Riverside     place   1×   "looks like a place"    [ Approve ]  [ Reject ] ││ ← A / R keys,
│ │ ◇ Helix         org     2×   "looks like an org"     [ Approve ]  [ Reject ] ││   auto-advance
│ └─────────────────────────────────────────────────────────────────────────────┘│
│   Approving one allocates its placeholder and moves it up into a guaranteed     │
│   group; rejecting drops it to "keeping in cleartext" (still visible — UX-9).   │
```

Visually inset, hollow glyph, explicit lower-trust framing — the band is unmistakably separate from the guaranteed set (PG6/FR-15). One keystroke clears each (A/R), focus auto-advances to the next pending (UX-4).

### 4.6 Empty state (US8) — a *success*, not a "did it run?"

```
│ ╔═══════════════════════════════════════════════════════════════════════════╗ │
│ ║ ✔  NOTHING SENSITIVE FOUND in this transcript.                             ║ │
│ ╚═══════════════════════════════════════════════════════════════════════════╝ │
│  Cloak scanned every segment against your declared list and the PII patterns. │
│  No declared terms and no PII were detected.                                  │
│                                                                               │
│  You can still:                                                               │
│   • [ Copy the transcript ]   (it's unchanged — nothing needed removing)      │
│   • [ Scan for misses ▢ ]     turn on the lens to double-check by eye         │
│   • [ Edit my declared list ]  add terms so they're caught next time (US2)    │
│                                                                               │
│  (Distinct from cold-start: "No transcripts yet — transcribe with Cloak on.") │
```

Reads as "done, you're clear" — and *still* offers the lens + declared-list edit so "nothing found" never becomes blind trust (NG2: undeclared completeness isn't guaranteed).

### 4.7 Unsafe state (US9 / PG7) — loud, blocking, copy physically removed

```
│ ╔═══════════════════════════════════════════════════════════════════════════╗ │
│ ║ ⛔  BLOCKED — UNSAFE. Cloak could NOT confirm your declared items were      ║ │
│ ║     removed. This text is NOT safe to share. Copy is disabled.             ║ │
│ ╚═══════════════════════════════════════════════════════════════════════════╝ │
│  What survived verification:                                                  │
│   • "Apollo"  — a declared term still present in the output (segment 4)        │
│                                                                               │
│  ┌─ scrubbed text ─────────────────────────────────────────────────────────┐ │
│  │  ▒▒▒▒  output withheld — cannot be shown or copied while unsafe  ▒▒▒▒    │ │ ← not rendered,
│  │        [ Show anyway (unsafe) ]   ← deliberate, warns again              │ │   not selectable
│  └─────────────────────────────────────────────────────────────────────────┘ │
│   [ Re-run verification ]   [ Add "Apollo" coverage ]   [ Report this ]        │
```

The fix for C2: in the unsafe state the scrubbed text is **not rendered into a selectable widget at all** — it's withheld behind a masked panel, so there's no `Ctrl+A` path. The verdict is a wall (glyph + ALL-CAPS word + reason), not a greyed button. "Show anyway" exists only as a deliberate, re-warned escape hatch, and even then never enables one-click copy.

---

## 5. Color-independent visual language (UX-5)

The rule: **every distinction is carried by at least two of {word, group/position, glyph-shape, typographic weight}** — color may *reinforce* but never *carry*.

### Three trust tiers

| Tier | Group header (word) | Glyph (shape, not hue) | Position | Type weight |
|---|---|---|---|---|
| Declared | "FROM YOUR LIST — guaranteed removed" | `▣` solid square | top group | bold header |
| PII | "DETECTED PII — guaranteed removed" | `#` hash | second group | bold header |
| Suggested | "SUGGESTIONS — model's guesses, your call" | `◇` hollow diamond | inset, lower, ruled off | lighter, indented |

Guaranteed (declared + PII) sit together up top as solid glyphs; suggestions are physically inset with a hollow glyph and an explicit "not guaranteed" sentence. The shape contrast (solid vs hollow) reads in grayscale and to a screen reader (the glyph has a text label).

### Four states

| State | Word shown | Form | Group/position |
|---|---|---|---|
| Approved | "Removed" | checkbox ticked `▣`, placeholder shown | in its tier group |
| Pending | "Awaiting your decision" | `[Approve] [Reject]` buttons (no checkbox) | suggestions group only |
| Rejected | "Kept in cleartext" | original **struck through** `~~…~~` | separate "KEEPING IN CLEARTEXT" group (UX-9) |
| Unsafe | "BLOCKED — UNSAFE / NOT confirmed removed" | `⛔` + ALL-CAPS in the spine; item pinned to top | owns the safety spine |

Strike-through is a *texture* (visible without color); the separate cleartext group is *spatial*; "unsafe" is *position + caps + glyph*. None of the four depends on a red/green read.

### Verdict (clean vs unsafe) — the highest-stakes signal

Never red-dot vs green-dot. **`✔ SAFE TO COPY`** vs **`⛔ BLOCKED — UNSAFE`**: different glyph shape, different word, and in the unsafe case the copyable text is physically withheld. A fully colorblind or grayscale user gets the verdict from the word and the missing-copy-path alone.

### Accessibility check

- **Grayscale:** every tier/state/verdict distinguishable by shape + word + position. ✔
- **Screen reader:** each row announces "From your list, Jane, person, occurs twice, removed"; glyphs are decorative-with-text-fallback, never icon-only. ✔
- **Keyboard:** full (see §6); no hover-only or color-only affordance. ✔
- **Contrast/zoom:** layout is grouping + weight, not hue; survives high-contrast themes and Qt default theming. ✔
- **The one thing to test:** that "✔ SAFE" green and "⛔ UNSAFE" red, *if* color is added as reinforcement, still differ unmistakably in deuteranopia — but since meaning never rests on them, this is a nicety, not a dependency.

---

## 6. Interaction + keyboard model

**Selection / navigation.** `↑`/`↓` move the selected row; the context pane (4.2) updates live. `←`/`→` jump prev/next item. `Tab` cycles list → context → mode control → primary action. Group headers are focusable and collapsible (`Space` collapses).

**Approve / reject (decide once, applied everywhere — UX-4/FR-3).**
- Guaranteed items are pre-approved. `Space` on a guaranteed row toggles it to *Kept in cleartext* (moves it to the cleartext group). 
- Suggestions use **explicit `A` (approve) / `R` (reject)** — *not* a checkbox. **Why diverge from the current checkbox model:** an unchecked checkbox is ambiguous between "pending" and "rejected," and a default-unchecked suggestion reads as a no-op the eye skips. Explicit Approve/Reject forces a real decision and makes "pending" a visible, un-skippable state (UX-5/UX-9). After A or R, focus **auto-advances to the next pending** — so a run of suggestions clears in N keystrokes (UX-4 / OQ5).

**Bulk (UX-4 — the named ones).** Each group header carries its own bulk action, and the spec's exact phrasings exist: **"Approve all from my list"** (declared group), **"Approve all phone numbers"** (PII subtype), **"Reject all dates"** (a type filter), plus **"Approve all" / "Reject all"** on suggestions. Keyboard: `Shift+A` / `Shift+R` approve/reject all in the focused group. Bulk-approving *guaranteed* tiers is safe by construction (PG2/PG6 — deterministic); bulk-approving *suggestions* is offered but framed as the lower-trust act it is.

**Clear the list fast (UX-4).** Open → guaranteed already done → `A A` (or `Shift+A` on suggestions) → done. The 12-item acceptance case clears in seconds without a mouse; "approve all from my list" resolves all declared in one action exactly as the sample acceptance requires.

**Miss-catching — the UX-3 centerpiece (FR-16 + FR-22).** Two complementary affordances, both making "catch a miss" *easier* than "approve a flag," not harder:

1. **Select-to-scrub (FR-16).** Select any text in the context/preview pane → a floating chip: **`Remove all "Helix" (3×)  ·  + add to my declared list?`**. One click removes every occurrence and (optionally) adds it to the declared list so it's auto-caught next time (closes the learn-loop M2 / US2 / US5). Catching a miss is now *one gesture* — at least as cheap as the `A` to approve a flag (UX-3 satisfied, literally).

2. **Suspicion lens (FR-22, opt-in, default off).** A toggle in the context pane (and an optional full-transcript scan overlay). When on, it **dims confirmed-safe text** (already-replaced placeholders + low-entropy tokens) and **raises contrast on residual entity-like tokens** (capitalized runs, number-shaped strings) that were *not* flagged. The eye is steered to *candidates for a miss*, not to the tidy list of hits. Critical framing rule, learned from how privacy tools fail: the lens labels its output **"candidates to check,"** never "all clear" — a scan the user *trusts* becomes a new skim surface, so it must always read as "look here," not "you're done."

**Why the un-removed transcript is never a passive blob.** Per UX-3, the only places un-removed text appears are (a) the context pane for the *selected* item, and (b) inside the suspicion-lens scan — both contexts where attention is being *directed at candidates*. It is never a big read-only copy-me panel on the home surface. That single IA choice is the difference between "review tool that trains skimming" and "review tool that hunts misses."

---

## 7. Phased implementation recommendation

Mapped onto the team's remaining work — deferred 5b polish (suspicion lens, informed auto-apply, detail view, styling) and Phase 6 — sequenced by **value-over-risk, smallest trust-improving step first.** The ordering principle: *do the pure risk-reduction that needs no new engine before the new capabilities; build the substrate (detail pane) before the thing that depends on it (miss-catching).*

**Phase A — Loud safety + trust hierarchy (smallest step, biggest leak-risk drop). No engine work; pure UI restructure of the existing window.**
- The blocking **unsafe state** (4.7): withhold the scrubbed text from any selectable widget when `meta.clean == False`; replace the greyed button with the wall. *Closes C2 — the highest-severity hole.*
- **Key hardening** (4.3 fencing + confirm-on-copy). *Closes C3.*
- **Group the list by tier** + a separate **"keeping in cleartext"** group with strike-through. *Closes C4 and H2.*
- **Drop the demo + about windows from the menu.** One-line menu change. *Closes M1.*

*Why first:* every item is risk reduction on what already ships, needs no new data or model, and removes two of the three leak-class holes. This is the "smallest first step that most improves trust" the brief asks for.

**Phase B — Master-detail + modes (the substrate). Uses existing `placements`; no engine change.**
- Split into **list (left) / context side-by-side (right)** using `placements` (UX-2 / H1).
- Add the **Review · Send out · Restore** segmented control; move the scrubbed blob off the home surface into Send-out behind the one prominent action (UX-1/UX-6/H4).
- Re-style **restore as the mirror mode** with filled-span highlighting and a reserved FR-17 slot (UX-7/H3).

**Phase C — Miss-catching (the headline UX-3 win; depends on B's context pane).**
- **Select-to-scrub** (FR-16) with "add to my declared list."
- **Suspicion lens** (FR-22) — the deferred 5b item, but now with a real home and the "candidates, not all-clear" framing.

**Phase D — Friction-trade & polish.**
- **Informed auto-apply** (FR-12/UX-8): the offer-moment (only after ≥1 reviewed run, using the persistent "have-reviewed" flag DEV_NOTES §8 calls for) + the persistent "removed N · Review · Undo" summary (FR-10).
- **First-run teaching overlay** (US6 / brief §9.12) — the salvaged-good-part of Direction B.
- **In-window declared-list management** (US2/M2), keeping Buzz-settings editing too.
- **Scale work** (M3): filter/search/sort/collapse for the 200-item case.

**Parallel track — Phase 6 (guarantee hardening), independent of UX.** PG1 offline proof, the FR-14 extensibility demo, and the README. One coupling to honor: ship the README's "the key is the secret / what we do *not* guarantee (NG2)" wording **in sync with the first-run overlay (Phase D)**, so the mental model is taught once and identically in both places.

```
risk-reduction ──────────────────────────────────────► new capability
 A (loud unsafe,        B (detail +        C (miss-       D (auto-apply,
    key guard,            modes +            catching:       onboarding,
    tier groups,          mirror restore)    FR-16 +         declared-list,
    drop demo)                               FR-22)          scale)
   └ no engine            └ uses placements  └ needs B       └ polish
        Phase 6 (offline proof · extensibility · README) runs alongside
```

---

## 8. Open risks & what I'd user-test before committing

- **The suspicion lens could create *new* false confidence.** The biggest design risk in the whole tool: a "scan" the user trusts becomes the very skim surface UX-3 warns against. *Test:* plant known misses in transcripts, measure catch-rate with the lens on vs. a flat list vs. nothing; check whether users read "candidates" as "all clear." If the lens doesn't beat the flat list on catch-rate, it's net-harmful and should ship off or not at all.
- **Is the key-gating enough friction — or too much?** If revealing/copying the key is annoying, users may copy it into a sticky note (worse than the in-app key). *Test:* observe the real restore flow; tune the disclosure so it's deliberate but not so heavy people route around it.
- **Bulk-approve vs. blind trust.** "Approve all from my list" is one click by design (it's deterministic/guaranteed). *Test:* do users understand that bulk-approving *declared* is safe but bulk-approving *suggestions* is a lower-trust act, or does one-click bulk train indiscriminate approval?
- **Empty vs. unsafe must look *opposite*.** US8 ("nothing found" = success) and US9 ("couldn't verify" = danger) carry inverse meanings. *Test:* show both cold; confirm no user reads "nothing found" as "something's wrong" or vice-versa.
- **Modeless coexistence with Buzz.** A three-mode window floating next to Buzz's main window — does it fight for screen space, get lost behind Buzz, or confuse "which window am I in?" *Test:* real dual-window use on a laptop screen.
- **"Quickly" is still undefined (OQ5).** UX-4 hangs on a target time to clear the list; set a number (e.g. ≤ N seconds / ≤ 1 action per item for the 12-item case) and test against it.
- **Scale reality (§9.10).** The 200-item dense transcript: does grouping + filter + keyboard actually keep it tractable, or does the list become the 10k-word hunt UX-1 forbids?
- **First-run teaching retention.** Does a one-time overlay actually lodge "the key is the secret," or do users need a persistent reminder (the Send-out key fencing is the safety net if not)?
- **Re-identification flag (FR-17, deferred).** When it lands in Restore: where does it surface without crying wolf so often users learn to ignore it? Worth prototyping the threshold before building.

---

### Appendix — spec-ID coverage map

UX-1 §3/§4.1 · UX-2 §4.2/H1 · UX-3 §6 (lens+select-to-scrub) · UX-4 §6 (bulk+keyboard) · UX-5 §5 · UX-6 §4.3/C3 · UX-7 §4.4/H3 · UX-8 §7 Phase D · UX-9 §4.1/§5/H2 · US8 §4.6 · US9 §4.7/C2 · FR-9/FR-15 §4.5 · FR-10/FR-12 Phase D · FR-16/FR-22 §6 · FR-17 §4.4 · PG6 §1 C4/§5 · PG7 §4.7 · PG8 §4.3.
**Flagged divergences:** (1) scrubbed text is *not* a passive home-surface blob — it lives in Send-out behind the action (UX-3 > convenience); (2) suggestions use explicit Approve/Reject buttons, not checkboxes (UX-5/UX-9 clarity); (3) demo window dropped from the shipped menu, sandbox value re-homed inside the guaranteed pipeline (PG7).
