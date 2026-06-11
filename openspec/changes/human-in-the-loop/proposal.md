## depends_on

- `auto-agent-mvp` — workflow schema, executor, `node_started` / `node_completed` event shape.
- `auto-agent-platform` — `Run` lifecycle (`queued | running | completed | failed | aborted`), FIFO queue, `RunEvent` persistence, `/ws/run` socket.
- `node-context-variables` — the approval node's collected inputs become available downstream via `{{nodes.<approval_id>.output.inputs.<field>}}`. This change technically ships without it (the inputs are persisted to the `Run` and emitted as `node_completed.output`), but the operator experience without `{{nodes...}}` references is poor; treating it as a hard dependency for ordering.

No dependency on `triggers-and-scheduling`, `node-error-handling`, `self-healing-selectors`, or `expanded-node-library`. The notifications hook this change emits is consumed by the deferred notifications change (not in this batch).

## Why

Every automation that touches money, sends an email, or modifies a third-party system eventually needs a human "are you sure?" step. Today our workflows are end-to-end autonomous: the planner can generate a check-out flow, but it cannot ask the operator to look at the cart before clicking Pay. The closest workaround is to terminate the workflow before the risky step and tell the user to manually trigger a second workflow — clunky, easy to skip, and indistinguishable in the run log from a "the workflow forgot something" bug.

We add a new node type `approval` that pauses the run mid-flow and surfaces a banner on the workflow detail page. The operator clicks 同意 or 拒绝 (optionally filling in a small input form), the run resumes from that node, and downstream nodes can reference the operator's decision and any collected inputs via the standard `{{nodes...}}` token form.

This is the smallest possible primitive that unlocks the largest class of "human verification" workflows. Multi-approver flows, timeouts, escalation, and reminder notifications are all explicit future work — flagged in design Open Questions and in the Out-of-scope section.

## What Changes

- **Node type**: new `NodeType` literal value `"approval"`. Params shape: `{prompt: str, inputs?: list[{name: str, type: "string"|"number"|"boolean", default?: any, required?: bool}]}`.
- **Executor**: on reaching an `approval` node, the executor SHALL emit `node_awaiting_approval` with the prompt + inputs schema, register a wait on an `asyncio.Event` keyed by `(run_id, node_id)`, then `await event.wait()`. When the event fires the executor reads the persisted decision + inputs and treats them as the node's `output` (which becomes the `node_completed.output` event AND the `context[node_id]` entry consumed by `node-context-variables`).
- **REST**: `POST /api/runs/{id}/approvals/{node_id}` with body `{decision: "approve"|"reject", inputs?: dict}`. Persists the decision to a new `RunApproval` row, then sets the in-process `asyncio.Event`. Returns 200 with the decision echoed. 409 if the approval is already resolved; 404 if the run / node / pending approval does not exist; 410 if the run was aborted or otherwise finalised while the approval was pending.
- **Run status**: a new run status pill `awaiting_approval` is surfaced in the UI but is NOT a new value in the `Run.status` column. Implementation: while the `asyncio.Event` is pending, the underlying `Run.status` stays `"running"` (the queue slot is held); a derived `pending_approval: {node_id, prompt, inputs_schema} | null` field is computed on read by the `runs` router from the latest unresolved `RunApproval` row.
- **Queue interaction**: a run blocked on approval keeps its single-Chromium queue slot. Documented; tradeoff resolved in design (see Decision 4) with future work to optionally release the slot.
- **Approval rejection** terminates the run with a new terminal status `rejected` (added to the existing `Run.status` literal alongside `completed | failed | aborted`). A rejection is NOT the same as a failure: no `node_failed` event, no `run_failed`, just `node_rejected` and `run_rejected`.
- **UI**: when a workflow detail page is open AND its currently-running run has a pending approval, a prominent banner SHALL render at the top of the page with the prompt, the inputs form (if any), and 同意 / 拒绝 buttons. The run-history list shows blocked-on-approval runs with a distinct `等待审批` pill.
- **Notification hook**: when an approval is requested, the executor SHALL call a service-level hook `services.notifications.emit("approval_requested", {run_id, workflow_id, node_id, prompt})`. The hook is a no-op in this change (it just logs); the future notifications change will replace the body to fan-out to email / Slack / webhook subscribers.

## Capabilities

### New Capabilities

- `approval-node`: the `approval` node type, the `node_awaiting_approval` event, the `RunApproval` table, the `POST /api/runs/{id}/approvals/{node_id}` endpoint, the `pending_approval` derived field, the `rejected` terminal status, the UI banner + history pill, the notification hook.

### Modified Capabilities

- `workflow-schema` (from `auto-agent-mvp`): adds `"approval"` to the `NodeType` literal.
- `hybrid-executor` (from `auto-agent-mvp`): adds the await-on-event branch for approval nodes and the rejection path.
- `run-history` (from `auto-agent-platform`): adds `rejected` to the `RunStatus` literal; the event-type literal gains `node_awaiting_approval`, `node_approved`, `node_rejected`, `run_rejected`. `RunSummary` / `RunOut` expose `pending_approval` (computed on read).
- `chat-authoring` (from `auto-agent-platform`): editor system prompt documents the new node type with one example.

## Impact

- **Backend**: new `RunApproval` table (small: `id`, `run_id`, `node_id`, `seq`, `prompt`, `inputs_schema`, `decision`, `decision_inputs`, `requested_at`, `resolved_at`, `resolved_by` reserved-for-future). New router `backend/app/routers/approvals.py`. ~100 LOC of executor changes (the await branch + the rejection terminal handling). New event types persisted via existing `services.runs.record_event`. New service stub `backend/app/services/notifications.py` (one function, currently a `log.info` line).
- **Frontend**: new banner component on the workflow detail page (semantic role only). New history-list pill. New form renderer for the inputs schema. Two new API methods: `apiClient.runs.respondToApproval(run_id, node_id, decision, inputs)` and `apiClient.runs.getPendingApproval(run_id)` (the latter polls when no socket is open).
- **Runtime**: an approval-blocked run holds the Chromium tab open AND holds its FIFO slot. Documented tradeoff; future change can optionally release the slot.
- **Migration**: SQLite `ALTER TABLE run ADD COLUMN status...` is unnecessary — `Run.status` is a free-text column today with a pydantic literal in the schema layer; we just extend the literal. New `run_approval` table is created by `init_db()`'s `create_all` on first boot.
- **Out of scope**: multi-approver workflows (require N-of-M approvals); approval timeouts (auto-reject or auto-approve after Δ minutes) — deferred to a future "approval-timeouts" change that consumes the existing `services.notifications.emit("approval_requested", ...)` hook plus an APScheduler delayed task (depends on `triggers-and-scheduling`); per-approver ACLs; reminder notifications; approval comments / attachments; on-decision side effects beyond resuming the run; per-node `release_slot` opt-out for the queue (this change always HOLDS the slot — a future change MAY add the opt-out without breaking the v1 contract).
