# Transcript Sanitizer — Product Brief

**Plugin (working title):** Sanitizer — a reversible, offline sensitive-information sanitizer for Buzz
**Status:** Draft v0.3 — product planning, for handoff to engineering (blocking questions resolved)
**Document type:** Product brief (problem, goals, scope, guarantees, principles)
**Audience:** maintainers / PM. Hands off to the implementing agent, which will pull the current Buzz repo and produce the technical design.
**Owner:** _PM (you)_

---

## 0. How to use this document

This is a **product brief**, not a technical design. It defines the problem, the user value, the scope boundaries, the guarantees the product must make, and the principles the build must honor. It deliberately does **not** specify architecture, components, interfaces, or data structures — the implementing agent will pull the latest Buzz source and produce that technical plan against the constraints and guarantees here.

The three previously-blocking open questions are now **resolved**; their decisions are recorded in §9. Remaining open questions are non-blocking and can resolve during implementation. We are unblocked for technical planning.

---

## 1. Problem

Buzz transcripts routinely contain sensitive content — personal names, phone numbers and other PII, and internal project/program codenames. Users increasingly want to run transcripts through cloud LLMs (summarize, extract actions, rewrite), but doing so leaks that content off-device, irreversibly, the moment it's pasted. There's no way today to strip the sensitive material locally, work with the cleaned text elsewhere, and reverse the substitution afterward.

The cost of inaction is concrete: privacy-conscious and compliance-bound users (legal, medical, corporate, journalistic) either avoid cloud LLMs entirely — forgoing the productivity Buzz could unlock — or paste sensitive data and accept an irreversible disclosure they often don't realize they've made.

## 2. Goals (outcomes)

- **G1 — Safe offload.** A user can transform a transcript so a defined set of sensitive items is replaced before the text leaves the machine, then restore the real values in any returned text — with all detection running on-device.
- **G2 — No silent leaks.** Items the user declared sensitive are guaranteed absent from sanitized output, and the user is never shown "done" while a declared item survived.
- **G3 — Usable output, not mush.** Sanitized text stays coherent enough for an LLM to reason over, so the offload is worth doing.
- **G4 — Low-friction trust.** A user can verify and correct the result in seconds, with the interface steering attention to the dangerous case — a *missed* item — not the safe one.
- **G5 — Built to grow.** Stronger detection (a local LLM), audio redaction, more formats, and richer behaviors can be added later without reworking what already exists.

## 3. Non-Goals (this version)

