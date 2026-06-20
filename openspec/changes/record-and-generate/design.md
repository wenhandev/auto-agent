## Context

`vision-action-mode` gives a perception layer that already indexes interactive elements; `run-artifacts-observability` stores screenshots; `browser-sessions-profiles` provides a live session; `workflow-input-parameters` provides the generalisation target. Recording is the composition: instrument a live session, capture intent-bearing actions, then synthesise a `Workflow`. Skyvern's "show once, run forever" is exactly this.

## Goals / Non-Goals

**Goals:**
- Capture a human's browser actions as an intent-bearing trace.
- Synthesise a runnable, *editable* draft workflow (not a brittle macro).
- Generalise typed values to parameters; convert secrets to a `login` node.

**Non-Goals:**
- Pixel-perfect deterministic replay of every micro-interaction.
- Multi-tab/window recording.
- Real-time synthesis mid-recording.

## Decisions

### Decision 1: Capture intent (element + description), not raw coordinates
Each action is tagged with the perception element index + accessible description + screenshot, not pixel coordinates.
- **Why**: intent generalises across viewport/layout changes; coordinates don't. Aligns with the vision-first identity.

### Decision 2: Synthesise to deterministic-where-unambiguous, vision-where-goal-shaped
The synthesizer emits `goto_url`/`click`/`fill` when the target is stable and unambiguous, and `vision_act`/`vision_navigate` when the action is better expressed as a goal (search-then-pick, list interactions).
- **Why**: cheap deterministic nodes where possible, robust vision where needed — the best of both. A pure-deterministic macro would be brittle; pure-vision would be slow/expensive.

### Decision 3: Sensitive inputs never recorded as literals
Typed values into password/2FA fields are dropped; the synthesizer inserts a `login` node referencing a credential (prompting the user to pick/create one).
- **Why**: never persist secrets from a recording; reuse the `login-block` primitive.

### Decision 4: Parameter inference from typed values
Non-sensitive typed text (search terms, quantities) becomes a `{{params.<name>}}` candidate with the recorded value as the default.
- **Why**: the recording generalises into a reusable template instead of a one-off.

### Decision 5: Synthesis on stop, output is a reviewable draft
Synthesis runs once on stop; the result opens in the editor with per-node screenshots and a seeded chat — nothing auto-runs.
- **Why**: a human-in-the-loop review step catches synthesis mistakes before they execute; matches the platform's chat-authoring model.

## Risks / Trade-offs

- [Noisy trace: stray clicks/scrolls] → the synthesizer prompt is instructed to drop incidental navigation/scroll noise; the user trims in the editor.
- [Ambiguous targets] → fall to a `vision_act` with a description rather than a guessed selector.
- [Secret leakage from recording] → sensitive fields detected (type=password, autocomplete=one-time-code) and never stored; values masked in the trace.
- [Over/under-parameterisation] → suggested params are editable; nothing is forced.

## Migration Plan

- `create_all` makes `recording`; recordings stored via the artifact store.
- New routes start/stop/synthesise; new recording UI page.
- No change to existing prompt/chat authoring.

## Open Questions

- Capture network calls to suggest `http_request` nodes (skip the UI for API-backed steps)? (Lean: capture but defer suggestion to a follow-up; UI-action synthesis first.)
- Allow re-synthesis with a different bias (more deterministic vs. more vision)? (Lean: a toggle on the "生成工作流" action.)
