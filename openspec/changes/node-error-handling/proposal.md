## depends_on

- `auto-agent-mvp` — workflow schema (`Node`, `Edge`), executor walker, `node_failed` event.
- `auto-agent-platform` — `RunEvent` table, `services.runs` state machine, executor's `record_event` callback.
- `node-context-variables` (soft) — on-error branches and chat / log messages reference `{{nodes.<id>.error.message}}` once `node-output-interpolation` is in place. This change ships without it (the error blob is still exposed on the `node_failed` event, just not interpolable into downstream params).

No other dependency on the current batch.

## Why

Today a single failing node kills the entire run. The executor's `Failure Isolation` requirement (from `hybrid-executor`) emits `node_failed` and stops traversal — there is no retry, no alternate path, no "best effort". For workflows that involve flaky selectors, transient HTTP errors, or rate-limited APIs, this means one bad pixel kills a 12-step automation that otherwise would have succeeded.

The fix is three small, orthogonal additions:

1. **Per-node retry policy**: a node declares `retry: {max_attempts, backoff_ms}` and the executor retries the action up to `max_attempts` times with linear backoff between attempts. Each attempt is a discrete event so the operator can see what happened.
2. **On-error policy**: a node declares `on_error ∈ {"fail_run", "continue", "branch"}`. The default `fail_run` preserves today's behaviour. `"continue"` moves to the next outgoing edge with `kind="next"` (the node's output is `{"error": ...}`). `"branch"` looks for an outgoing edge with `kind="on_error"` and follows it; if none exists it degrades to `fail_run`.
3. **On-error branch edges**: a new `kind ∈ {"next", "on_error"}` attribute on `Edge`. Default `"next"` for every existing edge. The executor inspects `kind` when picking the next node; combined with `on_error="branch"` this gives the operator a structured try/catch.

The same building blocks compose to a try/catch group: wrap a sub-chain in nodes whose `on_error="branch"` routes to a shared cleanup node via `kind="on_error"` edges.

This change is independent enough to ship before #4 (human-in-the-loop) and #5 (expanded node library) but is the strongest "quality of life" win for users running real browser automations.

## What Changes

- **Schema** (additive, all stored inside `WorkflowVersion.workflow_json` — no DB migration):
  - `Node.retry: {max_attempts: int, backoff_ms: int} | null` (default `null` ≡ no retry).
  - `Node.on_error: "fail_run" | "continue" | "branch"` (default `"fail_run"`).
  - `Edge.kind: "next" | "on_error"` (default `"next"`).
- **Executor**: the action invocation is wrapped in a retry loop. On every retry the executor emits a `node_retry` event with `attempt: int`, `error: str`, `next_attempt_at: datetime` BEFORE sleeping. When all attempts are exhausted, on-error policy decides the next traversal step. Linear backoff: `attempt_i_delay = retry.backoff_ms * i` (deterministic, no jitter in v1).
- **RunEvent**: adds `node_retry` to the event type literal. `RunEvent.payload_json` for retries follows the same shape as `node_failed` but with the extra `attempt` and `next_attempt_at` fields.
- **UI**:
  - NodeInspector grows a "错误处理" section with controls for `retry.max_attempts`, `retry.backoff_ms`, `on_error`, and a hint listing the canvas conventions for `on_error` edges.
  - Canvas draws `kind="on_error"` edges as dashed red lines, distinct from regular `kind="next"` edges.
  - RunLog / RunReplay renders retries as nested rows under the parent node row (collapsed by default; expandable to show each attempt's error).
- **Migration**: no DB migration. Every existing edge implicitly has `kind="next"`; the executor and the frontend default to `"next"` whenever the field is missing on a deserialised workflow. Same for `Node.on_error` (defaults to `"fail_run"`) and `Node.retry` (defaults to `null`).

## Capabilities

### New Capabilities

- `node-error-handling`: the retry policy schema, the `on_error` policy schema, the `Edge.kind` attribute, the executor's retry loop, the `node_retry` event, the canvas dashed-red edge styling, the NodeInspector "错误处理" section, the RunLog nested-retry rows.

### Modified Capabilities

- `hybrid-executor` (from `auto-agent-mvp`): the executor's "Failure Isolation" requirement is generalised. A failed action no longer always stops traversal; the on-error policy and the retry policy decide. Existing default behaviour (`on_error="fail_run"`, no retry) is preserved.
- `workflow-schema` (from `auto-agent-mvp`): `Node` and `Edge` accept the three new optional fields. The pydantic models default them to the values described above.
- `run-history` (from `auto-agent-platform`): event-type literal grows by one entry (`node_retry`). Replay player handles it.
- `chat-authoring` (from `auto-agent-platform`): the editor's patch op set is unchanged — `update_node` already accepts arbitrary `patch.params` and now also accepts `retry` and `on_error` at the same level via a small extension to the `update_node` schema. Editor system prompt documents the new fields with one example.

## Impact

- **Backend**: ~80 lines in `app/executor.py` for the retry loop and the on-error branch picker. ~20 lines in `app/schemas.py` to add the three optional fields (pydantic defaults handle backward compatibility). New `node_retry` event entry. Tests: new unit tests for retry counting and on-error routing; one integration test that combines both.
- **Frontend**: NodeInspector grows a small "错误处理" sub-form (~80 LOC). Canvas edge renderer learns `kind="on_error"` (~10 LOC, one CSS class). RunLog row renderer learns to nest `node_retry` rows under their parent `node_started` row (~30 LOC).
- **Runtime**: zero overhead for workflows that don't use the new fields. With retries enabled, the per-node wall time grows by `Σ retry.backoff_ms * i`; the executor's single-Chromium-tab constraint means this delays the queue's other workflows too, so the operator is encouraged to keep `backoff_ms` modest.
- **Migration**: none. Every existing workflow continues to behave exactly as before.
- **Out of scope**: circuit breakers (auto-disable a workflow after N consecutive failures), alerting on repeated failures (covered by the deferred notifications change), per-attempt random jitter in the backoff, exponential backoff (linear is enough for the POC).