- **NG1 — No cloud anything.** No remote detection, inference, or telemetry. Permanent for the detection/sanitization path, not just v1.
- **NG2 — Not a compliance certification.** Reduces disclosure risk; does not assert HIPAA/GDPR/CCPA compliance or guarantee completeness on undeclared items. Over-promising is itself a risk.
- **NG3 — No audio redaction in v1.** Text only; bleeping the source audio is roadmap.
- **NG4 — No coreference or reliable contextual-codename detection in v1.** v1 includes a suggestion model (FR-15) that proposes named entities and *obvious* codename-type mentions, but pronoun-level coreference ("she → Jane") and reliably inferring that a bare ordinary word is functioning as a secret codename need the local LLM tier — that stays roadmap (FR-18).
- **NG5 — No cross-file / project-wide keys in v1.** Each transcript gets its own key.
- **NG6 — Plain text and markdown only.** Import and export are limited to clipboard text and markdown, both directions. `.docx` and all other formats are out for v1 (`.docx` specifically carries hidden channels — comments, tracked changes, author metadata — that a sanitizer would have to scrub too, so it's deferred behind that requirement).

## 4. Target users & user stories

**Primary persona — the privacy-bound offloader.** A Buzz user (paralegal, clinician, analyst, journalist, founder) who wants an LLM's help on a transcript but can't let names, PII, or internal codenames reach a third party.

Ordered by priority. _As a [user], I want [capability] so that [benefit]._

- **US1.** As an offloader, I want sensitive items replaced with readable placeholders before I copy the transcript, so I can paste it into a cloud LLM without disclosing them.
- **US2.** As an offloader, I want to declare my own sensitive terms (projects, clients, people), so the items *I* know are sensitive are always removed, reliably.
- **US3.** As an offloader, I want to paste the LLM's reply back (as text or markdown) and have the real values restored, so the round trip is usable end to end.
- **US4.** As an offloader, I want the tool to *suggest* items it suspects but I didn't declare, held for my one-click review, so I catch what I forgot without trusting a model blindly.
- **US5.** As an offloader, I want to see what was removed and easily mark anything it *missed*, so I can trust the result and improve it for next time.
- **US6.** As an offloader, I want a clearly separate, plainly-marked key, so I understand the key — not the scrubbed text — is the secret I must protect.
- **US7.** As a returning offloader, I want an option to apply suggestions automatically without review, offered only after I've seen the tool work once, so I can trade friction for speed as an informed choice.
- **US8 (empty state).** As an offloader whose transcript holds nothing sensitive, I want a clear "nothing detected" result, so I'm not left wondering whether it ran.
- **US9 (error state).** As an offloader, if the tool can't guarantee my declared items were removed, I want it to fail loudly and refuse to present "clean" output, so I never ship a false negative.

## 5. Design principles & constraints (the build must honor these)

Your two mandates, stated as principles for engineering to realize — not as designs.

- **Modular and swappable (object-oriented).** Detection methods, replacement behaviors, format handlers, and host integration must each be independently replaceable, so stronger detection and new formats can be added later without reworking what exists. Long-term flexibility is a first-class requirement, not a nice-to-have.
- **Verifiable by contract.** Every component must state, in plain terms, what it assumes and what it guarantees, and those guarantees must be backed by automated tests that fail the build if broken.
- **Offline by default, and permanently for detection.** No transcript content leaves the device during detection or sanitization.
- **Fail-closed.** If the tool can't confirm the declared items were removed, it must refuse to present the text as safe.

## 6. Product guarantees (the safety contract, in plain language)

These are the promises the product makes. Each must be backed by an automated test (see Definition of Done).

- **PG1 — Offline.** Detection and sanitization make no network calls.
- **PG2 — No declared leak.** No declared term (or its obvious variants) survives in sanitized output.
- **PG3 — No structured-PII leak.** No enabled PII type (phone, email, etc.) survives in sanitized output.
- **PG4 — Reversible.** Anything removed can be restored exactly from the key.
- **PG5 — Timing preserved.** Subtitle/segment timing is unchanged, so captions stay in sync.
- **PG6 — Predictable removals.** The same input yields the same guaranteed removals every time — auditable and reproducible. (Model-driven *suggestions* are a separate, reviewable tier and never enter the guaranteed set automatically.)
- **PG7 — Fail-closed.** On any failure to confirm the declared set was removed, the tool never presents output as clean and never auto-copies it.
- **PG8 — The key is the secret.** The key is stored separately from the scrubbed text and clearly marked as the thing to protect; it's never embedded in the scrubbed output.

## 7. Requirements

IDs are stable references for tickets. Acceptance criteria are behavioral.

### Must-have — P0 (v1)

- **FR-1 — Declared list (highest trust).** Maintain a list of sensitive terms; all are detected (case/possessive/whitespace variants included) and removed automatically.
  - Every occurrence of a declared term is replaced and recorded in the key; matching never corrupts substrings ("Jane" must not touch "Janet").
- **FR-2 — Structured-PII detection.** Built-in detection for at least phone, email, credit card, SSN, IP, and URL, each individually toggleable, removed automatically.
  - Enabled types are removed; disabled types are left untouched.
- **FR-3 — Consistent placeholders, one decision per item.** Repeated mentions of the same thing become one decision with one consistent, readable placeholder; different things never share a placeholder.
- **FR-4 — Timing preserved.** Removal never alters segment timing (PG5).
- **FR-5 — Key produced and separate.** A local key is generated, stored apart from the scrubbed output, and surfaced as the protected secret (PG8).
- **FR-6 — Verification gate.** After removal, the tool re-checks the output and, if any declared term or enabled PII type survived, refuses to present it as clean (PG2/PG3/PG7; US9).
- **FR-7 — Restore.** Given returned text (clipboard text or markdown) plus the key, real values are substituted back exactly; placeholders absent from the returned text are simply skipped, with no error (PG4).
- **FR-8 — Review surface.** A review experience that opens to a finite, countable list of decisions (full UX in §8); high-trust removals are pre-approved, so only suggestions need action.
- **FR-9 — Held-for-one-click review by default.** Nothing in the suggestion tier is applied without a click.
- **FR-10 — Always-visible summary.** Even when suggestions are applied automatically (FR-12), a persistent, non-blocking "removed N · Review · Undo" summary is shown; the flow is never fully silent.
- **FR-11 — Nothing-detected state.** A clear result when no items are found (US8).
- **FR-12 — Informed auto-apply.** An "apply suggestions automatically / don't ask again" option, offered **only after** the user has completed at least one reviewed run — never up front (US7).
- **FR-13 — Runs as a plugin without modifying Buzz; model fetched via Buzz's own tools.** Operates within Buzz's plugin model. The suggestion model (FR-15) is **downloaded on first use through Buzz's built-in model-download mechanism** (the same one Buzz uses for its transcription models, which caches to Buzz's shared model location) — **nothing is bundled with the plugin**, and an already-cached model is reused. No modification of the Buzz app.
- **FR-14 — Extensibility honored.** Adding a new detection method, replacement behavior, or import/export format later must not require reworking existing detection or the core flow (G5). Demonstrated by adding one without disturbing the rest.
- **FR-15 — Suggestion model (lightweight, local, in v1).** A small on-device zero-shot model proposes undeclared names/orgs/locations and obvious codename-type mentions, always held for review (FR-9), never auto-trusted. Runs on CPU, cross-platform; fetched via Buzz's downloader (FR-13).
  - Suggestions appear in the review list as a distinct, lower-trust tier with their reason shown; approving or rejecting one is one action (§8).
