## Description

When a `click` or `fill` node's deterministic selector misses (Playwright `TimeoutError`), the executor SHALL invoke a small LLM agent to propose a replacement selector and retry the action with the candidate. The heal runs in two ordered stages: a cheap **DOM stage** that sends only the accessibility snapshot, and a more expensive **vision-fallback stage** that ALSO sends a screenshot. The vision stage runs only when the DOM stage's confidence falls below a configurable threshold (`LlmConfig.self_healing_vision_threshold`, default `0.6`).

Successful heals are observable via a `node_self_healed` event whose payload carries `mode: "dom" | "vision"`; failed heal attempts emit `node_self_heal_failed`. The original action functions are unchanged — the heal logic is a wrapper applied at executor dispatch time only for `click` and `fill` nodes.

The heal step uses the platform's active `LlmConfig` (via `get_adk_model_cached()`) so the model choice is centralised. A global toggle (`LlmConfig.self_healing_enabled`) and a per-node override (`node.params.auto_heal`) let cost-sensitive operators opt out at the granularity they care about.

Healed selectors are NOT persisted to the workflow automatically. The frontend renders a "采用新选择器" button on healed run-log rows; clicking it opens the chat panel with a pre-filled, locked-template patch-request message (`"将节点 <id> 的 selector 改为 \"<new>\""`) that the operator reviews and sends. NO bypass endpoint exists — every workflow mutation goes through the standard chat-driven editor flow so the audit trail stays coherent.

## User stories

- **As a workflow author**, I want my `click` and `fill` nodes to recover from minor DOM changes without me having to re-author the workflow every time the page is tweaked.
- **As an operator**, I want to see exactly which selectors were healed and what the new selectors were, so I can decide whether to apply the change permanently.
- **As an operator**, I want to disable self-healing globally when I'm running cost-sensitive workflows, and per-node when I want some specific actions to fail loudly rather than be auto-corrected.
- **As an operator**, I want self-healed workflows to require my approval before the new selectors land in the workflow JSON, so the platform never silently mutates my automations.

## Functional requirements

### Requirement: Action Wrapper For `click` And `fill`

The executor SHALL wrap the action coroutine at dispatch time for nodes of type `click` and `fill` with `services.self_healing.wrap_action(action_fn, node, page, *, emit, session)`. The wrapper SHALL invoke the inner action; on `playwright.async_api.TimeoutError` (and ONLY that exception type) it SHALL invoke `services.self_healing.attempt_heal(page, node, original_error)` and act on the result. Other node types SHALL be dispatched without the wrapper.

#### Scenario: Non-Playwright exception bypasses heal

- **WHEN** a `click` action raises `Exception("unexpected")` (NOT a `TimeoutError`)
- **THEN** the wrapper SHALL re-raise without invoking the heal service AND no heal event SHALL be emitted.

#### Scenario: Non-click node not wrapped

- **WHEN** a `navigate` node fails
- **THEN** the executor SHALL NOT invoke any heal logic AND the behaviour SHALL be identical to today.

### Requirement: Heal Attempted At Most Once Per Action Invocation

The heal step SHALL run at most once per action invocation. On success the wrapper SHALL retry the original action exactly once with the new selector substituted into the action's kwargs. If that second invocation also fails, the wrapper SHALL emit `node_self_heal_failed(reason="post_heal_action_failed")` AND re-raise the original `TimeoutError`. When combined with `node-error-handling`'s retry loop, each retry attempt counts as an independent action invocation and may consume one additional heal.

#### Scenario: Healed-then-action-succeeds happy path

- **WHEN** the original selector misses, the agent returns `(".new", 0.9)`, and the second action call with `.new` succeeds
- **THEN** the executor SHALL emit `node_self_healed` AND `node_completed` for the node AND the action SHALL be considered successful.

#### Scenario: Healed-then-action-also-fails

- **WHEN** the original selector misses, the agent returns `(".new", 0.9)`, but the second action call with `.new` also raises `TimeoutError`
- **THEN** the executor SHALL emit `node_self_healed` (the heal itself succeeded) AND `node_self_heal_failed(reason="post_heal_action_failed", post_heal_error=...)` AND `node_failed` with the ORIGINAL error.

### Requirement: Confidence Threshold

The heal wrapper SHALL retry the action only when the agent's confidence is `>= 0.5`. Below the threshold the wrapper SHALL emit `node_self_heal_failed(reason="low_confidence", agent_confidence=<value>)` AND re-raise the original `TimeoutError` without retrying the action.

#### Scenario: Low confidence drops the candidate

