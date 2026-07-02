# Sanitizer UI — start-here handoff manifest

Everything needed to implement the Sanitizer review window UI, in one place. Read in this order.

## 1. Instructions (read first)
- **`../sanitizer-implementation-brief-for-claude-code.md`** — the build plan: region→widget→data
  map, the four items that need new backend, the phased steps (A→D), guardrails, and the
  Step-A kickoff. **This is your task list.**

## 2. The structural spec (the target to build)
- **`sanitizer_layout_skeleton.py`** — the approved v2 design as a real PyQt6 widget tree,
  layout-only (no behaviour). Build the real UI by matching *this structure*, then binding
  the live data model into it. Run it to see it live:
  `python -c "import sys;sys.path.insert(0,'design');from sanitizer_layout_skeleton import SanitizerDesignSkeleton;from PyQt6.QtWidgets import QApplication as A;a=A([]);w=SanitizerDesignSkeleton();w.show();a.exec()"`
- **`renders/*.png`** — authentic native-Qt screenshots of every state (visual check).
- **`render_states.py`** — regenerate the screenshots (`QT_QPA_PLATFORM=offscreen python design/render_states.py`).

## 3. Visual + copy reference
- **`handoff/Sanitizer-Test-Fit.html`** — the interactive design test-fit (open in a browser;
  drive the mode tabs + demo-state toggle). Reference only — **do not port its HTML/CSS.**
- **`handoff/claude-design-handoff.md`** — exact copy, sample data, design tokens (QSS
  colours), the state model, and suggested signals/slots.

## 4. Rationale + contract (the "why")
- **`../sanitizer-design-revision-v2.md`** — the design decisions and the ones deliberately
  declined (e.g. suggestions stay held-by-default, FR-9).
- **`../sanitizer-ux-critique-and-direction.md`** §4–6 — wireframes, the colour-independent
  visual language, the interaction/keyboard model, and the spec-ID coverage map.
- **`../buzz-sanitizer-spec.md`** — the binding contract (PG-/FR-/UX-/US- IDs).

## 5. The code you change
- `../sanitizer/sanitizer_host/review_window.py` (the surface to evolve), `../sanitizer/sanitizer_host/menu.py`
  (drop demo/About), `../sanitizer/sanitizer_core/` (the pure data model — **read, do not add Qt to it**).

## Non-negotiables (from the spec — do not "simplify" away)
Unsafe **withholds** the scrubbed text (never just disables copy) — PG7/US9 · the key reads as
the secret, copying it is deliberate — PG8/UX-6 · rejected items stay visible — UX-9 · meaning
never depends on colour alone — UX-5 · suggestions are never auto-applied — FR-9 · `sanitizer_core`
stays free of `buzz`/`PyQt6` (AST-enforced) · never modify Buzz.
