# Sanitizer — Design Revision v2 (after the persona walkthrough)

The three-persona walkthrough (Dana/paralegal, Okafor/clinician, Reyes/journalist) was strong signal. Net effect: the design gets **simpler**, not bigger. Below is the decision log — what I'm adopting, what I'm adapting, the one thing I'm declining (with the reason), and one finding I'm routing out of UX. Every call is weighed against the spec contract and the false-negative frame first.

## The headline change — close the approve/catch asymmetry

All three personas independently hit the same wall, and it's the worst one: **approving what the tool found is effortless; finding what it missed is "re-read the whole transcript myself" — the exact job they came to avoid** (UX-3, FR-16, FR-22, R1). This is simultaneously the worst friction and the deepest safety hole, and Reyes is right that the asymmetry *is* the product.

Two moves, both already latent in Direction A, now promoted to the center:

1. **Inline select-to-redact, unified with "add to my list."** Select any text in the context pane → one action: *"Redact this everywhere · also always treat as sensitive?"*. Catching a miss becomes one gesture — the same effort as ticking a found item. It also kills the separate "where do I add my terms?" hunt (M2/US2): the gesture that catches a miss *is* the gesture that teaches the list.
2. **A bounded "what we did NOT touch" reverse list** (the suspicion lens, FR-22, made concrete). Instead of dimming, it produces a short list: *"These look like names/orgs/emails we left in cleartext — confirm they're fine."* So miss-catching is reviewing a second finite list, not reading 10,000 words.

Guardrail kept from my open-risks: the reverse list is **bounded** (entity-shaped, un-redacted tokens only) and always reads **"candidates to confirm," never "all clear"** — a scan the user trusts becomes a new skim surface, which is the failure mode for this whole class of tool.

## Adopted — and they make it simpler ("simplicity is the soul of design")

- **Collapse four groups into two action zones.** Dana/Okafor/Reyes don't care, at approval time, whether a confirmed removal came from "my list" or "a phone pattern" — both are *found, removed, guaranteed*. So merge **Declared + PII → one "Removed" group** with provenance as a small per-row label (which preserves UX-1's "why flagged"). The result is a clean two-way split that actually sharpens the only line that carries safety weight: **Guaranteed (Removed)** vs **Suggested (your call)**. My original four-group list over-segmented on a distinction (declared-vs-PII) that isn't a *trust* distinction — both are deterministic and verified (PG2/PG3/PG6). This is a real improvement; credit the feedback.
- **One master "Approve everything detected"** instead of per-group bulk (UX-4). Clears the guaranteed zone in one action, leaving attention on the only two things that need a human: **Suggestions** and the **unconfirmed/not-touched** scan. ("Approve all from my list" survives as a filter on that action.)
- **Collapse "Keeping in cleartext" by default.** Stays visible and one-click re-approvable (UX-9 satisfied) but doesn't compete with the live decisions.
- **Empty state must *prove it ran*** (US8). Every persona distrusts a bare "nothing found" — a deposition or a patient visit with zero names reads as "it didn't run." Replace the reassurance sentence with **evidence of work**: *"Scanned 14 detectors across N segments · 0 matches."* Cheap, no safety cost, removes the unease entirely.
- **Copy-confirmation on Send out** (UX-6). A toast — *"Scrubbed text copied — safe to paste"* — so Dana and Reyes *know* they grabbed the safe artifact, not the key. The key's copy control stays distinct and fenced; distinctness is carried by **label + position + lock-glyph** (color only reinforces, never carries — UX-5).
- **Unsafe block gets a door** (US9/PG7). My §4.7 wireframe already named the survivor and offered a fix; the walkthrough confirms it's essential — under deadline a doorless wall sends people hunting for a workaround. Make the fix literal: *name the unconfirmed term, show where, one click to redact and clear the block.*
- **Restore surfaces unresolved tags** (FR-7). FR-7 silently skips unmatched placeholders; the personas need the inverse — *"3 placeholders filled · ⚠ 1 still unresolved in the text."* An unresolved tag the user doesn't notice is a small leak of structure.
- **Label the add/redact affordance "treat as sensitive," not "add a name."** Okafor's identifying diagnosis, Reyes's code name and city — the declared list already takes arbitrary strings (FR-1), but if the UI *says* "name," users think it's name-only. Fix the wording, not the engine.

## Adapted — first-run teaching

The feedback wants a hard acknowledgment gate so "the key is the secret" lands (US6). Right problem — Dana X's the modal, Okafor reads at 1.5x — but a bigger upfront wall gets dismissed harder. **Teach at the moment of consequence instead:** the first time the user reaches *Send out*, the key reveal carries the lesson *where it matters*, unskippable once. No upfront modal to click past; the lesson attaches to the action it governs. Simpler and stickier than a front gate.