- **WHEN** the agent returns `(".guess", 0.31)`
- **THEN** the wrapper SHALL emit `node_self_heal_failed(reason="low_confidence", agent_confidence=0.31)` AND SHALL NOT invoke the action with `.guess`.

### Requirement: Global And Per-Node Toggle

The heal step SHALL run if and only if `LlmConfig.self_healing_enabled` is `True` on the active row AND the node's `params.auto_heal` is `True` (default `True`). Either setting being `False` SHALL completely skip the heal step — the wrapper SHALL fall through to the inner action and let the `TimeoutError` propagate as today.

#### Scenario: Global toggle off

- **WHEN** the active `LlmConfig` has `self_healing_enabled = False`
- **THEN** no `click` / `fill` failure SHALL emit any heal event AND the behaviour SHALL be identical to a pre-self-healing build.

#### Scenario: Per-node override off

- **WHEN** the global toggle is on AND a specific `click` node has `params.auto_heal = False`
- **THEN** that node's failure SHALL NOT trigger the heal AND other `click` / `fill` nodes SHALL still attempt heals.

### Requirement: `SelectorFinderAgent` Uses Active LLM Via The Cache

The agent SHALL be an ADK `LlmAgent` whose `model` is the object returned by `get_adk_model_cached()`. The agent SHALL expose exactly one tool, `propose_selector(selector_description: str, confidence: float) -> dict`. The agent's system prompt SHALL instruct the model to call this tool exactly once with its best candidate selector and a confidence in `[0, 1]`.

#### Scenario: Agent reuses platform LLM cache

- **WHEN** the active `LlmConfig` is rotated via the Settings page (`POST /api/llm-config/{id}/activate`)
- **THEN** the next heal attempt SHALL use the newly active model (via the existing `invalidate_model_cache()` call) AND SHALL NOT require a backend restart.

### Requirement: Two-Stage Heal — DOM First, Vision Fallback

`attempt_heal` SHALL run in two ordered stages within a single action invocation:

1. **DOM stage**: capture `page.accessibility.snapshot()` (JSON, no screenshot). Invoke `SelectorFinderAgent(ax_tree=...)`. Record `(selector, confidence, mode="dom")`.
2. **Decision**: if `confidence >= LlmConfig.self_healing_vision_threshold` (default `0.6`), use the DOM-stage result and skip stage 3.
3. **Vision-fallback stage** (only if DOM-stage confidence is below the threshold): ALSO capture `page.screenshot(full_page=False, type="png", mask=[<password fields>])`. Re-invoke `SelectorFinderAgent(ax_tree=..., screenshot=...)`. Record `(selector, confidence, mode="vision")` from this second call (overwriting the stage-1 result).