- **FR-22 — Suspicion lens (v1, opt-in, default off).** A toggle that dims clearly-safe text and raises contrast on likely-missed items, to help a user scan for misses. Off by default; never required to complete a review. (Lowest-priority v1 item; may slip to fast-follow without affecting the core.)
- **FR-23 — Placeholder robustness.** Placeholders must be chosen so that markdown rendering, copy/paste, and light editing cannot alter or split them — so restore stays reliable across the markdown round trip. (This is the real reliability risk of the markdown path, independent of format count.)
- **FR-24 — Formats: text and markdown, both directions.** Sanitized output can be taken as clipboard text or markdown; returned text can be restored from clipboard text or markdown. No file import/export and no other formats in v1 (NG6).

### Should-have — P1 (fast follow)

- **FR-16 — One-gesture "scrub this".** Select any un-removed text → remove all its occurrences → offer to add it to the declared list. (Steers attention to misses; US5.)
- **FR-17 — Re-identification flag on restore (first pass).** Flag obvious cases where returned text *describes* a hidden item without using its placeholder ("the CFO who joined in 2019").

### Future considerations — P2 (don't preclude)

- **FR-18 — Optional local LLM tier.** For coreference and reliable contextual-codename inference; strictly additive on top of the guaranteed-removal floor, never the only safeguard.
- **FR-19 — Per-category replacement behaviors.** Realistic fakes for structured data, date-shifting that preserves intervals, redact/keep — chosen per item type.
- **FR-20 — Audio redaction.** Bleep/silence the source audio at the relevant timestamps.
- **FR-21 — Cross-file / project keys.** Consistent placeholders across a series of related transcripts.
- **FR-25 — More formats.** `.docx` (gated on scrubbing hidden channels) and other formats; file-based import/export; `.srt`/`.vtt` export of scrubbed captions (an outbound-only use case, no restore leg).

## 8. UX requirements

The review experience is the trust surface; these encode the design direction we converged on.

