# Cloak — design skeleton (the structural spec for the real UI)

This folder is the **buildable design handoff** for the Cloak review window. It is the
answer to "how do we specify the GUI for the programmer" without losing fidelity in a
screenshot: the spec is expressed as a **real PyQt6 widget tree**, so the implementing
agent inherits the structure instead of guessing it from pixels.

## Files

- **`cloak_layout_skeleton.py`** — layout-only window. Builds the approved v2 design as
  native Qt widgets: one window, three modes (Review / Send out / Restore), the two-zone
  decision list (REMOVED / SUGGESTIONS + collapsed "keeping in cleartext"), the reverse
  "not touched — confirm these" strip, side-by-side context, the fenced key, and the
  Safe / Unsafe / Empty states. **It contains NO behaviour** — `set_mode` / `set_state`
  only toggle widget visibility. Region → spec-ID (UX-/PG-/FR-) mappings are inline.
- **`render_states.py`** — renders each (mode, state) to `renders/*.png`.
- **`renders/`** — reference screenshots (authentic native-Qt output).

## How to use it

**See it live** (on your machine, with the PyQt6 venv):

```
python design/cloak_layout_skeleton.py   # add an app runner, or:
python -c "from PyQt6.QtWidgets import QApplication; import sys; \
  sys.path.insert(0,'design'); from cloak_layout_skeleton import CloakDesignSkeleton; \
  a=QApplication([]); w=CloakDesignSkeleton(); w.show(); a.exec()"
```

Flip modes with the tabs and states with the demo-state toggle (top-right — a
prototype-only control; the real plugin derives the state from the sanitizer result).

**Regenerate the screenshots** (headless, no display):

```
QT_QPA_PLATFORM=offscreen python design/render_states.py
```

## For the implementing agent

Treat this skeleton as the **structural contract**, `renders/` as the **visual check**,
and the design docs (`../cloak-design-revision-v2.md`, `../cloak-ux-critique-and-direction.md`,
and the Claude-Design handoff README) as the **rationale + behaviour**. Your job is to
bind the real data model (`ReviewItem` / `TrustTier` / `DecisionState` / `apply_review`
from `cloak/cloak_core`) into this layout — not to reinvent the layout. Follow the phased
plan in `../cloak-implementation-brief-for-claude-code.md`, starting with Step A.

Do not port pixel measurements; Qt lays out natively. The skeleton is the target shape;
your app's theme provides the final styling.
