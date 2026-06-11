## Description

A node may declare a retry policy and a failure policy. An edge may declare a `kind` that distinguishes "happy path" successors (`"next"`) from "error path" successors (`"on_error"`). The executor consults these fields when it would otherwise have terminated the run on a failed action: it retries first per the retry policy, then routes per the on-error policy. Every retry is its own observable event.

The default values are chosen to preserve today's behaviour exactly: `retry = null` (one attempt, no retry events), `on_error = "fail_run"` (today's failure-isolation behaviour), `kind = "next"` (today's edge semantics). Workflows that do not opt in are byte-for-byte unchanged in their event streams.

## User stories

- **As a workflow author**, I want a flaky click to retry a few times before giving up, so transient page slowness doesn't kill a long run.
- **As a workflow author**, I want one node's failure to route to a cleanup branch instead of killing the whole run, so I can take a screenshot and stop the browser gracefully.
- **As an operator**, I want every retry to show up in the run log so I can see which selectors are flaky and decide whether to switch to `fuzzy_action`.
- **As an operator**, I want the canvas to visually distinguish error-path edges so a glance tells me where a workflow's recovery goes.
- **As the editor LLM**, I want a small, documented schema fragment so I can add retries on the user's request without learning a templating language.

## Functional requirements

### Requirement: Per-Node Retry Policy

A `Node` MAY carry an optional `retry: {max_attempts: int, backoff_ms: int} | null` field. `max_attempts` SHALL be a positive integer in `[1, 10]`. `backoff_ms` SHALL be a non-negative integer in `[0, 60_000]`. When `retry` is `null` (default), the executor SHALL run the action exactly once with no retry-related events.

#### Scenario: No retry preserves today's behaviour

- **WHEN** a node has `retry = null` and its action raises
- **THEN** the executor SHALL emit `node_failed` exactly once (with NO `node_retry` events) and SHALL proceed per `on_error`.

#### Scenario: Schema validation rejects bad bounds

- **WHEN** a workflow JSON contains `retry.max_attempts = 0` or `retry.backoff_ms = -1` or `retry.max_attempts = 11`
- **THEN** pydantic validation SHALL fail before the workflow is saved.

### Requirement: Retry Loop With Linear Backoff And First-Attempt Resolution Lock

When `retry` is non-null, the executor SHALL invoke the action up to `retry.max_attempts` times. The first attempt SHALL have no preceding delay. Each retry attempt `i ∈ [2, max_attempts]` SHALL be preceded by `await asyncio.sleep(retry.backoff_ms * (i-1) / 1000)`.

The executor SHALL resolve `params` through the credential / variable interpolation pass EXACTLY ONCE — on the first attempt — and SHALL cache the resolved dict for all subsequent retry attempts within the same `_run_node` invocation. Subsequent attempts SHALL invoke the action with the cached params; they SHALL NOT re-resolve. This applies to BOTH `{{cred...}}` and `{{nodes...}}` tokens. Rationale: predictability — a retry must not change semantics under the operator. The explicit construct for per-attempt re-resolution is to wrap the node in a `foreach` (once `expanded-node-library` ships) or to rebuild the workflow with distinct per-attempt branches.

#### Scenario: Linear backoff timing

- **WHEN** `retry = {max_attempts: 3, backoff_ms: 500}` and attempts 1 and 2 fail and attempt 3 succeeds
- **THEN** the wall clock between attempt 1's failure and attempt 2's start SHALL be ~500 ms, AND between attempt 2's failure and attempt 3's start SHALL be ~1000 ms.

#### Scenario: First-attempt resolution is locked

- **WHEN** a node's `params` contain `{{nodes.x.output.v}}` resolved to `"v1"` on attempt 1, AND a test fixture mutates `context["x"]["output"]["v"] = "v2"` between attempt 1 and attempt 2
- **THEN** attempt 2 SHALL invoke the action with the cached params containing `"v1"` AND SHALL NOT re-resolve the token.

#### Scenario: Credential rotation does not affect in-flight retries

- **WHEN** a node's `params` contain `{{cred.api.token}}` resolved on attempt 1, AND the operator rotates the credential between attempt 1 and attempt 2
- **THEN** attempt 2 SHALL invoke the action with the attempt-1 token value AND the new token value SHALL take effect only on the next run.

### Requirement: `node_retry` Event Per Failed Attempt

For every failed attempt that is NOT the final one, the executor SHALL emit a `node_retry` event BEFORE the inter-attempt sleep. The event's payload SHALL contain `attempt: int` (the just-failed attempt number), `error: str` (`str(exc)`), `error_kind: str` (`type(exc).__name__`), and `next_attempt_at: datetime` (the wall-clock time after the sleep). The event SHALL be persisted by `services.runs.record_event(...)` in the same way as every other event.

#### Scenario: Two retries observed

- **WHEN** `max_attempts = 3` and attempts 1 and 2 fail and attempt 3 succeeds
- **THEN** the persisted event stream SHALL contain `node_started`, `node_retry(attempt=1)`, `node_retry(attempt=2)`, `node_completed(attempt=3)` — in that order, monotonic `seq`.

#### Scenario: All attempts exhausted

- **WHEN** `max_attempts = 3` and all three attempts fail
- **THEN** the event stream SHALL contain `node_started`, `node_retry(attempt=1)`, `node_retry(attempt=2)`, `node_failed(attempt=3, error_kind=…)` — exactly two `node_retry` events.

### Requirement: On-Error Policy

A `Node` MAY carry an `on_error: "fail_run" | "continue" | "branch"` field, defaulting to `"fail_run"`. The executor SHALL consult this field AFTER the retry loop has exhausted. The three policies SHALL behave as follows:

- `"fail_run"` (default): the executor SHALL emit `run_failed` and stop traversal (today's behaviour); the run terminates with status `failed`.
- `"continue"`: the executor SHALL add `context[node.id] = {"error": {"message": str(exc), "kind": type(exc).__name__, "attempts": attempts_used}}` to the per-run context AND SHALL pick the next node via the FIRST outgoing edge with `kind="next"`, using existing condition logic. The run's per-run flag `had_tolerated_failure` SHALL be set to `True`.
- `"branch"`: the executor SHALL add the same `error` context entry AND SHALL pick the FIRST outgoing edge with `kind="on_error"`. If no such edge exists, the executor SHALL append `"; on_error=branch but no on_error edge from node <id>; falling back to fail_run"` to the `node_failed.error` text and SHALL behave as `"fail_run"`. When the branch is followed, the run's per-run flag `had_tolerated_failure` SHALL be set to `True`.

#### Scenario: continue follows next edge with completed_with_errors terminal

- **WHEN** node `n3` has `on_error="continue"` and a single outgoing edge `kind="next"` to `n4`, and `n4` succeeds
- **THEN** after `n3` fails, the executor SHALL emit `node_failed(n3)` AND THEN `node_started(n4)`, AND the run SHALL terminate with status `completed_with_errors` (NOT `completed`), emitting `run_completed_with_errors` with `failed_node_count == 1`.

#### Scenario: branch follows on_error edge

- **WHEN** node `n3` has `on_error="branch"` and two outgoing edges (`kind="next"` to `n4`, `kind="on_error"` to `n_cleanup`)
- **THEN** after `n3` fails, the executor SHALL pick `n_cleanup` (NOT `n4`).

#### Scenario: branch with no on_error edge degrades

- **WHEN** node `n3` has `on_error="branch"` and only `kind="next"` outgoing edges
- **THEN** the `node_failed.error` text SHALL end with `"falling back to fail_run"` AND the run SHALL terminate `failed`.

### Requirement: Edge `kind` Attribute

An `Edge` MAY carry a `kind: "next" | "on_error"` field, defaulting to `"next"`. The default SHALL apply to every edge in a workflow JSON serialised before this change shipped. The frontend canvas SHALL render `kind="on_error"` edges with a dashed red stroke (`stroke-dasharray: 6 4`, error-color from theme tokens) and a hover tooltip identifying the target.

#### Scenario: Legacy edges default to next

- **WHEN** a workflow JSON loaded from `WorkflowVersion.workflow_json` has edges without a `kind` field
- **THEN** pydantic deserialisation SHALL fill in `kind="next"` AND the executor SHALL treat them identically to today.

#### Scenario: Canvas distinguishes the two kinds

- **WHEN** a workflow has at least one `kind="on_error"` edge
- **THEN** the canvas SHALL render that edge dashed red AND solid (non-dashed) for every `kind="next"` edge.

### Requirement: New Terminal Run Status `completed_with_errors`

`Run.status` SHALL accept the new literal value `"completed_with_errors"` alongside `queued | running | completed | failed | aborted`. This is a cross-change augmentation of the platform's `workflow-persistence` and `run-history` capabilities (defined in `auto-agent-platform`); the augmentation is application-level only (the `Run.status` column is `TEXT` at the DB layer; the literal restriction lives in `app/schemas_api.py::RunStatus`). The full enum after this change SHALL be:

```
queued | running | completed | completed_with_errors | failed | aborted
```

The executor SHALL set the terminal status to `completed_with_errors` iff the run reached its end node naturally (no `run_failed`, no `run_aborted`) AND the per-run `had_tolerated_failure` flag is `True` (i.e. at least one `node_failed` event was emitted AND tolerated via `on_error ∈ {"continue", "branch"}`). Otherwise the terminal status remains `completed`.

A new terminal event `run_completed_with_errors` SHALL be emitted in place of `run_completed` in those cases. Its payload SHALL include `failed_node_count: int` and `failed_node_ids: list[str]`.

The scheduler SHALL treat `completed_with_errors` as a terminal status (releases the queue slot, promotes the next queued row) — semantically equivalent to `completed` for queue advancement.

The runs-list UI SHALL render `completed_with_errors` with an amber/warning pill distinct from green `completed` and red `failed`. Hovering the pill SHALL show the `failed_node_count` from the terminal event.

#### Scenario: All-green run still terminates `completed`

- **WHEN** a run completes with zero `node_failed` events
- **THEN** the terminal status SHALL be `completed` AND the terminal event SHALL be `run_completed` (unchanged from today).

#### Scenario: Tolerated continue terminates `completed_with_errors`

- **WHEN** a run had one `node_failed` event tolerated via `on_error="continue"` AND reached its end node
- **THEN** the terminal status SHALL be `completed_with_errors` AND the terminal event SHALL be `run_completed_with_errors` with `failed_node_count == 1` AND `failed_node_ids == ["<id of the failed node>"]`.

#### Scenario: Tolerated branch terminates `completed_with_errors`

- **WHEN** a run had one `node_failed` event tolerated via `on_error="branch"` (followed a `kind="on_error"` edge) AND reached its end node
- **THEN** the terminal status SHALL be `completed_with_errors`.

#### Scenario: `fail_run` still terminates `failed`

- **WHEN** any node fails with `on_error="fail_run"` (default)
- **THEN** the terminal status SHALL be `failed` (NOT `completed_with_errors`) AND the terminal event SHALL be `run_failed`.

#### Scenario: Branch degradation also `failed`

- **WHEN** a node has `on_error="branch"` but no `kind="on_error"` outgoing edge
- **THEN** the executor SHALL fall back to `fail_run` AND the terminal status SHALL be `failed`.

#### Scenario: Scheduler advances on completed_with_errors

- **WHEN** a run terminates `completed_with_errors` AND another run for the same workflow is queued
- **THEN** the queue slot SHALL be released AND the queued run SHALL be promoted to `running` exactly as if the terminal status had been `completed`.

### Requirement: Context Entry Shape For Failed Nodes

When `on_error ∈ {"continue", "branch"}` and a node fails (after retries), the executor SHALL set `context[node.id] = {"error": {"message": <exception str>, "kind": <exception class name>, "attempts": <int>}}`. The key is `error`, not `output`. Downstream references via `{{nodes.<id>.error.message}}` SHALL resolve once `node-context-variables` is in place; references via `{{nodes.<id>.output.…}}` against a failed-then-continued node SHALL fail loudly per that change's missing-path rule.

#### Scenario: Continued node leaves error context

- **WHEN** node `n3` fails with `on_error="continue"` and exception `TimeoutError("locator: Timeout 30000ms exceeded")`
- **THEN** `context["n3"]` SHALL equal `{"error": {"message": "TimeoutError: locator: Timeout 30000ms exceeded", "kind": "TimeoutError", "attempts": 1}}`.

### Requirement: Abort During Retry Cancels The Sleep

The abort flag SHALL be checked both before the inter-attempt sleep AND while awaiting it (`asyncio.sleep` SHALL be wrapped so the abort signal cancels it). On abort during a retry loop the executor SHALL emit `run_aborted` and SHALL NOT emit further `node_retry` events for that node.

#### Scenario: Abort mid-backoff

- **WHEN** a node is between attempt 1 and attempt 2 (sleeping `backoff_ms`) and the user posts an abort frame
- **THEN** the sleep SHALL be cancelled within ~50 ms AND `run_aborted` SHALL be the next emitted event.

### Requirement: Replay Compresses Retry Backoff

The frontend replay player SHALL fire `node_retry` events with zero inter-attempt sleep, mirroring how `wait` node delays are collapsed for replay. The visual nesting under the parent node row SHALL still render.

#### Scenario: Replay is fast

- **WHEN** a past run had three `node_retry` events totalling 6 s of live backoff
- **THEN** the replay at 1× speed SHALL render the three `node_retry` rows in under 100 ms of wall time (subject to the existing 2 s cap on inter-event waits).

### Requirement: NodeInspector "错误处理" Section

The NodeInspector SHALL render a "错误处理" section per selected node with three controls (`重试次数`, `重试间隔 (ms)`, `失败策略`). When `重试次数` is non-empty the inspector SHALL render a worst-case wall-time preview text (`"最长重试时间：N 秒"`). When `失败策略 = 走错误分支` the inspector SHALL render a hint pointing the operator to draw a dashed-red edge on the canvas.

#### Scenario: Wall-time preview

- **WHEN** the operator sets `重试次数 = 3` and `重试间隔 = 500`
- **THEN** the preview SHALL read `"最长重试时间：1.5 秒"` (sum of `500 + 1000 = 1500` ms).

### Requirement: Editor Patches Support The New Fields

The chat editor's `update_node` patch op SHALL accept `retry` and `on_error` at the same level as `label`, `type`, and `params`. The patch application helper SHALL deep-merge these fields onto the existing node and SHALL re-validate the resulting workflow before persisting a new `WorkflowVersion`.

#### Scenario: Editor turns on retry

- **WHEN** the user says "重试这个节点三次" and the editor returns `patch = [{op:"update_node", id:"n4", patch:{retry:{max_attempts:3, backoff_ms:500}}}]`
- **THEN** the resulting `WorkflowVersion` SHALL contain `n4` with the new `retry` field AND no other fields SHALL change.

## API contract

No new HTTP endpoints. The event-type literal grows by two entries and `RunStatus` grows by one:

| Event type | Payload keys | Notes |
| --- | --- | --- |
| `node_retry` | `attempt: int`, `error: str`, `error_kind: str`, `next_attempt_at: datetime` | emitted before each inter-attempt sleep |
| `run_completed_with_errors` | `failed_node_count: int`, `failed_node_ids: list[str]` | replaces `run_completed` when ≥1 tolerated failure occurred |
| `node_completed` (extended) | adds optional `attempt: int` | omitted for non-retrying nodes |
| `node_failed` (extended) | adds optional `attempt: int`, `error_kind: str` | always present after this change ships |

`RunStatus` literal grows from `queued | running | completed | failed | aborted` to `queued | running | completed | completed_with_errors | failed | aborted`. This is a cross-change augmentation of `auto-agent-platform`'s `workflow-persistence` and `run-history` capabilities; the augmentation is application-level only (no DB ALTER required because `Run.status` is a `TEXT` column).

## Data model

Schema additions (all inside `WorkflowVersion.workflow_json`; no DB column changes):

```python
class RetryPolicy(BaseModel):
    max_attempts: int = Field(ge=1, le=10)
    backoff_ms: int = Field(ge=0, le=60_000)

class Node(BaseModel):
    # ...existing...
    retry: Optional[RetryPolicy] = None
    on_error: Literal["fail_run", "continue", "branch"] = "fail_run"

class Edge(BaseModel):
    # ...existing...
    kind: Literal["next", "on_error"] = "next"
```

In-memory context shape for a failed-then-continued node:

```python
context[node_id] = {
    "error": {
        "message": "TimeoutError: ...",
        "kind": "TimeoutError",
        "attempts": 3,
    }
}
```

## Out of Scope

- Exponential backoff. Linear only in v1.
- Random jitter. Deterministic timing for replay parity.
- Circuit breakers (auto-disable a workflow after N consecutive failed runs).
- Cross-node retry budgets ("retry the whole sub-chain N times"). Compose via `on_error="branch"` and an `on_error` edge looping back.
- Per-error-type retry rules ("retry only on TimeoutError"). Composable later via `error_kind` checks once context references resolve.
- Alerting on repeated failures. Belongs to the deferred notifications change.
- A new run status `completed_with_errors`. Flagged in design open questions; if decided yes, will be a small follow-up to `run-history`.