- **UX-1 — A decision list is the home surface.** Review opens to a short, countable list of *item-level* decisions — not a hunt through a long transcript. Each entry shows the placeholder, the original, the type, *why it was flagged* ("matched your list" / "looks like a name" / "phone pattern"), how many times it occurs, and its state.
- **UX-2 — Side-by-side is the detail view.** Selecting an entry shows the original in context beside the result, for the "is removing *this* one correct?" judgment. The detail view serves the list; it isn't the entry point.
- **UX-3 — Emphasis points at misses.** Catching a missed item must be at least as easy as approving a flagged one (FR-16), and the optional suspicion lens (FR-22) exists to support that scan. The interface must not, by design, train the eye to skim the un-removed (and therefore un-checked) text.
- **UX-4 — Decide once per item; bulk and keyboard.** Approve/reject once per item, applied everywhere it occurs; bulk actions ("approve all phone numbers", "approve all from my list", "reject all dates"); fast keyboard flow to clear the list. (Target speed to be set — §9.)
- **UX-5 — State and reason shown in words and grouping, not color alone.** State and type are labeled and grouped, and the interface is fully usable without color (accessibility requirement, not a nicety).
- **UX-6 — Outbound action design.** "Copy scrubbed text" is the single prominent action; the key is visually branded as the secret. In any two-pane layout, guard against the most likely error: copying the wrong pane.
- **UX-7 — Mirrored restore.** Restore reuses the same surface in reverse: paste reply → placeholders highlighted, real values filled back, with a distinct flag for possible re-identification.
- **UX-8 — Auto-apply is non-blocking, not invisible.** The safety distinction is blocking vs. non-blocking, not review vs. no-review: auto-apply still shows the persistent summary and Undo (FR-10).
- **UX-9 — Rejected items stay visible.** Items the user chooses to leave in cleartext are not hidden; they remain shown (struck-through, in a clearly separate "keeping in cleartext" group) and are re-approvable in one action. Rationale: in a privacy tool the *absence* of an item is dangerous information to lose — a wrongly-rejected sensitive item must stay recoverable and auditable, never silently gone.

**Sample acceptance (UX-1/UX-4):** Given a 60-minute transcript with ~12 sensitive items, when the user opens review, they see ~12 entries (not a 10,000-word scroll), with declared/PII entries pre-approved and only suggestions awaiting action; "approve all from my list" resolves all declared entries in one action.

## 9. Open questions & resolved decisions

**Resolved (previously blocking):**
- **Suggestion model in v1?** → **Yes.** The lightweight local model ships in v1 as the suggestion tier (FR-15), fetched via Buzz's built-in downloader, not bundled (FR-13).
- **Suspicion lens?** → **A toggle**, off by default (FR-22).
- **Rejected-item visibility?** → Rejected items **stay visible** (struck-through, separate group, re-approvable) — the safety-aligned call (UX-9).

**Still open (non-blocking):**
- **OQ4 (data) — Quality bar.** Target detection recall on a curated test set, and acceptable processing time per transcript. Needed to make Success Signals concrete.
- **OQ5 (design) — "Quickly" defined.** Target effort/time to clear the review list for a typical transcript (UX-4).
- **OQ6 (product) — Placeholder style.** Readable symbolic placeholders only in v1 (assumed), or expose realistic fakes for structured types earlier (pulls FR-19 forward)? Note this interacts with FR-23: whichever style is chosen must satisfy placeholder robustness.

## 10. Success signals

This is an **offline, no-telemetry, privacy-first** plugin (NG1), so we deliberately forgo instrumented funnels and define success through testable correctness and community signal.

- **Leading (in test/CI):** the guarantee tests (PG1–PG8) passing; detection recall on a curated sensitive-transcript set above the agreed bar (§9); review effort below the agreed bound on that set.
- **Lagging (observed, not instrumented):** adoption/install signal where the host surfaces it; issue and PR sentiment; and the single most important real-world signal — the **absence** of reported "it leaked X" incidents.

## 11. Definition of Done

A change is Done when all hold:

- [ ] All P0 requirements (FR-1…FR-15, FR-22, FR-23, FR-24) met, with their acceptance criteria passing.
- [ ] Every product guarantee (PG1–PG8) is backed by an automated test that fails the build if violated.
- [ ] Fail-closed, empty-state, and restore-with-unmatched-placeholders behaviors all verified (US8/US9, FR-7/FR-11).
- [ ] The markdown ↔ text round trip is verified, and placeholders are shown to survive markdown rendering, copy/paste, and light editing without alteration (FR-23/FR-24).
- [ ] The suggestion model is present, runs locally, is review-gated, and is fetched via Buzz's downloader with nothing bundled (FR-13/FR-15).
- [ ] Extensibility demonstrated: a new detection method or format can be added without reworking existing detection or the core flow (G5/FR-14).
- [ ] The sanitization logic is verifiable independently of the Buzz app.
- [ ] Runs within Buzz without modifying the app.
- [ ] Review UX acceptance criteria met, including rejected-item visibility (§8, UX-9).
- [ ] The agreed quality bar (recall / processing-time / review-effort from §9) is met.
- [ ] A short README states what the tool guarantees, what it explicitly does **not** (NG2), and the "the key is the secret" model.

## 12. Phasing / roadmap

