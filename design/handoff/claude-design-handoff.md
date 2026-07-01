# Handoff: Cloak — sensitive-information sanitizer (PyQt6 plugin window)

## Overview
Cloak is an **offline, reversible sensitive-information sanitizer** that runs as a plugin inside a
desktop transcription app. After a transcript is produced, Cloak replaces sensitive items with
reversible placeholders (`{{PERSON-A}}`, `{{EMAIL-1}}`, `{{PROJECT-A}}`…). The user copies the
scrubbed text into a cloud LLM, pastes the reply back, and Cloak restores the real values from a
**local key**.

**The mental model the UI must teach: _the key is the secret._** The scrubbed text is safe to share;
the key is the thing to protect.

This bundle is the approved **design test-fit**. Build the real thing in **PyQt6**.

---

## About the design file
`Cloak Test-Fit.html` is a **design reference**, not production code. It is an HTML stand-in for the
PyQt6 window. **Do not ship the HTML or wrap it in a WebView.** Reimplement it as native PyQt6
widgets. The HTML was deliberately constrained to widgets that map 1:1 onto Qt (see the widget map
at the bottom of the page and the table below), so the translation is mechanical.

How to use it:
1. Open the file in a browser. It works offline (double-click).
2. Click the mode tabs (**Review · Send out · Restore**) and flip the demo-state toggle
   (**Safe · Unsafe · Empty**) in the top-right of the toolbar. Those two controls expose every
   screen state you must build.
3. Screenshot states as you go and match them.

## Fidelity
**High-fidelity for layout, hierarchy, copy, and behavior.** Match the structure, the exact text,
the widget choices, the grouping, and the safety affordances precisely. Colors/spacing are
Qt-default-plausible neutrals — reproduce them via a QSS stylesheet, but you may align them to your
app's existing theme as long as the **grayscale-readability rule** (below) still holds.

---

## ⚠ Non-negotiable design pressures (read before building — this is a privacy tool)
The catastrophic failure is a **false negative**: a real sensitive item that is NOT removed and gets
shipped to the cloud. Every one of these rules exists to fight that. Do not "simplify" them away.

1. **The home surface is a list of decisions, not a read-only scrubbed-text blob.** Catching a
   *missed* item must be at least as easy as approving a flagged one. Never add a big passive
   "here's your scrubbed text" panel to the Review screen.
2. **Unsafe is a loud, blocking wall — not a greyed-out button.** When removal can't be confirmed,
   the scrubbed text is **withheld** (never rendered into any selectable/copyable field) and copy is
   impossible. The verdict is a **word + glyph**, never just a color.
3. **The key reads as the secret.** "Copy scrubbed text" is the one prominent action. The key is
   fenced off, lock-marked, hidden behind a deliberate reveal, and warns on copy.
4. **Rejected items stay visible** — struck through, in a separate "Keeping in cleartext" group,
   re-approvable in one click. (Absence is dangerous information.)
5. **Meaning never depends on color alone.** Tier and state must be readable in grayscale via words,
   grouping/position, glyph shape, and type weight. _Test: desaturate the window — it must still
   parse._ Color may reinforce, never carry.

---

## Information architecture: ONE window, three modes, three demo states
A single `QMainWindow`. Do **not** build separate dialogs per state. Everything is reached via:
- **Mode tabs** at top: Review · Send out · Restore → `QTabWidget` (or `QStackedWidget` + custom tab strip).
- **A safety spine** (a banner under the toolbar) — persistent across all three modes.
- A **demo-state toggle** (Safe/Unsafe/Empty) in the toolbar — this is a **prototype-only**
  affordance for the test-fit. In the real plugin, the safety state is computed from the sanitizer
  result, not chosen by the user; keep the spine + state-driven rendering, drop the toggle (or hide
  it behind a debug flag).

### Two-way split that matters
Items have trust tiers, but at the screen the only split that matters is **two-way**:
- **Removed (guaranteed)** — declared terms (people, projects, clients) **and** detected PII
  (email, phone, SSN, IP, URL, card). All auto-removed and verified. Provenance is a small per-row
  label, not a separate group.
