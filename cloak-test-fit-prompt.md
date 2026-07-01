# Cloak — Test-Fit Prompt for a Claude Design Surface

**Purpose:** generate an interactive *test-fit* of Cloak's recommended UX (Direction A, **v2** — folds in the persona-walkthrough feedback) — a quick, throwaway prototype to confirm the information architecture and the safety affordances "fit" before any PyQt6 is written.

> **What changed in v2** (vs. the first test-fit): the Review list collapses from four groups to **two action zones** (Removed / Suggestions) plus a collapsed cleartext group; a bounded **"not touched — confirm these" reverse list** is added for catching misses; **select-to-redact also offers "add to my list"** in one gesture; the empty state shows **scan evidence**; Send-out gets a **copy-confirmation toast**; and the "key is the secret" lesson is taught **at the Send-out moment**, not as an upfront overlay.

## How to use this

1. Open a Claude design/artifact surface (any Claude that can produce an interactive HTML artifact — e.g. start a new Claude conversation and it will render the HTML inline, or use whatever "Claude design" entry point you have).
2. **Paste everything inside the `=== PROMPT ===` fence below** as your message. It's self-contained — the design surface does not need the critique doc.
3. You'll get a single `.html` file. Open it in a browser: click the mode tabs (Review / Send out / Restore) and flip the state toggle (Safe / Unsafe / Empty). That's the whole test-fit.
4. Iterate by replying with changes ("make the unsafe banner heavier," "show the side-by-side on row select").

**Why HTML and not PyQt6 directly:** the prompt constrains the design to widgets that map 1:1 onto Qt, and asks for an explicit *widget-mapping* annotation on each region — so the HTML is a faithful stand-in for the PyQt6 window, not a web aesthetic you'd have to throw away. The translation table at the end is the bridge from the approved test-fit to the real build.

---

=== PROMPT ===