## Declined — flipping the suggestion default (and why)

The feedback (Reyes) proposes suggestions default to **redacted, untick to keep**, on the logic that "a missed suggestion is a leak." I'm declining the default flip, on two grounds:

1. **It violates the binding contract.** FR-9: *"Nothing in the suggestion tier is applied without a click."* PG6/FR-15: model suggestions *"never enter the guaranteed set automatically."* Default-on = auto-applying an unvalidated zero-shot model's guesses — exactly what the spec forbids, to keep the guaranteed tier predictable (PG6) and avoid over-scrub mush (R2) and blind model-trust (R3).
2. **It doesn't fix the real hole.** An *unapproved* suggestion isn't a silent leak — it's an item the user **saw** in the list. The actual danger is items the model **never suggested at all** (true misses), and the default flip does nothing for those. The thing that protects Reyes's source is the reverse-list + select-to-redact (the headline change), not auto-trusting the model.

The compliant way to give the over-redact-preferring user what they want: an **opt-in "aggressive" posture** that pre-selects suggestions for removal — offered the same way FR-12's informed auto-apply is (only after ≥1 reviewed run, never the naked default). Reyes gets their preference as a deliberate, informed choice; Dana and Okafor keep the predictable guaranteed-vs-suggested model. *This is a deliberate divergence-decline, flagged per the brief's "where you diverge, justify it."*

## Routed out of UX — for PM/eng

Reyes asked the question UX can't answer: **where is the key stored, and what happens if my laptop is seized?** Today the key is `key.json` on disk, separate but (per DEV_NOTES) **not encrypted at rest**. PG8 guarantees *separate* and *clearly marked* — it says nothing about at-rest protection. For the journalist threat model, "the key is the secret" rings hollow if it's a plaintext file. **Recommend the PM scope key-at-rest protection** (OS keychain / passphrase) — out of this UX pass, but the walkthrough surfaced it and it shouldn't get lost.

## Revised core surface (Review) — two zones, not four

```
┌─ Sanitizer ───────────────────────────────────────────────── [_][▢][X] ┐
│ ✔  SAFE TO COPY · 9 removed · scanned 14 detectors · 2 to review     │
│ Transcript: [ Depo — Meridian v. Caldwell ▾ ]   [ Approve everything ]│
│ ( • Review )  ( Send out )  ( Restore )                              │
│ ┌── REMOVED — guaranteed ───────────┬── CONTEXT ─────────────────┐  │
│ │ ▣ {{PERSON-A}} Ahn   2  your list │ Ahn → {{PERSON-A}}  ×2      │  │
│ │ ▣ {{CASE-A}}  Meridian 3 your list│ …deposition of «Ahn», who… │  │
│ │ ▣ {{EMAIL-1}} j…@…   1  email     │ [ Scan for misses ]        │  │
│ │ ▣ {{PHONE-1}} (415)… 1  phone     │ select text → Redact + add │  │
│ ├── SUGGESTIONS — guesses, your call (2) ──────────────────────┐  │  │
│ │ ◇ Helix   org  2  "looks like an org"   [Approve] [Reject]    │  │  │
│ ├── ▸ Keeping in cleartext (1) ─ collapsed ────────────────────┘  │  │
│ └── ⚲ Not touched but entity-shaped: "Karen" (1) — confirm? ──────┘  │ ← reverse list
└──────────────────────────────────────────────────────────────────────┘
```

## Fastest happy path (target ~4 deliberate actions)

Open → Review (found pre-checked, scan-evidence shown, reverse-list surfaced) → glance + select-to-redact any miss → **Approve everything** → Send out → **Copy scrubbed text**. Reveal-the-key and Restore stay as separate, only-when-needed flows so they never clutter the main run.

## Keep even though each costs a step (the personas agreed)

The unsafe block (now with a door), the deliberate key reveal, the one glance at what was removed (made *cheap* via inline redact, never *optional*), and — critically — the manual miss-scan in the speed run: speed up everything around it, never let it be skipped. Reyes's instinct ("I re-read for source names every single time") is correct; the design's job is to make that scan *fast* (reverse list + select-to-redact), not removable.

## Phasing impact

The miss-catching work (FR-16 + FR-22) moves from "the hard Phase C item" to **the single highest-value change** — every persona's #1 pain and the deepest safety hole, and the rare fix that serves speed and safety at once. It still depends on the Phase B context pane to host select-to-redact, so the order holds (A → B → C), but B should be scoped tightly to unlock C as fast as possible. The four-into-two group merge folds into Phase A (it's pure restructure of the existing list).

---

*Next: I can generate the HTML test-fit reflecting these v2 decisions (two zones, reverse list, scan-evidence empty state, copy toast) so the reviewer can redo the Send-out and Review beats against real button placement — which is where the "which one is safe?" hesitation actually lives or dies.*