- **Suggestions (held)** — the model's guesses (undeclared names/orgs/places). Never auto-applied;
  the user approves/rejects each. Visibly lower-trust, separate from the guaranteed zone.

Item states: **Approved** (removed) · **Pending** (awaiting decision) · **Rejected** (kept in
cleartext) · plus the window-level **Unsafe** condition.

---

## Widget map (region → PyQt6 widget)
| Region | PyQt6 widget |
|---|---|
| Window | `QMainWindow` |
| Menu bar (`File Edit View Cloak Help`, Cloak active) | `QMenuBar` |
| Toolbar: transcript selector | `QComboBox` |
| Toolbar: demo-state toggle (prototype-only) | `QButtonGroup` of checkable `QToolButton` |
| Safety spine | `QFrame` + `QLabel` (word + glyph) |
| Mode tabs | `QTabWidget` / `QStackedWidget` |
| Review master-detail split | `QSplitter(Qt.Horizontal)` |
| Decision list (grouped, collapsible) | `QTreeWidget` with top-level group items |
| Bulk action + filter | `QPushButton` + `QComboBox` |
| Suggestion Approve/Reject | `QPushButton` per row |
| Miss-catching strip | `QFrame` + `QLabel` + small list + `QPushButton` |
| Context pane (side-by-side) | two read-only `QPlainTextEdit` (original vs substituted) |
| Scan-for-misses toggle | `QCheckBox` / checkable `QToolButton` |
| Select-to-redact affordance | `QPushButton` + `QCheckBox` |
| Send-out copy / key block | `QVBoxLayout`: primary `QPushButton`, disclosure `QToolButton`, fenced key `QGroupBox` with reveal `QPushButton` |
| Restore | `QVBoxLayout`: editable `QPlainTextEdit`, `QPushButton`, read-only `QPlainTextEdit` result |
| Toast | transient frameless `QLabel` overlay (auto-dismiss ~2.4 s) |

Stay inside this vocabulary. Nothing in the design needs a widget without a Qt analogue.

---

## Screen 1 — REVIEW (the home surface)
`QSplitter(Horizontal)`. Above the splitter: a single bulk action row.

**Bulk action row:** `[ Approve everything detected ]` (`QPushButton`) + a filter `QComboBox`
(`all detected` / `approve all from my list` / `approve all phone numbers` / `approve all emails`).
The named bulk actions are a *filter on the one button*, not their own groups.

### Left pane — decision list (`QTreeWidget`, collapsible top-level groups, in this order)
**1. REMOVED — guaranteed** (solid glyph `▣`, bold header, caption "guaranteed · declared + detected,
verified"). Declared + PII rows live together. Each row: glyph · placeholder (monospace) + `was: <value>`
· occurrence count · a small provenance pill (`your list` / `email` / `phone` / `ssn` / `ip` / `url` /
`card`). Sample rows (9):

| Placeholder | was | count | provenance |
|---|---|---|---|
| `{{PERSON-A}}` | Jane | 2× | your list |
| `{{PROJECT-A}}` | Apollo | 3× | your list |
| `{{CLIENT-A}}` | Northwind | 1× | your list |
| `{{EMAIL-1}}` | con…@… | 1× | email |
| `{{PHONE-1}}` | (415)… | 1× | phone |
| `{{SSN-1}}` | •••-••-1234 | 1× | ssn |
| `{{IP-1}}` | 192.168… | 1× | ip |
| `{{URL-1}}` | intra…/… | 1× | url |
| `{{CARD-1}}` | ••••4242 | 1× | card |

**2. SUGGESTIONS — model's guesses, your call** (hollow glyph `◇`, **inset/indented**, lighter
weight, ruled off below Removed). Caption: _"not guaranteed — nothing here is removed until you
approve it."_ Rows use explicit **`[Approve]` / `[Reject]` buttons, NOT checkboxes**. Once decided,
the buttons are replaced by an italic "decided" label and the status text updates
(`approved · removed` or `kept in cleartext`).

| Suggestion | kind | count | status |
|---|---|---|---|
| Riverside | place | 1× | awaiting |
| Helix | org | 2× | awaiting |

