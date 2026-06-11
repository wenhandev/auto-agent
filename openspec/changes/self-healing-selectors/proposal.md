## depends_on

- `auto-agent-mvp` — workflow schema, executor, `click` / `fill` actions, ADK `LlmAgent` shape, hybrid executor.
- `auto-agent-platform` — `runtime-llm-config`'s `get_adk_model_cached()` (the heal agent must use the active LLM, not a hard-coded SDK), `RunEvent` table for the new `node_self_healed` event, `LlmConfig` table for the global toggle.

No dependency on the other changes in this batch. This change ships orthogonally; if `node-error-handling` is also live, the heal step runs INSIDE the retry loop (one heal per retry attempt). If `expanded-node-library` is also live, this change does NOT auto-heal anything beyond `click` / `fill` — adding `http_request` self-healing or similar would be a follow-up.

## Why

Selectors break. Every browser-automation tool that has shipped at scale lives with this problem: a `#product-title` element becomes `.product-name h1`, a `[data-test=submit]` becomes `[data-testid=submit]`, an entire DOM region is rewritten by an A/B test. Today our executor fails the run, the operator opens the chat panel, asks the editor to suggest a new selector, runs the workflow again, and hopes nothing else changed. That loop is too slow for a serious automation user.

We add an auto-heal step that runs at the action level. When a `click` or `fill` node's deterministic selector miss is about to fail the node, the executor takes a screenshot plus an accessibility snapshot, asks a tiny LLM agent (`SelectorFinderAgent`) for a candidate replacement selector and a confidence score, then retries the original action with the candidate. If it succeeds, the executor emits a `node_self_healed` event identifying the old + new selectors and a follow-up "patch suggestion" event the operator can apply to the workflow JSON via the existing chat editor.

The heal step costs one vision LLM call. It is gated by a global toggle (`LlmConfig.self_healing_enabled`) so cost-sensitive operators can opt out, and a per-node override (`node.params.auto_heal: false`) so individual nodes can opt out without disabling the feature globally. Healed selectors are NOT persisted to the workflow automatically — the operator decides via the patch-suggestion UI. Per-workflow learning of healed selectors is explicitly future work.

## What Changes

- **Executor / actions**: `app/tools/actions.py::click(...)` and `fill(...)` are wrapped so that on Playwright `TimeoutError` (selector miss) the wrapper calls `services.self_healing.attempt_heal(page, node, original_error)`. The wrapper is a function decorator applied during executor dispatch; the action functions themselves remain unchanged.
- **Self-heal service**: new `app/services/self_healing.py` exposing `attempt_heal(page, node, original_error) -> HealResult` where `HealResult = {healed: bool, new_selector: str|None, confidence: float, cost_hint: dict}`. The service captures a viewport screenshot via `page.screenshot()` and the accessibility tree via `page.accessibility.snapshot()`, calls a small ADK `LlmAgent` (`SelectorFinderAgent`) with a tightly-scoped tool surface (`propose_selector(description) -> {selector, confidence}`), and returns the agent's best candidate.
- **Selector finder agent**: new `app/agents/selector_finder.py` — an ADK `LlmAgent` initialised with `get_adk_model_cached()` (so it shares the platform's active LLM). System prompt is short: "Given a screenshot + accessibility snapshot + the original selector that failed + the action's intent (click / fill), propose a CSS or text-based selector for the same element. Return only the selector and a confidence score in `[0, 1]`."
- **Retry semantics**: the heal step runs at most once per action attempt. It is not itself retried. When `node-error-handling` is also live, the heal runs inside each retry attempt (so a node with `retry={max_attempts:3}` may heal up to 3 times across attempts — but each attempt is one heal). When the heal succeeds, the action returns success; the per-action retry loop is satisfied for that attempt.
- **Events**: two new event types `node_self_healed` (carries `old_selector`, `new_selector`, `confidence`, `cost_hint`) and `node_self_heal_failed` (carries the original error AND the agent's failure reason, e.g. low confidence or no candidate). Both are persisted via the existing `record_event` plumbing.
- **Settings**: `LlmConfig` gains `self_healing_enabled: bool = True`. Per-node override via `node.params.auto_heal: bool = True` (default true). When the global toggle is off, the heal step is skipped entirely regardless of per-node settings.
- **UI**:
  - The RunLog renders self-healed action rows with a small wand icon and a "采用新选择器" button. Clicking opens the chat panel with a pre-filled user message asking the editor to apply the patch (`update_node` op with the new selector).
  - The Settings page surfaces the global toggle in the "LLM 配置" section.
  - The NodeInspector grows a small "auto_heal" switch on `click` / `fill` nodes.
- **Cost surface**: each `node_self_healed` event carries `cost_hint: {input_tokens, output_tokens, vision_calls}` populated from the ADK response when available. This is observable but NOT enforced — a future "run cost tracking" change will aggregate it. For now we just log + emit.

## Capabilities

### New Capabilities

- `selector-self-healing`: action-level wrapper, self-heal service, `SelectorFinderAgent`, two new event types, global / per-node toggle, UI surfaces.

### Modified Capabilities

- `hybrid-executor` (from `auto-agent-mvp`): deterministic action routing for `click` / `fill` now passes through the heal wrapper. Other actions are unaffected.
- `runtime-llm-config` (from `auto-agent-platform`): `LlmConfig` adds `self_healing_enabled: bool`. The model cache is unchanged.
- `run-history` (from `auto-agent-platform`): event-type union grows by two. Replay handles them.

## Impact

- **Backend**: new service (~150 LOC) + new agent (~80 LOC, mostly the system prompt). Action wrapper (~30 LOC). Schema literal extension for events. `LlmConfig` column addition (one SQLite `ALTER TABLE` via the existing additive-column convention). Tests: unit tests for the service with the agent stubbed, an integration test that runs against a deliberately broken selector and asserts a heal event.
- **Frontend**: RunLog new row variant + button. Settings toggle. NodeInspector switch. Chat-prefill helper. ~150 LOC of frontend across these.
- **Runtime**: one vision LLM call per healed action. The screenshot is ~50–200 KB; the accessibility snapshot serialised is typically <30 KB. Wall time: 1–3 s for the LLM round-trip, plus the original action's own wait. Bounded by the existing 30 s Playwright timeout — if the heal call exceeds it, the heal aborts and the action fails with the original error.
- **Migration**: `LlmConfig.self_healing_enabled` added with default `True`; an idempotent helper sets it to `True` for the existing row on first boot (marker file `backend/.self_healing_default_set`). New `node.params.auto_heal` defaults to `True` and is omitted from existing workflow JSON; pydantic defaults handle backward compat.
- **Out of scope**: caching healed selectors (per-workflow learning that bypasses the LLM call after the first successful heal — flagged as the next iteration in this area), self-healing for non-selector node types, automatic permanent application of the new selector without operator approval, cost enforcement / budget cutoffs.
