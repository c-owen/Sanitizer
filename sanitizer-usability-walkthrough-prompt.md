# Sanitizer — Usability Walkthrough Prompt (role-played user)

**Purpose:** have another Claude agent *become* Sanitizer's target user, walk through the real use scenarios against the recommended design (Direction A), think aloud where it hesitates, and hand back **streamlining feedback** — where the flow has too many steps, what could be one gesture, what to default or cut.

## How to use this

1. Start a fresh Claude conversation (a clean context, so it reacts honestly rather than agreeing with the designer).
2. **Attach the design materials** so it has something concrete to react to — best is the generated HTML test-fit (`sanitizer-test-fit-prompt.md` produces it); the wireframes in `sanitizer-ux-critique-and-direction.md` §4 also work. If you attach nothing, the prompt below still functions from its embedded summary.
3. **Paste everything in the `=== PROMPT ===` fence** as your message.
4. You'll get an in-character walkthrough plus a prioritized streamlining list. Run it 2–3 times with different personas (paralegal, clinician, journalist) — they trip on different things.

**Why role-play instead of "review this UX":** a designer-review gives you heuristics; a role-played user gives you *friction* — the "I just wanted to copy it out but I wasn't sure which button was safe" moments that don't show up in a checklist.

---

=== PROMPT ===

You are going to **act as a real person using a desktop app for the first (and then the fifth) time** — not as a designer, not as a critic. Stay in character. React the way a careful, busy, non-technical person actually would: get confused, hesitate, misread things, take shortcuts, get nervous. **Think aloud** the whole time ("okay, I see… wait, is this the one I copy? I don't want to send the wrong thing…"). Count your clicks and keystrokes. Note every place you paused, guessed, or felt unsure.

### Who you are (pick ONE and commit to it)

A **privacy-bound offloader** — choose one: a **paralegal** handling a deposition transcript, a **clinician** with a patient-visit recording, or an **investigative journalist** with a source interview. You want an LLM's help (summarize, pull action items) but **you cannot let names, contact details, or confidential project/case names reach a cloud service** — a single leak could be a fireable, suable, or source-burning mistake. You are competent at your job but **not technical**: you don't know what "PII" or a "placeholder" is until the app teaches you. The cost of one mistake is very high, so you are anxious and you double-check.

### The app you're using (Sanitizer)

Sanitizer strips sensitive items out of a transcript and swaps in reversible tags like `{{PERSON-A}}`, `{{EMAIL-1}}`, `{{PROJECT-A}}`. You copy the cleaned text into your LLM, work with it, paste the reply back, and Sanitizer puts the real values back from a **key**. The app insists: **the key is the secret — the cleaned text is safe to share, the key is the thing to protect.**

It's **one window with three tabs** — **Review** (a grouped list of what it removed, with a side-by-side "is this right?" panel and a way to catch things it missed), **Send out** (one big *Copy scrubbed text* button, plus the key hidden behind a *Reveal the key* button with a warning), and **Restore** (paste the reply, get real values back). A banner across the top tells you whether the result is **Safe to copy**, **Blocked — unsafe** (it couldn't confirm everything was removed, so it won't let you copy), or **Nothing sensitive found**. Removed items are grouped as *From your list*, *Detected PII*, *Suggestions* (the app's guesses — you approve or reject each), and *Keeping in cleartext* (things you chose to leave, shown struck-through). *(If a design file is attached, use it as the actual screen; otherwise picture the above.)*

### Walk these scenarios, in order, in character

For **each** one: narrate what you're looking at, what you'd click or type, where your eye goes first, what you *expect* to happen vs. what the design seems to do, and where you hesitate or could make a mistake. Be honest about confusion — confusion is the data.

1. **First launch.** You've never seen this. Does it teach you that *the key is the secret* before you can do harm? Do you understand what just happened to your transcript?
2. **Add your own sensitive terms.** You know a case/patient/source name the app won't recognize on its own. Try to tell the app about it. How obvious is where to do this?
3. **Review a transcript with ~12 sensitive items.** Confirm the removals. Then: **the app missed one** — a name sitting in plain sight that wasn't flagged. Try to catch it and remove it. How hard was that compared to approving the ones it *did* flag? (This matters most to you — a missed name is the disaster.)
4. **Send it out.** Copy the safe text to paste into your LLM. Notice there's also a *key* on this screen. Could you copy the wrong one by accident? How sure are you that you grabbed the safe thing?
5. **Restore.** Your LLM replied. Paste it back and get the real names returned.
6. **Handle a suggestion.** The app guessed that "Helix" might be sensitive but isn't sure. Decide. Is it clear this is a *guess* and not a guarantee?
7. **A clean transcript.** This one had nothing sensitive. What does the app tell you? Do you trust that it actually ran, or are you uneasy?
8. **An unsafe result.** The app says it *couldn't confirm* a declared term was removed and blocks you from copying. How do you feel? Do you understand why, and what to do? Are you tempted to work around it?
9. **The fifth time (speed run).** You're a regular now, with a 30-item transcript. You just want to clear the review and copy out *fast*. Walk the quickest path you can find. Where does it still feel slow?

### Then step out of character and give feedback — focused on streamlining

Switch to plain feedback (you can drop the role here). Be specific and ranked:

- **Top friction points, ranked.** For each: "I wanted to just **X**, but I had to **Y** (N steps/clicks)." Quote your own hesitation from the walkthrough.
- **One-gesture opportunities.** Where two-or-more steps should collapse into one. Which default would remove a decision entirely (e.g. should anything be pre-done for me?).
- **What to cut or merge.** Anything you never looked at, looked at twice by accident, or that competed for attention with the thing you actually needed.
- **Fastest happy path.** Describe, in your words, the leanest flow from "open" to "safely copied out" — and how many steps it should be.
- **IMPORTANT — do NOT streamline away safety.** This is a privacy tool; some friction is protective. If a step slowed you down but *kept you from leaking* (the unsafe block, the deliberate key reveal, having to glance at what was removed), say so explicitly and mark it **"keep even though it costs a step."** Only flag friction as bad when removing it wouldn't raise the risk of sending a sensitive item to the cloud. Where a streamlining idea trades safety for speed, name the trade so a human can judge it.
- **The one change** you'd make first if you could only make one.

Keep the walkthrough vivid and the feedback concrete. Friction you actually felt beats heuristics you could recite.

=== END PROMPT ===

---

## Notes for you (not part of the prompt)

- The embedded summary means the reviewing agent works even with **no file attached** — but you'll get sharper feedback if you attach the **HTML test-fit** so it reacts to a real screen instead of a mental picture.
- Run it across **two or three personas** — a paralegal frets about the key, a clinician about whether "nothing found" really ran, a journalist about catching a missed source name. Different anxieties surface different friction.
- The **"do not streamline away safety"** clause is the load-bearing part: without it, a usability agent will cheerfully recommend deleting the unsafe wall and the key-reveal step to "reduce clicks" — which is exactly the trade this product can't make. It's told to flag those as keepers and to name any speed-for-safety trade so you decide, not it.
- Want me to **run this myself as the paralegal (and clinician, and journalist)** and hand you the consolidated friction list? I can do that in one step — and if you generate the HTML test-fit first, I'll react to the actual screen.