**3. ▸ Keeping in cleartext (N)** — collapsed by default. Expanded, each row shows the original
**struck through** + `date · 2× · Kept` and a one-click `[Remove after all]`. Sample: `~~Q3~~`.

### Reverse "miss-catching" strip (below the groups, inside the left pane)
A low `QFrame`: `⚲ Not touched, but entity-shaped — confirm these are fine:` then a token chip
`"Karen" (1)` + `[Redact + add]`. It must read as **"candidates to confirm,"** never "all clear."
Its job is to make catching a miss as cheap as approving a find — without becoming a surface the user
blindly trusts.

### Right pane — context / side-by-side (two read-only `QPlainTextEdit`)
On row selection, show a meta block (item value, kind, provenance, placeholder, occurrence count,
"why flagged") then two boxes labelled **ORIGINAL** (matched span highlighted) and **AFTER
SUBSTITUTION** (placeholder highlighted), under the prompt _"Is removing this one correct?"_. For a
**suggestion**, the right box is labelled **"If approved"** and shows the *proposed* placeholder
(`{{PLACE-A}}`, `{{ORG-A}}`) — nothing is actually removed.

Also in the right pane: a `[ Scan for misses ▢ ]` toggle, and a select-to-redact affordance:
**`[Redact this everywhere]` + a checkbox `also always treat as sensitive (add to my list)`** — one
gesture that both removes every occurrence and offers to grow the declared list. (Catching a miss and
growing the list are the same action.)

### Review in the EMPTY state — replace the split with a "proof it ran" panel
Centered: big `✔`, "Nothing sensitive found", subtext "This is a result, not a skip", then **scan
evidence** in a monospace box: `Scanned 14 detectors across 36 segments · 0 matches · key not needed`,
then `[Copy the transcript]`, `[Scan for misses ▢]`, `[Edit my declared list]`. It must read as
**done, with receipts** — not "did it even run?".

### Review in the UNSAFE state
Keep the list visible so the user can act, but add a thick blocking strip at the top of the body:
`⛔ OUTPUT WITHHELD. A declared item could not be confirmed removed (see ⚠ below). No scrubbed text is
produced until this is resolved.` Mark the unconfirmed row (e.g. `{{PROJECT-A}}`) with a
`⚠ NOT CONFIRMED` badge instead of its provenance pill. Replace the right-pane side-by-side with a
**CONTEXT WITHHELD** notice (no substitution preview while unconfirmed).

---

## Screen 2 — SEND OUT (`QVBoxLayout`)
- One large primary `QPushButton`: **`📋 Copy scrubbed text`**, centered, caption _"This is the safe
  thing to paste into your LLM."_ It is the only prominent action. On click → copy to clipboard +
  brief **toast** `✔ Scrubbed text copied — safe to paste`.
- A collapsed disclosure `▸ Preview scrubbed text` (view-only, not a big copy-me blob).
- A divider, then the **fenced key block** (`QGroupBox`):
  - Dark header bar: `🔒 THE KEY — this is the secret.  Never paste this into an LLM.`
  - One explanatory line.
  - **First-use teaching:** the first time the user reaches Send-out, show a one-time inline note
    next to the key — _"💡 First time here: remember — the key is the secret. Share the scrubbed text
    freely; guard this key."_ Dismiss-once (✕), tied to this moment — **not** an upfront modal.
  - `[ Reveal the key ]` — key hidden by default. Revealed, it shows the mapping (monospace) and a
    `[⚠ Copy the secret key]` that warns on click (`⚠ Secret key copied — never paste this into an
    LLM`) + a `[Hide key]`.
- **Unsafe state:** replace the whole copy area with the blocking wall (`⛔ BLOCKED — UNSAFE`, big
  glyph, explanation). **No copyable/selectable scrubbed text anywhere on the screen.**

---

## Screen 3 — RESTORE (`QVBoxLayout`)
- Editable paste box (`QPlainTextEdit`) prefilled with:
  `{{PERSON-A}} agreed to ship {{PROJECT-A}} by Friday; loop in {{ORG-A}}.`
