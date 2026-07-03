# Sanitizer

Sanitizer replaces sensitive information in a transcript (the names, PII, and codenames
you care about) with reversible placeholders **before** you send the text to a cloud
LLM, then restores the originals from a local **key** when the reply comes back.

```
   Jane briefed Apollo at jane@acme.com
                │
        ┌───────▼────────┐        scrubbed text  →  paste into your LLM
        │     Sanitizer      │  ───────────────────────────────────────────►
        └───────┬────────┘   {{PERSON-A}} briefed {{PROJECT-A}} at {{EMAIL-1}}
                │
              key.json  (stays on your machine)
    {{PERSON-A}} = Jane · {{PROJECT-A}} = Apollo · {{EMAIL-1}} = jane@acme.com
                │
        LLM reply about {{PERSON-A}}  →  Restore  →  the real names back
```

Everything happens **on your machine**. The guaranteed path makes no network calls
and needs no extra packages.

## The one idea: the key is the secret

The **scrubbed text is safe to share**: that's the whole point; paste it anywhere.
The **key** is the thing to protect: it's the map from placeholders back to real
values. Sanitizer keeps it in a separate file (`key.json`), never inside the scrubbed
text, and marks it clearly in the UI. Guard the key; share the scrubbed text freely.

## How you use it

Transcribe as usual (sanitization happens in the background; your stored transcript is
never modified), then **Sanitizer → Review & restore…** to review removals, approve
suggestions, copy the scrubbed text, and later restore the reply. The full illustrated
walkthrough is in the [repository README](https://github.com/c-owen/Sanitizer#using-it); this file is the
reference for the guarantees, settings, and file locations.

If Sanitizer **can't confirm** your declared terms were removed, it shows **BLOCKED —
UNSAFE** and withholds the scrubbed text entirely. There is nothing to copy until
you resolve it. Better no output than a leak.

## What Sanitizer guarantees

| | Guarantee |
|---|---|
| **Offline** | Detection and sanitization make **no network calls** (PG1). |
| **No declared leak** | No declared term survives in the scrubbed output (PG2). |
| **No PII leak** | No enabled PII type (email, phone, card, SSN, IP, URL) survives (PG3). |
| **Reversible** | Anything removed restores exactly from the key, including through a markdown round trip (PG4). |
| **Timing preserved** | Segment/caption timing is never altered (PG5). |
| **Predictable** | The same input yields the same guaranteed removals, every time (PG6). |
| **Fail-closed** | If removal of the declared set can't be confirmed, Sanitizer never presents the output as clean and never lets you copy it (PG7). |
| **The key is the secret** | The key is stored in its own file, never embedded in the scrubbed text, and surfaced as the thing to protect (PG8). |

Each guarantee is backed by an automated test that fails the build if broken
(`sanitizer/sanitizer_core/tests/guarantees_test.py`).

## What Sanitizer does **not** do

- **Not a compliance certification (NG2).** Sanitizer reduces disclosure risk; it does not
  assert HIPAA/GDPR/CCPA compliance and does not guarantee completeness on items you
  didn't declare. Treat the suggestion tier as *guesses to review*, not a safety net.
- **No cloud anything (NG1).** No remote detection, inference, or telemetry, by design.
  That's a permanent property of the guaranteed path, not a limitation of this version.
- **No coreference / reliable codename inference (NG4).** It won't tie "she" back to a
  name, or reliably tell that an ordinary word is being used as a secret codename. The
  suggestion model proposes named entities and *obvious* codename-type mentions only.
- **Text & markdown only (NG6); per-transcript keys (NG5); no audio redaction (NG3).**

The honest failure mode to guard against is a **miss** (something sensitive you didn't
declare and no detector caught). That's why the review surface actively points at
candidates it did *not* remove. Declare the ones that matter and future transcripts
catch them automatically.

## Install (developer build)

```bash
python tools/package.py                 # -> dist/sanitizer.zip
cd dist && python -m http.server 8000
# In Buzz: Help → Plugins → Add by URL → http://localhost:8000/sanitizer.zip → restart Buzz
```

Prefer to just see the UI? `tools/preview_review.py` opens the review window with
sample data, no Buzz required (run it in a PyQt6 environment).

## Settings (Buzz → plugin config)

- **Declared terms**: one per line; prefix with a category for clearer placeholders
  (`person: Jane`, `project: Apollo`). You can also grow this list from inside the
  review window ("add to my list").
- **Remove email / phone / credit-card / SSN / IP / URL**: per-type PII toggles (all
  on by default).
- **Suggest undeclared names/orgs (local model)**: off by default; when on, downloads
  a small model on first use via Buzz and proposes suggestions for your review. Never
  applied automatically.

## Where your data lives

Per transcript, under Buzz's cache (`…/Buzz/plugins_data/sanitizer/<transcription id>/`):

```
segments.json   original + scrubbed text, timing preserved
decisions.json  one entry per removed / suggested / kept item
key.json        placeholder → original   ← THE SECRET (its own file)
meta.json       version, the clean/unsafe flag, counts, source file name
```

Sanitizer's preferences and your added declared terms live alongside, in
`preferences.json` and `declared_terms.json`.
