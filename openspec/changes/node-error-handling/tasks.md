## 1. Shared contract (parent worker)

- [ ] 1.1 `[shared-contract]` Extend `backend/app/schemas.py`:
  - new `RetryPolicy(BaseModel)` with `max_attempts: int = Field(ge=1, le=10)` and `backoff_ms: int = Field(ge=0, le=60_000)`;
  - `Node.retry: Optional[RetryPolicy] = None`;
  - `Node.on_error: Literal["fail_run","continue","branch"] = "fail_run"`;
  - `Edge.kind: Literal["next","on_error"] = "next"`.
- [ ] 1.2 `[shared-contract]` Extend `backend/app/schemas_api.py`:
  - event-type literal union to include `"node_retry"` AND `"run_completed_with_errors"`;
  - add `NodeRetryPayload(BaseModel)` with `attempt: int`, `error: str`, `error_kind: str`, `next_attempt_at: datetime`;
  - add `RunCompletedWithErrorsPayload(BaseModel)` with `failed_node_count: int`, `failed_node_ids: list[str]`;
  - update `WSEvent` discriminated union accordingly;
  - extend the `RunStatus` Pydantic literal to include `"completed_with_errors"` (cross-change augmentation of `auto-agent-platform`'s `workflow-persistence` / `run-history` capabilities; no DB ALTER required because `Run.status` is a `TEXT` column).
- [ ] 1.3 `[shared-contract]` Mirror TS types in `frontend/src/types.ts` (`RetryPolicy`, extended `Node` and `Edge`) and in `frontend/src/types-platform.ts` (`NodeRetryPayload`, `RunEventType` union grows, `RunStatus` union grows by `"completed_with_errors"`).
- [ ] 1.4 `[shared-contract]` Smoke-check: `python -c "from app.schemas import Workflow, Edge, Node; assert Edge.model_fields['kind'].default == 'next'; assert Node.model_fields['on_error'].default == 'fail_run'; print('ok')"` and `cd frontend && npx tsc --noEmit` pass.

## 2. Backend executor (Sibling A — `[backend-runtime]`)

- [ ] 2.1 Refactor `backend/app/executor.py::run_workflow` to extract the per-node action invocation into a `_run_node(node, context, session, ...) -> NodeOutcome` helper. `NodeOutcome` is a small dataclass `{kind: "completed"|"failed", output: dict|None, error: BaseException|None, attempts: int}`. The helper SHALL resolve `node.params` via `variable_interpolation.resolve_params(...)` EXACTLY ONCE before the retry loop and cache the resolved dict for all attempts (per design Decision 11).
- [ ] 2.2 Implement the retry loop inside `_run_node`:
  - if `node.retry is None`: run once, no retry events;
  - else: loop `i` in `1..node.retry.max_attempts`; every attempt invokes `action_fn(**cached_resolved_params)` — DO NOT re-resolve `params` between attempts (per design Decision 11);
  - on failure and `i < max_attempts`, emit `node_retry` with `attempt=i`, `error=str(exc)`, `error_kind=type(exc).__name__`, `next_attempt_at=now+timedelta(ms=node.retry.backoff_ms*i)`, then `await asyncio.sleep(node.retry.backoff_ms*i/1000)`; check abort flag both before the sleep and after.
- [ ] 2.3 Implement on-error routing in `run_workflow`'s outer loop:
  - `outcome.kind == "completed"` → existing path; emit `node_completed` (now carries `attempt=outcome.attempts`); add `context[node.id] = outcome.output`; pick next via `kind="next"` edge using existing condition logic;
  - `outcome.kind == "failed"` → emit `node_failed` (carries `attempt=outcome.attempts`, `error_kind`); set a per-run flag `had_tolerated_failure = True` whenever `on_error` is `"continue"` or `"branch"` AND the branch is taken successfully (per Decision 12); branch on `node.on_error`:
    - `"fail_run"`: emit `run_failed`, stop traversal with terminal status `failed`;
    - `"continue"`: add `context[node.id] = {"error":{...}}` per design Decision 8; pick next via `kind="next"` edge;
    - `"branch"`: pick FIRST outgoing edge with `kind="on_error"`; if absent, fall back to `"fail_run"` with the appended note in `error`.
- [ ] 2.3a When the run reaches its end node naturally (no `run_failed`, no `run_aborted`), set the terminal `Run.status` to `"completed_with_errors"` if `had_tolerated_failure` is `True`, otherwise `"completed"`. Emit the matching `run_completed_with_errors` or `run_completed` event (the existing event-type set is extended by `run_completed_with_errors` — add to §1.2's event-type union).
- [ ] 2.4 Update `backend/app/services/runs.py` event persistence — accept `node_retry` events; persist with `event_type="node_retry"` and the payload dict unchanged.
- [ ] 2.5 Update `backend/app/agents/editor.py` system prompt with the paragraph from design Decision 10.
- [ ] 2.6 Update `backend/app/agents/planner.py` system prompt with the same paragraph plus a one-line example.
- [ ] 2.7 Add unit tests `backend/tests/test_executor_retry.py`:
  - no retry → one attempt, no `node_retry` events emitted (today's behaviour);
  - retry succeeds on 2nd attempt → one `node_retry` event with `attempt=1`, one `node_completed` with `attempt=2`;
  - retry exhausts all attempts → `max_attempts-1` `node_retry` events, one `node_failed` with `attempt=max_attempts`;
  - retry interleaves abort: abort flag set during the inter-attempt sleep cancels the loop and emits `run_aborted` instead of `node_retry/node_failed`;
  - **first-attempt resolution lock (Decision 11)**: a node whose `params` reference `{{nodes.x.output.v}}` whose underlying context entry is mutated between attempts (e.g. by a test fixture monkey-patching the context dict) SHALL still receive the attempt-1 resolved value on attempt 2; re-resolution SHALL NOT occur.
- [ ] 2.8 Add unit tests `backend/tests/test_executor_on_error.py`:
  - `fail_run` default behaviour unchanged;
  - `continue` adds `{"error":{...}}` to context and follows `kind="next"` edge;
  - `branch` with a matching `kind="on_error"` edge follows it; without one, degrades to `fail_run` with the explanatory note in `error`;
  - **terminal status `completed_with_errors` (Decision 12)**: a run with one `on_error="continue"` failure that reaches its end node terminates with `Run.status="completed_with_errors"` AND emits `run_completed_with_errors` with `failed_node_count == 1`;
  - a run with NO `node_failed` events terminates with `Run.status="completed"` AND emits `run_completed` (unchanged from today).
- [ ] 2.9 Smoke-check: `pytest backend/tests/test_executor_retry.py backend/tests/test_executor_on_error.py -v` passes.

## 3. Frontend canvas + inspector + log (Sibling B — `[frontend]`)

- [ ] 3.1 Update the canvas edge renderer (semantic role — the existing component that styles workflow edges) to read `edge.kind` and render `kind="on_error"` with `stroke-dasharray: 6 4` and the error-color stroke from the theme tokens. Hover tooltip `"失败时跳转到 <target.label>"`.
- [ ] 3.2 Update the NodeInspector — add a "错误处理" section per design Decision 9:
  - `重试次数` numeric input (1–10);
  - `重试间隔 (ms)` numeric input (0–60000), disabled when 重试次数 is empty;
  - `失败策略` segmented control with the three options; show the dashed-red-edge hint when `走错误分支` is selected;
  - render a one-line worst-case-wall-time preview `"最长重试时间：N 秒"` whenever `重试次数` is non-empty.
- [ ] 3.3 Update the RunLog (semantic role — the existing component that renders the live event stream) to recognise `node_retry` events and nest them under the parent node's row. Collapsed by default; chevron expands to show each attempt's `error` and `next_attempt_at`. Style: muted grey text with the retry icon.
- [ ] 3.4 Update the RunReplay player to compress `node_retry` event sleep timing to 0 (same rule as `wait` node delays). Re-emit the event to the canvas / log so the visual nesting still appears.
- [ ] 3.5 Update the editor's patch-preview component (the chat-panel-side renderer for `update_node` ops) to also render `retry` / `on_error` changes succinctly (`~ node n4.on_error: fail_run → branch`).
- [ ] 3.5a Update the runs-list page (semantic role) to render `completed_with_errors` as an amber/warning pill distinct from green `completed` and red `failed`. Hovering the pill SHALL show the `failed_node_count` from the `run_completed_with_errors` payload (fetched from the run's last event if not already on the list response).
- [ ] 3.6 Smoke-check: `pnpm build` clean; `tsc --noEmit` clean.

## 4. Verification (parent worker)

- [ ] 4.1 `[verification]` Author a 3-node workflow: `start → flaky_click (selector that fails twice then succeeds) → end`. Set `retry={max_attempts:3, backoff_ms:200}`. Run it. Confirm two `node_retry` events and a `node_completed` with `attempt=3`. Total run time ≈ 600 ms above the action's own time.
- [ ] 4.2 `[verification]` Same flaky node with `retry={max_attempts:1}`. Confirm a single `node_failed` and `run_failed`. No `node_retry` events.
- [ ] 4.3 `[verification]` On-error `continue`: a 4-node workflow `start → failing_click → log_message → end`, where `failing_click` has `on_error="continue"`. Confirm a `node_failed` event AND that `log_message` runs to completion AND that the run terminates `completed_with_errors` (NOT `completed`) with a `run_completed_with_errors` event whose `failed_node_count == 1`. Confirm `context["failing_click"] == {"error":{...}}` is observable in `log_message`'s `node_completed.output` (when chained with `node-context-variables`; otherwise just confirm `log_message` ran). Confirm the runs-list pill renders as the amber/warning variant.
- [ ] 4.4 `[verification]` On-error `branch` happy path: a workflow with `failing_click → cleanup` via a `kind="on_error"` edge. Confirm the cleanup node runs and the run terminates `completed`.
- [ ] 4.5 `[verification]` On-error `branch` degradation: same `failing_click` with `on_error="branch"` but no outgoing `kind="on_error"` edge. Confirm `node_failed.error` ends with the substring `"falling back to fail_run"` AND the run terminates `failed`.
- [ ] 4.6 `[verification]` Abort during retry sleep: kick off a retrying run, hit 停止 between attempts, confirm `run_aborted` is emitted within 100 ms of the click (the inter-attempt sleep is cancelled).
- [ ] 4.7 `[verification]` Replay a past retrying run, confirm the run log shows retries nested correctly AND that the playback wall time is ≪ live wall time.
- [ ] 4.8 `[verification]` Backwards compat: a workflow generated before this change (no `retry`, no `on_error`, no `kind`) runs and replays unchanged.
- [ ] 4.9 `[verification]` Kill all dev processes.

## 5. README

- [ ] 5.1 Update `auto-agent/README.md` — new "错误处理 / Error handling" section: retry policy shape, on-error semantics, edge `kind` convention, worst-case wall-time guidance.

---

## Parallel Implementation Plan

Two sibling workers after the parent lands §1.

### Sibling A — Backend runtime `[backend-runtime]`

**Mission.** Executor retry loop, on-error router, event-type extension, editor / planner prompt updates. All of §2.

**Owns.** `backend/app/executor.py` (refactor + retry + on-error router), `backend/app/services/runs.py` (event-type extension, no behavioural change beyond accepting `node_retry`), `backend/app/agents/editor.py` and `backend/app/agents/planner.py` (system-prompt paragraph), all of `backend/tests/test_executor_retry.py`, `backend/tests/test_executor_on_error.py`.

**Must NOT touch.** Anything under `frontend/`, `backend/app/tools/actions.py` (action signatures unchanged), `backend/app/agents/fuzzy.py` / `extractor.py`. The `Workflow` / `Node` / `Edge` pydantic schemas are touched only via the shared contract in §1 (parent-owned).

**Shared contract deps (§1).** `Node.retry`, `Node.on_error`, `Edge.kind`, `NodeRetryPayload`, event-type union extension.

**Independent verification.** `pytest backend/tests/test_executor_retry.py backend/tests/test_executor_on_error.py` passes; a scripted run against a flaky local fixture asserts the retry / on-error semantics live.

**Estimated tasks.** ~9 (2.1–2.9).

### Sibling B — Frontend `[frontend]`

**Mission.** Canvas dashed-red edge styling, NodeInspector "错误处理" section, RunLog nested retry rows, replay compression. All of §3.

**Owns.** The edge renderer wiring (semantic role; the implementer picks the existing component that owns edge styling), the NodeInspector params area (one new sub-form), the RunLog row renderer (one new event-type case), the RunReplay player (one new event-type case), the chat-panel patch-preview renderer (one extension).

**Must NOT touch.** Backend files, `frontend/src/store.ts` (consumes via existing public API only), `frontend/src/chat/api.ts` (no API change for the chat panel; the editor produces `update_node` patches as before).

**Shared contract deps (§1).** Extended `Node`, `Edge`, `RunEventType` TS types.

**Independent verification.** Against a running Sibling-A backend, set up a retrying workflow via the chat editor, run it, watch the canvas render the dashed edge AND the run log nest the retry rows.

**Estimated tasks.** ~6 (3.1–3.6).

### Rationale

The retry / on-error logic is entirely inside `executor.py`; the canvas / inspector / log changes are entirely inside the frontend. Once the schema additions and the new event-type literal are in the shared contract, the two siblings stop overlapping. Both are small (~80 LOC each on the implementation side, ~150 LOC on tests / styles), making this one of the smaller changes in the roadmap.