- `[ Restore originals ]` button.
- Read-only result box: the same text with placeholders filled back (filled spans highlighted),
  leaving any unresolved tag visible and flagged. With the prefill above:
  `Jane Okafor agreed to ship Apollo by Friday; loop in {{ORG-A}}.` (`{{ORG-A}}` has no key entry →
  shown struck/flagged).
- A reserved callout line: _"Reserved — possible re-identification flag would appear here."_
- Footer reporting **both directions**: `2 placeholders filled · ⚠ 1 still unresolved in the text`.
  An unresolved tag must be **surfaced, not silently skipped.**

---

## Safety spine — three states (persistent banner, word + glyph differ; never red/green only)
| State | Spine text | Glyph | Treatment |
|---|---|---|---|
| Safe | `SAFE TO COPY · 9 removed · 2 suggestions awaiting you` | `✔` | calm; left accent rule |
| Unsafe | `BLOCKED — UNSAFE — could not confirm your declared items were removed` | `⛔` | ALL-CAPS, heavy, thick dark/red wall owning the spine |
| Empty | `NOTHING SENSITIVE FOUND in this transcript` | `✔` | calm |

---

## State model
```
window:
  mode:        'review' | 'sendout' | 'restore'
  safety:      'safe' | 'unsafe' | 'empty'   # real plugin: derived from sanitizer result
  selected_item_id: str | None               # drives the Review right pane
per item:
  status: 'approved' | 'pending' | 'rejected'
suggestions: { id -> 'awaiting' | 'approved' | 'rejected' }
flags:
  key_revealed:      bool   # Send-out
  key_note_dismissed:bool   # first-use teaching, once
  sendout_visited:   bool   # gates the first-use note
  cleartext_expanded:bool   # Review group
  preview_expanded:  bool   # Send-out disclosure
  scan_misses:       bool   # toggle
  redact_add_to_list:bool   # select-to-redact checkbox
  restored:          bool   # Restore result shown
```

### Signals / slots (suggested wiring)
- Mode tab `currentChanged` → switch stack; entering Send-out sets `sendout_visited = True`.
- Removed/suggestion row `itemClicked` → set `selected_item_id`, repopulate right pane.
- `Approve everything detected` → mark all Removed approved (no-op in test-fit; toast).
- Suggestion `Approve` → status `approved`, remove from list / show "decided", toast.
- Suggestion `Reject` → status `rejected`, moves to "Keeping in cleartext", toast.
- `Copy scrubbed text` → clipboard set + toast. **Disabled/withheld when `safety == 'unsafe'`.**
- `Reveal the key` → toggle `key_revealed`. `Copy the secret key` → clipboard + warning toast.
- `Restore originals` → `restored = True`, fill result, compute filled/unresolved counts.

---

## Design tokens (QSS-plausible neutrals — grayscale-first)
```
window bg          #f2f1ef        title bar bg      #e4e2de
menu bar bg        #efeeec        panel/white       #ffffff / #fbfbfa
border (light)     #b9b6b1        border (mid)      #9a968f / #6f6b65
text               #1d1c1a        muted text        #6b6864 / #8a8680
selected row bg    #dde6f0        button face       #dcdad5 / #e3e1dc

safe accent        #2f6b3d  (spine bg #e9f1ea, left rule 7px)
empty accent       #4a6b7a  (spine bg #eaf0f2)
unsafe             bg #3a1c1c / #2a1414, border #b3261e, text #ffe6e1   (heavy wall)

highlight: original-match  bg #f3d9d4, underline #b3261e
highlight: substituted     bg #dfe9df, underline #2f6b3d

font (UI)     system stack (-apple-system / Segoe UI / Roboto)
font (mono)   ui-monospace / Menlo  — placeholders & key ONLY
glyphs        ▣ ◇ ✔ ⛔ 🔒 📋 ⚠ ⚲   (unicode; do NOT introduce an SVG icon set)
```
No rounded "card" web styling, no gradients, no drop shadows. Plain bordered panels, native spacing.

## Assets
None. The UI is plain widgets + unicode glyphs only.

## Files in this bundle
- `Cloak Test-Fit.html` — the offline, interactive design reference (the source of truth for look +
  behavior). Open it, drive the tabs and the demo-state toggle, screenshot, and match.