- **v1 (P0):** the guaranteed-removal floor — declared list + structured-PII patterns — plus the lightweight local **suggestion model** (review-gated), consistent placeholders, a separate key, restore, fail-closed verification, the decision-list review surface with rejected-item visibility, the always-visible summary, informed auto-apply, the opt-in suspicion lens, and **text + markdown** in/out with robust placeholders. Lightweight, offline, predictable.
- **v1.x (P1):** one-gesture "scrub this," first-pass re-identification flag on restore.
- **v2 (P2):** optional local LLM tier (coreference + contextual codenames), per-category replacement behaviors, audio redaction, cross-file keys, and more formats (`.docx` gated on hidden-channel scrubbing, file import/export, `.srt`/`.vtt` caption export).

## 13. Risks & mitigations

- **R1 — False negative (the catastrophic risk).** A real sensitive item is missed and shipped. *Mitigation:* tune for recall, combine detectors rather than intersect them, fail-closed verification on the declared set, and an interface that points at misses (UX-3, FR-16, FR-22). Honest scoping that completeness on undeclared items isn't guaranteed (NG2).
- **R2 — Over-scrub → unusable mush.** Too-aggressive removal yields "PERSON-A told PERSON-B about PROJECT-C," defeating the offload. *Mitigation:* per-type control, the review step, readable role-preserving placeholders; recall-vs-usability treated as the real target, not "remove everything."
- **R3 — Suggestion unpredictability unsettles users.** *Mitigation:* the guaranteed-removal set is predictable by design (PG6); model suggestions are clearly a separate, reviewable tier.
- **R4 — Domain accuracy varies.** General models underperform on clinical/legal text. *Mitigation:* the declared list and per-user vocabulary are the adaptation mechanism and are never optional; said plainly in the README.
- **R5 — Re-identification on return.** The LLM paraphrases a placeholder into an identifying description. *Mitigation:* a re-identification flag on restore from v1's fast-follow onward (FR-17).
- **R6 — Host coupling / update breakage.** *Mitigation:* keep Buzz-specific integration thin and at the edges; don't modify the app; conform to its plugin model and reuse its model-download mechanism.
- **R7 — Markdown mangles placeholders.** Editing or rendering breaks a token so restore misses it. *Mitigation:* the placeholder-robustness requirement (FR-23), verified in the DoD.

## 14. Host constraints that shape the product

A few facts about how Buzz runs plugins drive product decisions (engineering will handle the mechanics):

- Sanitization runs automatically in the background right after a transcription finishes, so the review-and-correct experience is a **separate screen the user opens**, not a blocking dialog mid-transcription.
- **Restore is a distinct, manual action** (paste reply → restore), not automatic — the round trip is two deliberate steps. Worth confirming this is the intended model.
- The plugin installs its own components and **downloads its model on first use through Buzz's existing model-download mechanism, without altering the Buzz app**; models are fetched and shared via Buzz's cache, not shipped with the plugin.
- There's no built-in "sanitize an already-finished transcript on demand" path today — sanitization happens at transcription time. If we want on-demand sanitization of older transcripts too, that's an explicit product ask to scope, not a given.

## 15. Candidate approaches (engineering chooses specifics)

The tiers we settled on: structured PII via rule-based pattern matching (fast, exact, auditable); suggested freeform items (names, obvious codename-type mentions) via a **lightweight local zero-shot model — committed for v1**, fetched through Buzz's downloader; and the hardest cases (coreference, reliable contextual codenames) via an **optional local LLM, later**. The specific model and libraries are engineering's call when planning against the repo; the constraints that bind them are: on-device, CPU-capable, cross-platform, and review-gated (suggestions never auto-applied).

## 16. Glossary

- **Declared list** — the user's own sensitive terms; the highest-trust tier; always removed and verifiable.
- **Trust tiers** — declared (authority) > pattern-detected PII > model-suggested. Governs what's removed automatically vs. held for review.
- **Placeholder** — the readable stand-in shown in place of a removed item (e.g., a person becomes a consistent "PERSON-A"-style label); must survive markdown and light editing (FR-23).
- **Key** — the private map from placeholders back to real values; stored separately; the secret the user protects.
- **Verification gate** — the independent re-check that fails closed if a declared or PII item survived.
- **Re-identification** — recovering a hidden item from an un-replaced *description* in returned text.
- **Fail-closed** — when the tool can't confirm the declared set was removed, it refuses to present the text as safe.