The final `(selector, confidence, mode)` triple is what the wrapper applies the 0.5 confidence threshold against. `cost_hint` SHALL aggregate token usage AND `vision_calls` across BOTH stages (so a vision-fallback heal reports `vision_calls == 1` and the SUM of both calls' input/output tokens). The `node_self_healed` and `node_self_heal_failed` event payloads SHALL include the `mode` field.

Password-typed inputs SHALL be masked in the vision-stage screenshot via Playwright's `mask` parameter. No screenshot is taken in the DOM stage.

#### Scenario: DOM-first hit skips vision

- **WHEN** the DOM-stage agent returns `(".x", 0.78)` and `self_healing_vision_threshold == 0.6`
- **THEN** the heal SHALL emit `node_self_healed(mode="dom", new_selector=".x", confidence=0.78, cost_hint.vision_calls=0)` AND `page.screenshot` SHALL NOT have been called.

#### Scenario: Vision fallback when DOM confidence is low

- **WHEN** the DOM-stage agent returns `(".x", 0.45)` and the vision-stage agent returns `(".y", 0.91)` with threshold `0.6`
- **THEN** the heal SHALL emit `node_self_healed(mode="vision", new_selector=".y", confidence=0.91, cost_hint.vision_calls=1)` AND `cost_hint.input_tokens` SHALL be the SUM of both calls' input tokens (when token usage is available).

#### Scenario: Threshold knob is honoured

- **WHEN** the operator sets `self_healing_vision_threshold = 0.0` (DOM-only mode)
- **THEN** every heal SHALL emit `mode="dom"` regardless of the DOM-stage confidence AND `vision_calls` SHALL always be `0`.

#### Scenario: Always-vision mode

- **WHEN** the operator sets `self_healing_vision_threshold = 1.01`
- **THEN** every heal SHALL fall through to the vision stage AND emit `mode="vision"` AND `vision_calls` SHALL always be `1`.

#### Scenario: Password masking

- **WHEN** the vision stage runs and the page contains a visible `<input type="password">`
- **THEN** the screenshot passed to the agent SHALL show that input as a solid coloured rectangle (Playwright's default mask) AND SHALL NOT include the underlying value.

### Requirement: 15 s Timeout Around Each Agent Call

EACH agent invocation inside `attempt_heal` (the DOM stage AND, when reached, the vision stage) SHALL be independently wrapped in `asyncio.wait_for(..., 15.0)`. On timeout of either stage the heal SHALL emit `node_self_heal_failed(reason="agent_error", mode=<stage that timed out>, original_error="agent timeout after 15s")` AND SHALL re-raise the original Playwright `TimeoutError`. A DOM-stage timeout SHALL NOT trigger the vision stage as a fallback (the time budget is already spent).

#### Scenario: DOM-stage agent timeout

- **WHEN** the DOM-stage call exceeds 15 s wall time
- **THEN** the heal SHALL abort with `mode="dom", reason="agent_error"` AND the vision stage SHALL NOT be invoked AND the executor SHALL proceed as if no heal was attempted (raise the original error).

#### Scenario: Vision-stage agent timeout

- **WHEN** the DOM stage completed with low confidence AND the vision-stage call exceeds 15 s wall time
- **THEN** the heal SHALL abort with `mode="vision", reason="agent_error"` AND the executor SHALL raise the original Playwright `TimeoutError`.

### Requirement: Vision-Not-Supported Short-Circuit

If the heal attempt fails specifically because the active model has no vision capability (detectable from the provider's error), the heal service SHALL set a process-wide flag `_VISION_SUPPORTED = False` for the rest of the current run AND SHALL emit `node_self_heal_failed(reason="agent_error", original_error="model has no vision capability")` ONCE for that run. Subsequent `click` / `fill` failures in the same run SHALL skip the heal step entirely and SHALL NOT emit additional heal events for the same reason.

#### Scenario: First miss emits, subsequent miss skips

- **WHEN** the active model has no vision capability AND two `click` nodes in the same run both miss
- **THEN** exactly ONE `node_self_heal_failed(reason="agent_error")` event SHALL be emitted (for the first miss) AND the second miss SHALL emit no heal events.

### Requirement: Events Persisted Via Existing Plumbing

The two new event types (`node_self_healed`, `node_self_heal_failed`) SHALL be persisted via `services.runs.record_event(...)` exactly as existing events, with payload shapes per the data model section. Replay SHALL render them in the run log; replay timing SHALL NOT introduce a wait for them (immediate render, like the existing rule for `wait` / `node_retry`).

#### Scenario: Replay renders both event types

- **WHEN** a past run had one `node_self_healed` and one `node_self_heal_failed`
- **THEN** the replay timeline SHALL render both rows with the wand icon styling per the Frontend Requirement.

### Requirement: "采用新选择器" Chat Prefill Flow — No Bypass Endpoint

The frontend SHALL render a "采用新选择器" button on every `node_self_healed` row in the RunLog. Clicking SHALL open the chat panel for the workflow AND pre-fill the composer text with the LOCKED template `"将节点 <node_id> 的 selector 改为 \"<new_selector>\""` (no old-selector text; the editor agent looks up the current value). The button SHALL NOT auto-send; the operator reviews and sends manually. The resulting editor turn SHALL produce a standard `update_node` patch that mutates `params.selector`.

The platform SHALL NOT expose any bypass endpoint (no `apiClient.workflows.applyHeal(...)` shortcut, no equivalent backend route). Every workflow mutation goes through the chat-driven editor flow so the audit trail (every change is a chat turn) stays coherent.

The editor agent's system prompt SHALL include a one-shot example mapping the locked template wording above to an `update_node` patch whose `patch.params = {"selector": "<new>"}`, so the mapping is reliable across editor LLM models.

#### Scenario: Click opens chat with the locked template

- **WHEN** a `node_self_healed` row has `new_selector=".new"`, `node_id="n4"`
- **THEN** the chat composer SHALL be pre-filled with the exact string `"将节点 n4 的 selector 改为 \".new\""` AND the send button SHALL be focused but not pressed.

#### Scenario: No bypass endpoint

- **WHEN** an integration test scans the codebase for `applyHeal` (or any synonym route like `/api/workflows/.../apply-heal`)
- **THEN** no matches SHALL be found AND the only path to apply a healed selector SHALL be a chat-editor turn.

### Requirement: Cost Hint Surfaced In The Event

Both heal events SHALL include a `cost_hint: {input_tokens: int|null, output_tokens: int|null, vision_calls: int}` field populated from the ADK response when available. `vision_calls` SHALL be `1` for every heal attempt (success or failure that involved the agent). The frontend SHALL render the cost hint as a small icon with a tooltip showing the token counts.

#### Scenario: Token counts when provider supports usage

- **WHEN** the active provider returns input / output token counts in its response
- **THEN** `cost_hint.input_tokens` and `cost_hint.output_tokens` SHALL be populated with the integers AND the tooltip SHALL show them.

#### Scenario: Token counts when provider does NOT support usage

- **WHEN** the provider does not return token counts
- **THEN** the fields SHALL be `null` AND the tooltip SHALL read `"消耗未知"`.

### Requirement: Abort Cancels Heal In Flight

The wrapper SHALL check the executor's abort flag both before calling the heal service AND immediately after the heal call returns. An abort during the heal SHALL cancel the awaiting `asyncio.wait_for(...)` AND SHALL cause the wrapper to re-raise the original `TimeoutError` so the executor proceeds to its abort branch.

#### Scenario: Abort mid-heal

- **WHEN** an abort frame is received while the heal LLM call is in flight
- **THEN** the heal task SHALL be cancelled within ~50 ms AND no `node_self_healed` event SHALL be emitted for that node AND the run SHALL terminate as `aborted`.

## API contract

No new HTTP endpoints. The event-type literal grows by two entries:

| Event type | Payload keys |
| --- | --- |
| `node_self_healed` | `original_selector: str`, `new_selector: str`, `confidence: float`, `mode: "dom"\|"vision"`, `cost_hint: CostHint` |
| `node_self_heal_failed` | `original_selector: str`, `reason: "low_confidence"\|"no_candidate"\|"post_heal_action_failed"\|"agent_error"`, `mode: "dom"\|"vision"`, `agent_confidence: float\|null`, `original_error: str`, `post_heal_error: str\|null`, `cost_hint: CostHint` |

`CostHint`:

```json
{
  "input_tokens": 1234 | null,
  "output_tokens": 12 | null,
  "vision_calls": 0 | 1
}
```

`vision_calls == 0` for DOM-stage hits; `vision_calls == 1` for vision-fallback hits. `input_tokens` / `output_tokens` are the SUM of all agent calls made during the heal (so a vision-fallback heal aggregates both stages).

`LlmConfig` extension: adds `self_healing_enabled: bool = True` AND `self_healing_vision_threshold: float = 0.6` (range `[0.0, 1.0]`). `POST /api/llm-config` and `PUT /api/llm-config/{id}` accept both fields; `GET` responses include both.

`node.params.auto_heal` extension for `click` and `fill`: `bool = True`, optional.

## Data model

Schema additions (no DB table changes beyond the one column on `LlmConfig`):

```python
class LlmConfig(SQLModel, table=True):
    # ...existing...
    self_healing_enabled: bool = Field(default=True)
    self_healing_vision_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
```

Workflow-JSON additions (inside `WorkflowVersion.workflow_json`):

```python
# Per-type params model registered for click / fill
class ClickParams(BaseModel):
    selector: str
    auto_heal: bool = True

class FillParams(BaseModel):
    selector: str
    value: str
    auto_heal: bool = True
```

Service surface:

```python
# backend/app/services/self_healing.py
@dataclass
class HealResult:
    healed: bool
    new_selector: Optional[str]
    confidence: Optional[float]
    mode: Literal["dom", "vision"]    # which stage produced the recorded result
    cost_hint: CostHint               # aggregated across all stages run
    failure_reason: Optional[str]
    event_payload: dict       # for node_self_healed
    failure_payload: dict     # for node_self_heal_failed

def wrap_action(action_fn, node, page, *, emit, session) -> Callable: ...
async def attempt_heal(page, node, original_error) -> HealResult: ...
def _is_enabled(node, session) -> bool: ...
def _vision_threshold(session) -> float: ...
```

## Out of Scope

- Caching healed selectors per workflow + per URL (the obvious next iteration; this change emits enough information for a future change to build the cache).
- Self-healing of non-`click` / non-`fill` actions (`navigate`, `extract`, `fuzzy_action`, `wait`, `condition`).
- Auto-application of new selectors to the workflow JSON without operator approval.
- Per-heal cost budgets / hard caps (logged via `cost_hint`; enforcement is future work).
- Multiple candidate selectors returned by the agent (`propose_selector` returns exactly one).
- Heal step on non-headed Chromium with different behaviour. The wrapper works identically; the screenshot is still taken.
- Vision-quality fallback chain ("if model A has no vision, try model B"). Single active LLM per design.
- Heal-step parallelism — each healed action is sequential within its node.
