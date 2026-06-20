## depends_on

- `vision-action-mode` — the perception layer + indexed element map are how a recorded click is mapped to a durable node target.
- `run-artifacts-observability` — recorded steps reuse the screenshot/artifact plumbing.
- `auto-agent-platform` — workflow persistence + the chat editor that the generated draft lands in.
- `browser-sessions-profiles` (soft) — recording happens in a live session.

No hard dependency on other in-flight changes.

## Why

The fastest way to author an automation is to **do it once** and have the tool watch. Skyvern's pitch: "Record yourself performing a task in the browser. Skyvern watches, learns, and generates a reusable automation — show once, run forever." `auto-agent` currently authors by NL prompt or chat. This change adds the third, often-fastest path: **record → generate workflow**, turning a human's demonstrated actions into a draft `Workflow` the user can refine and run.

## What Changes

- **Recording session**: a `POST /api/recordings` starts a live recording in a browser session (reusing `browser-sessions-profiles`). The page is instrumented (CDP `Input` events + DOM listeners injected via an init script) to capture the user's actions: navigations, clicks, typing (values masked/optional), selects, scrolls, and waits — each tagged with the perception element index + an accessible description + a screenshot.
- **Action trace → workflow synthesis**: on stop, a `WorkflowSynthesizer` (an ADK `LlmAgent`) consumes the recorded action trace + screenshots and produces a draft `Workflow`: deterministic `goto_url`/`click`/`fill` nodes where the target was unambiguous, and `vision_act`/`vision_navigate` nodes where the intent is better expressed as a goal. Typed values become candidate `{{params.<name>}}` (from `workflow-input-parameters`) so the recording generalises instead of hardcoding.
- **Sensitive input handling**: typed values into password/2FA fields are NOT stored; they become a `login` node referencing a credential (prompted at synthesis) rather than literal text.
- **Review & land**: the generated draft opens in the workflow editor with the recording's screenshots attached per node and a chat session seeded with "我录制了这个流程，请帮我细化". The user edits, parameterises, and saves a version — nothing auto-runs.
- **UI**: a "录制" entry that opens the live browser (livestream), a record/stop control, a step list building up live, and a "生成工作流" button that runs synthesis and navigates to the new draft.

## Capabilities

### New Capabilities

- `action-recording`: the recording session, page instrumentation, the captured action trace (with element indices + screenshots + masked sensitive inputs), and the recording UI.
- `workflow-synthesis`: the `WorkflowSynthesizer` agent that turns an action trace into a draft `Workflow` (deterministic where unambiguous, vision where goal-shaped), parameter inference, and sensitive-input→`login`-node conversion.

### Modified Capabilities

- `chat-authoring` (from `auto-agent-platform`): a generated draft opens with a seeded chat session for refinement.
- `nl-workflow-planner` (from `auto-agent-mvp`): synthesis is a sibling authoring path; the planner is unchanged but documented as one of three entry points (prompt / chat / record).
- `workflow-input-parameters` (soft): synthesis emits `{{params...}}` candidates.

## Impact

- **Backend**: new `app/services/recording.py` (instrumentation + trace capture), `app/agents/synthesizer.py` (the synthesis agent), a `Recording` model (trace + linked artifacts), and routes to start/stop/synthesise. Reuses session + artifact plumbing. Tests: trace capture fidelity on a fixture page, sensitive-field masking, synthesis produces a valid `Workflow`, parameter inference.
- **Frontend**: a recording page with the livestream, live step list, record/stop, and "生成工作流". Moderate-to-large.
- **Runtime**: recording adds event listeners (cheap); synthesis is one (larger) LLM call over the trace + a sample of screenshots.
- **Migration**: `create_all` makes `recording`. Recordings are artifacts under the existing store. No behaviour change to existing authoring.
- **Out of scope**: real-time synthesis during recording (synth happens on stop); recording across multiple tabs/windows; editing the raw trace by hand; non-browser steps (HTTP/email) in a recording — those are added in the editor afterward; perfect deterministic replay of every micro-interaction (we synthesise intent, not a macro).