You are a senior product designer building an **interactive test-fit** (a quick, disposable HTML prototype) of a desktop application window. Output a **single self-contained `.html` file** (inline CSS + vanilla JS, no external assets, no frameworks, no CDN). It must look like a **native desktop app window**, not a web app, and every visible region must map cleanly onto a **PyQt6** widget (I'll list the allowed widgets — stay inside them).

### The product (context you need)

**Cloak** is an offline, reversible sensitive-information sanitizer that runs as a plugin inside a desktop transcription app. After a transcript is produced, Cloak replaces sensitive items with reversible placeholders like `{{PERSON-A}}`, `{{EMAIL-1}}`, `{{PROJECT-A}}`. The user copies the *scrubbed* text into a cloud LLM, works with it, pastes the reply back, and Cloak restores the real values from a local **key**. Mental model to teach: **the key is the secret — the scrubbed text is safe to share; the key is the thing to protect.**

Items belong to trust tiers, but **the only split that matters at the screen is two-way**:
- **Removed — guaranteed.** Both the user's **declared** terms (people, projects, clients) and **detected PII** (email, phone, SSN, IP, URL, card) — all removed automatically and verified. Provenance (which one it was) is a small per-row label, *not* a separate group: at approval time the user only cares that it's found and removed.
- **Suggestions — the model's guesses** (undeclared names/orgs/places). **Held — never auto-applied; the user approves or rejects each.** Visibly lower-trust and separate from the guaranteed zone.

And one of four **states**: **Approved** (removed), **Pending** (a suggestion awaiting decision), **Rejected** (deliberately kept in cleartext), and a window-level **Unsafe** condition.

### The non-negotiable design pressures (this is a privacy tool — read twice)

The catastrophic failure is a **false negative**: a real sensitive item that is *not* removed and gets shipped to the cloud. So:

1. **Do not train the eye to skim what was removed.** The home surface is a *list of decisions*, not a big read-only scrubbed-text blob. Catching a *missed* item must be at least as easy as approving a flagged one.
2. **Unsafe must be a loud, blocking wall — not a greyed button.** When the app can't confirm removal, the scrubbed text is **withheld** (not rendered into any selectable field) and copy is impossible. The verdict is a word + glyph, never just a color.
3. **The key reads as the secret; copying the wrong thing is hard.** "Copy scrubbed text" is the single prominent action. The key is fenced off, lock-marked, hidden behind a deliberate reveal, with a warning.
4. **Rejected items stay visible** — struck through, in a separate "Keeping in cleartext" group, re-approvable in one click. (Absence is dangerous information.)
5. **Meaning never depends on color alone.** Tier and state must read in grayscale via words, grouping/position, glyph *shape*, and type weight. Color may reinforce, never carry.

### What to build — ONE window, three modes, three state toggles

Keep it simple: **a single window.** Do not make seven separate screens. Reach every important state through:
- a **mode tab row** at top: **Review** · **Send out** · **Restore** (maps to QTabWidget / QStackedWidget);
- a small **demo state toggle** (a labeled control in the title strip, clearly a prototype-only affordance): **Safe** · **Unsafe** · **Empty** — flipping it changes the safety spine and the Review body so a reviewer can see all three conditions.

**Persistent across all modes — the safety spine** (a banner under the title): in *Safe* it reads `✔  SAFE TO COPY · 9 removed · 2 suggestions awaiting you`; in *Unsafe* it reads `⛔  BLOCKED — UNSAFE · could not confirm your declared items were removed`; in *Empty* it reads `✔  NOTHING SENSITIVE FOUND in this transcript`. Word + glyph differ; do not rely on red/green.

#### Mode 1 — REVIEW (the home surface; a master-detail split → QSplitter)

A single top-of-list action **`[ Approve everything detected ]`** clears the whole guaranteed zone at once (the named bulk actions like "approve all from my list" / "approve all phone numbers" are a small filter on it, *not* their own groups).

*Left pane — the decision list as TWO action zones + a collapsed group (→ QTreeWidget with collapsible top-level group rows).* In order:
- **REMOVED — guaranteed** (solid glyph ▣, bold header). Declared and PII rows live together here; the last column is a small **provenance label** (your list / phone / email …), not a separate group. Rows: `▣ {{PERSON-A}}  Jane    2  your list`, `▣ {{PROJECT-A}} Apollo  3  your list`, `▣ {{EMAIL-1}}   con…@…  1  email`, `▣ {{PHONE-1}}   (415)…  1  phone`.
- **SUGGESTIONS — model's guesses, your call** (hollow glyph ◇, visually inset/indented, caption "not guaranteed — nothing here is removed until you approve it"). Rows use explicit **`[Approve]` / `[Reject]` buttons, not checkboxes**: `◇  Riverside  place  1  awaiting`, `◇  Helix  org  2  awaiting`.
- **▸ Keeping in cleartext (1)** — a **collapsed-by-default** quiet group; expanded it shows `~~Q3~~  date  2  Kept  [Remove after all]`, original **struck through**, still visible and one-click re-approvable. Collapsed so it never competes with live decisions.

Below the two zones, a **reverse "miss-catching" strip** (→ a low QFrame + QLabel + small list): **`⚲ Not touched, but entity-shaped — confirm these are fine:  "Karen" (1)  [Redact + add]`**. This is the bounded list of capitalized/entity-like tokens Cloak did *not* remove. It must read as **"candidates to confirm," never "all clear"** — its whole job is to make catching a miss as cheap as approving a find, without becoming a new surface the user blindly trusts.

*Right pane — context / side-by-side* (→ two read-only QPlainTextEdit side by side, or a QTextEdit with highlight). When a row is selected, show: item, provenance, placeholder, occurrence count, "why flagged"; then the **original sentence with the matched span marked** beside **the same sentence after substitution** ("is removing *this* one correct?"). Include a **`[ Scan for misses ▢ ]`** toggle and, on text selection, a single **`Redact this everywhere · also always treat as sensitive?`** affordance — one gesture that both removes every occurrence *and* offers to add it to the user's list (so catching a miss and growing the declared list are the same action). These can be visually present without full behavior in the test-fit.

In the **Empty** state, the Review body replaces the list with a calm "nothing sensitive found" panel that **proves it ran** — show scan evidence like **`Scanned 14 detectors across 36 segments · 0 matches`** — plus `[Copy the transcript]`, `[Scan for misses ▢]`, `[Edit my declared list]`. It must read as *success/done with receipts*, not "did it even run?".

#### Mode 2 — SEND OUT (the outbound action; → QVBoxLayout)

- The safety spine on top (same as Review).
- **One large, primary button: `📋 Copy scrubbed text`**, centered, with caption "This is the safe thing to paste into your LLM." It is the *only* prominent action. On click, show a brief **confirmation toast — `✔ Scrubbed text copied — safe to paste`** so the user *knows* they grabbed the safe artifact (not the key).
- A collapsed **`▸ Preview scrubbed text`** disclosure (view, not a big copy-me blob).
- Below a divider, a **fenced key block**: `🔒 THE KEY — this is the secret. Never paste this into an LLM.` + one explanatory line + a **`[ Reveal the key ]`** button (hidden by default; revealing shows the key and a `[Copy the secret key]` that warns on click). **First-use teaching:** the *first* time the user reaches Send-out, a one-time inline note next to the key teaches "the key is the secret" *here, at the moment it matters* (not an upfront modal) — dismiss-once, tied to this action.
- In the **Unsafe** state, this mode disables/withholds the copy action and shows the blocking wall instead (no copyable scrubbed text anywhere).

#### Mode 3 — RESTORE (the mirror of Send-out; → QVBoxLayout)

- A paste box (editable QPlainTextEdit) prefilled with `{{PERSON-A}} agreed to ship {{PROJECT-A}} by Friday; loop in {{ORG-A}}.`
- A `[ Restore originals ]` button.
- A read-only result box showing the same text with placeholders **filled back** to real values (highlight the filled spans), plus a small reserved callout line for a future "possible re-identification" flag, and a footer that reports both directions: `3 placeholders filled · ⚠ 1 still unresolved in the text` — an unresolved tag the user doesn't notice must be surfaced, not silently skipped.

### Visual language (make these legible in grayscale)

- **Zones** by group header word + glyph shape + position + weight: the guaranteed **Removed** zone (`▣` solid) sits up top, bold header; **Suggestions** (`◇` hollow) inset and lighter, ruled off below it. The guaranteed-vs-suggested line is the primary two-way split — make it unmistakable.
- **States** by word + form: Approved = "Removed" + filled mark + placeholder shown; Pending = "awaiting" + Approve/Reject buttons (no checkbox); Rejected = "Kept" + strikethrough in the collapsed cleartext group; Unsafe = ALL-CAPS + `⛔` owning the spine.
- **Verdict** never red-dot/green-dot: `✔ SAFE TO COPY` vs `⛔ BLOCKED — UNSAFE` differ in word and glyph, and unsafe physically hides the copyable text.

### Styling — desktop/Qt-plausible

System UI font stack; tight, native-feeling spacing; a real **menu bar** strip at the very top reading `File  Edit  View  Cloak  Help` with **Cloak** subtly indicated as active. No rounded "card" web aesthetics, no gradients, no drop shadows, no SVG icon sets — use **unicode glyphs** (▣ # ◇ ✔ ⛔ 🔒 📋 ⚠) and plain bordered panels. Think "a clean native Qt window with default-ish theming," not "a SaaS landing page." Monospace only for placeholders/key text.

### Allowed widget vocabulary (stay inside this — it's what we'll build in PyQt6)

Use only layouts/controls that map to: `QMainWindow` / `QWidget`, `QMenuBar`, `QTabWidget` or `QStackedWidget` (modes), `QSplitter` (master-detail), `QTreeWidget` (grouped collapsible list) or `QTableWidget`, `QGroupBox`, `QPushButton` / `QToolButton`, `QCheckBox`, `QComboBox` (transcript selector), `QLabel`, `QPlainTextEdit` / `QTextEdit`, `QFrame` (dividers). Build the layout with the HTML equivalents of `QVBoxLayout` / `QHBoxLayout` / `QGridLayout` / `QSplitter`. **Do not** use anything with no Qt analogue.

### Required output

1. The single `.html` file (works offline, double-click to open).
2. At the **bottom of the page**, a small collapsed `▸ Qt widget map` section listing each region → its intended PyQt6 widget (e.g. "mode tabs → QTabWidget; decision list → QTreeWidget with top-level group items; safety spine → QFrame + QLabel; context pane → QSplitter of two read-only QPlainTextEdit"). This is the handoff bridge.

### This test-fit passes if

- The home surface is a **decision list of two zones** (Removed / Suggestions), and there is **no passive scrubbed-text blob** competing for the eye on Review.
- The **reverse "not touched — confirm these" strip** is present and reads as *candidates to check*, so catching a miss looks as cheap as approving a find — and **select-to-redact also offers "add to my list"** in one gesture.
- Flipping to **Unsafe** makes copy impossible and the scrubbed text un-selectable/withheld — loudly.
- The **key** is clearly the protected secret, copying the scrubbed text is the obvious easy action, and the copy gives a **safe-to-paste confirmation**.
- The **Empty** state proves it ran (scan evidence), reading as *done*, not "did it run?".
- **Zone and state are fully readable with the page in grayscale** (try it — desaturate and it must still parse); rejected items remain visible (collapsed, struck-through), suggestions visibly lower-trust.

### Out of scope (keep it simple)

No real sanitization logic, no persistence, no settings dialog, no onboarding overlay, no animation. Static sample data is fine. One window, three modes, three demo states — nothing more.

=== END PROMPT ===

---

## Notes for you (not part of the prompt)

- The prompt deliberately collapses the seven wireframes from the critique into **one window with mode tabs + a demo-state toggle**, per your "simplicity is the soul of design." The side-by-side, suggestion-review, and empty/unsafe states all live *inside* that single window rather than as separate screens — which also happens to be the actual recommended IA, so the test-fit and the design reinforce each other.
- The **Qt widget map** at the bottom is the part that makes this translate cleanly into your environment: it names the real PyQt6 widget behind every region, so an approved HTML test-fit becomes a build checklist, not a redesign.
- If the first output drifts toward web aesthetics, reply with: *"Too web-styled — make it look like a default-themed native Qt window: plain bordered panels, system font, menu bar, unicode glyphs only."*
- Want me to **run this prompt myself and hand you the HTML test-fit directly** instead of (or before) you trying the design surface? I can generate it in one step.
