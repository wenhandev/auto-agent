## Description

A new node type `approval` pauses a run mid-flow and waits for a human decision. The decision is `"approve"` or `"reject"`, optionally accompanied by a small inputs payload validated against a per-node schema. On approve the run resumes from the approval node and continues traversal; on reject the run terminates with a new `Run.status = "rejected"` terminal value. The collected decision + inputs become the approval node's `output`, available to downstream nodes through the standard `{{nodes.<approval_id>.output.<path>}}` interpolation.

Suspension is implemented as an in-process `asyncio.Event` keyed by `(run_id, node_id)`. Pending approvals survive socket drops but NOT backend restarts: a startup hook marks lost pending approvals and fails the affected runs with a clear reason.

The notification hook `services.notifications.emit("approval_requested", payload)` is wired but is a no-op in this change; the deferred notifications change will replace its body.

## User stories

- **As a workflow author**, I want to insert a "please confirm" step before risky actions (sending an email, clicking Pay, deleting records) so the workflow cannot finish autonomously past that step.
- **As an operator**, I want a clear banner at the top of the workflow detail page when a run is waiting on me, so I do not miss it.
- **As an operator**, I want to fill in small structured inputs at approval time (e.g. an order quantity or a note) and have those inputs land in downstream nodes' params.
- **As an operator**, I want a rejected run to be visually distinct from a failed run in the run history, so I can tell deliberate stops from crashes.
- **As an operator**, I want a backend restart during a pending approval to fail the run with an obvious reason rather than leave the run in a confused state.

## Functional requirements

### Requirement: `approval` Node Type And Params Shape

The `NodeType` literal SHALL include `"approval"`. A node with `type="approval"` SHALL validate its `params` against `ApprovalParams`:

```python
class ApprovalInputSpec(BaseModel):
    name: str
    type: Literal["string", "number", "boolean"]
    default: Optional[Any] = None
    required: bool = False
    label: Optional[str] = None

class ApprovalParams(BaseModel):
    prompt: str
    inputs: list[ApprovalInputSpec] = Field(default_factory=list)
    approve_label: str = "同意"
    reject_label: str = "拒绝"
```

#### Scenario: Minimal valid approval node

- **WHEN** the workflow contains `{"id":"n3", "type":"approval", "label":"confirm", "params":{"prompt":"确认继续？"}}`
- **THEN** pydantic validation SHALL succeed.

#### Scenario: Missing prompt rejected

- **WHEN** an approval node's `params` lacks `prompt`
- **THEN** pydantic validation SHALL fail before the workflow is saved.

### Requirement: Executor Suspends On Approval Node

When the executor reaches an `approval` node it SHALL:

1. Persist a `RunApproval` row via `services.approvals.request(...)`.
2. Emit a `node_awaiting_approval` event whose payload contains `prompt: str` and `inputs_schema: list[dict]` (the JSON form of `inputs`).
3. Call `services.notifications.emit("approval_requested", {run_id, workflow_id, node_id, prompt})`.
4. `await services.approvals.wait(approval_id)`.
5. Resume per the resolved decision (see Requirement "Approve Resumes Traversal" / "Reject Terminates Run As Rejected").

The abort flag SHALL be checked at the await edges; an abort during the wait SHALL terminate the run with `status="aborted"` (NOT `"rejected"`) and SHALL emit `run_aborted`.

#### Scenario: Pending approval observable via REST

- **WHEN** the executor has just emitted `node_awaiting_approval` for run `R` and node `n3`
- **THEN** `GET /api/runs/{R}` SHALL return `pending_approval = {node_id:"n3", prompt:"...", inputs_schema:[...], requested_at:"..."}` until the decision is resolved.

#### Scenario: Abort during approval

- **WHEN** an approval is pending and the operator posts `{"type":"abort"}` over the run socket
- **THEN** the run SHALL terminate with `status="aborted"`, the `RunApproval` row SHALL be marked `decision="lost"`, AND a subsequent POST to the resolve endpoint SHALL return HTTP 410.

### Requirement: Resolve Endpoint

`POST /api/runs/{run_id}/approvals/{node_id}` with body `{"decision":"approve"|"reject", "inputs": dict}` SHALL resolve the latest unresolved `RunApproval` for the `(run_id, node_id)` pair. The endpoint SHALL:

- return HTTP 404 if no pending approval exists for the pair;
- return HTTP 410 if the parent run is not `"running"`;
- return HTTP 409 if the approval was already resolved (race against another tab);
- on `decision="approve"`, validate `inputs` against the row's `inputs_schema` (required fields present, type match); return HTTP 422 with field-level errors on validation failure;
- on `decision="reject"`, skip inputs validation and persist `inputs` verbatim (empty dict by convention);
- on success, persist `decision`, `decision_inputs`, `resolved_at = now()`, fire the in-process `asyncio.Event`, AND return HTTP 200 with the echoed decision and timestamp.

#### Scenario: Approve happy path

- **WHEN** the operator POSTs `{"decision":"approve","inputs":{"note":"ok"}}` for a pending approval whose schema requires `note: string`
- **THEN** the response SHALL be HTTP 200 AND the executor SHALL resume within ~100 ms AND a subsequent `GET /api/runs/{run_id}` SHALL show `pending_approval = null`.

#### Scenario: Reject happy path

- **WHEN** the operator POSTs `{"decision":"reject"}` (omitted inputs)
- **THEN** the response SHALL be HTTP 200 AND the run SHALL terminate with `status="rejected"` AND a `node_rejected` event AND a `run_rejected` event SHALL be persisted.

#### Scenario: Inputs validation failure

- **WHEN** the operator POSTs `{"decision":"approve","inputs":{}}` against a schema requiring `note`
- **THEN** the response SHALL be HTTP 422 with a body identifying `note` as the missing required field AND the `RunApproval` row SHALL stay `decision IS NULL`.

#### Scenario: Stale UI race

- **WHEN** two tabs both POST a decision for the same approval and the first succeeds
- **THEN** the second POST SHALL return HTTP 409 with `{"detail":"approval already resolved"}` AND SHALL NOT modify the row.

### Requirement: Approve Resumes Traversal

On resolution with `decision="approve"`:

- the executor SHALL set `context[node.id] = {"decision":"approve","inputs":<resolved.inputs>}`;
- the executor SHALL emit `node_approved` (informational; payload `{decision, inputs}`) followed by `node_completed` whose `output = context[node.id]` and `attempt = 1`;
- traversal SHALL continue along the next-edge as for any other completed node.

#### Scenario: Downstream interpolation

- **WHEN** the approval node `n3` resolves approve with `inputs={"note":"ok"}` AND a downstream node has `params = {"comment": "{{nodes.n3.output.inputs.note}}"}`
- **THEN** (when chained with `node-context-variables`) the downstream node's resolved params SHALL contain `comment = "ok"`.

### Requirement: Reject Terminates Run As Rejected

On resolution with `decision="reject"`:

- the executor SHALL emit `node_rejected` with `output={"decision":"reject","inputs":<resolved.inputs>}`;
- the executor SHALL transition the parent run to `status="rejected"`, set `finished_at = now()`, and emit `run_rejected`;
- the scheduler SHALL release the queue slot exactly as it does for other terminal statuses;
- the run-list response SHALL render the new `已拒绝` pill (NOT the red `失败` pill).

#### Scenario: Reject does not bubble through on_error

- **WHEN** an approval node has `on_error="branch"` (per `node-error-handling`) AND is rejected
- **THEN** rejection SHALL terminate the run as `rejected` AND SHALL NOT follow the `kind="on_error"` edge (rejection is a deliberate terminal decision, not an error).

### Requirement: Pending Approval Derived On Read

`Run.status` SHALL stay `"running"` while an approval is pending. `RunSummary` and `RunOut` SHALL include a derived `pending_approval: PendingApproval | null` field computed by querying the latest unresolved `RunApproval` for the run id (single `SELECT … LIMIT 1`; batched via `IN` for the runs-list endpoint).

#### Scenario: No DB literal extension for awaiting_approval

- **WHEN** an approval is pending
- **THEN** `SELECT status FROM run WHERE id=?` SHALL return `"running"` AND the UI pill `等待审批` SHALL be driven solely by `pending_approval != null` on the API response.

### Requirement: Queue Slot Held During Approval Wait

A run blocked on approval SHALL retain its queue slot. The scheduler SHALL NOT promote another queued run for the same workflow until the approval is resolved (or the run is aborted). This is documented as a tradeoff (see proposal / design); a future change MAY add a per-node `release_slot: bool` field that closes the Chromium tab and re-queues the run.

#### Scenario: Other workflows blocked

- **WHEN** workflow A has a run pending approval AND workflow B has a queued run AND no other run is running
- **THEN** workflow B's run SHALL stay `queued` for as long as workflow A's approval is pending (per-workflow FIFO continues; cross-workflow blocking is governed by the single-Chromium global lock).

### Requirement: Restart Reaping Of Pending Approvals

On every backend startup AFTER `init_db()`, the lifespan hook `reap_lost_approvals_on_startup()` SHALL find every `RunApproval` with `decision IS NULL` whose parent `Run.status = "running"`, mark each `decision = "lost"`, transition the affected runs to `status="failed"` with `finished_at = now()`, append a `run_failed` `RunEvent` with payload `{"reason":"approval lost across backend restart","approval_id":...}`, and log one `WARNING` line per affected run.

#### Scenario: Approval lost across restart

- **WHEN** a run is pending approval, the backend is `Ctrl-C`'d, then restarted
- **THEN** the lifespan SHALL terminate that run as `failed` with the documented reason AND a subsequent POST to the resolve endpoint SHALL return HTTP 410.

### Requirement: New Event Types Persisted

The event-type literal SHALL grow by four entries: `node_awaiting_approval`, `node_approved`, `node_rejected`, `run_rejected`. Each SHALL be persisted via `services.runs.record_event(...)` in the same shape and ordering as existing events. Replay SHALL handle them (rendering them on the timeline; compressing the inter-event wait between `node_awaiting_approval` and the resolving event to zero, per the existing replay timing rule for `wait` and `node_retry`).

#### Scenario: Replay renders the approval

- **WHEN** a past run had a successful approval at `n3`
- **THEN** the replay timeline SHALL render `node_awaiting_approval(n3)` and `node_approved(n3)` and `node_completed(n3)` in order, with zero wall-time gap between them.

### Requirement: Notifications Hook Signature Locked

`services.notifications.emit(event_name: str, payload: dict) -> None` SHALL exist as an async function. In this change the body SHALL be a single `log.info` call. The event name `"approval_requested"` and payload shape `{run_id, workflow_id, node_id, prompt}` SHALL be documented and stable; the future notifications change SHALL be able to replace the body without re-touching the executor.

#### Scenario: Hook fires on approval request

- **WHEN** the executor reaches an approval node
- **THEN** a `log.info` line containing `"notifications.emit approval_requested"` SHALL be present in the backend log AND SHALL include the run id and node id.

### Requirement: UI Banner On The Workflow Detail Page

The workflow detail page SHALL render a prominent banner when its currently-running run has `pending_approval != null`. The banner SHALL show the prompt, the inputs form (per `inputs_schema`), the 同意 / 拒绝 buttons, and an elapsed-time text. Submitting the form SHALL call the resolve endpoint and SHALL surface 4xx errors inline without losing the user's input. The banner SHALL also appear when the operator navigates to the page after the approval was already requested (state is fetched on mount, not only via the socket).

#### Scenario: Banner appears on socket event

- **WHEN** the detail page is open with the run socket connected AND a `node_awaiting_approval` event arrives
- **THEN** the banner SHALL render within one frame.

#### Scenario: Banner appears on mount

- **WHEN** the operator navigates to a detail page whose current run is already pending approval
- **THEN** the banner SHALL render after the `/api/runs/{id}` fetch completes, without requiring a socket event.

## API contract

| Method | Path | Request | Response | Notes |
| --- | --- | --- | --- | --- |
| `POST` | `/api/runs/{run_id}/approvals/{node_id}` | `ApprovalDecisionRequest` | `ApprovalDecisionResponse` | 404 / 410 / 409 / 422 per Requirements |

`ApprovalDecisionRequest`:

```json
{
  "decision": "approve" | "reject",
  "inputs": { "<name>": <value>, ... }
}
```

`ApprovalDecisionResponse`:

```json
{
  "node_id": "n3",
  "decision": "approve",
  "inputs": { "note": "ok" },
  "resolved_at": "2026-..."
}
```

`PendingApproval` (returned inside `RunSummary` / `RunOut`):

```json
{
  "node_id": "n3",
  "prompt": "确认继续？",
  "inputs_schema": [
    {"name":"note","type":"string","required":true}
  ],
  "requested_at": "2026-..."
}
```

`RunStatus` extension: `queued | running | completed | failed | aborted | rejected`.

Event-type extension: adds `node_awaiting_approval | node_approved | node_rejected | run_rejected`.

## Data model

```python
class RunApproval(SQLModel, table=True):
    __tablename__ = "run_approval"
    id: str = Field(primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    node_id: str
    seq: int  # monotonic within run_id
    prompt: str
    inputs_schema: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    decision: Optional[Literal["approve","reject","lost"]] = None
    decision_inputs: dict = Field(default_factory=dict, sa_column=Column(JSON))
    requested_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None  # reserved for future multi-user work
    __table_args__ = (UniqueConstraint("run_id", "seq"),)
```

The approval service implementation surface:

```python
# backend/app/services/approvals.py
def request(run_id, node_id, prompt, inputs_schema) -> RunApproval: ...
async def wait(approval_id) -> RunApproval: ...
def resolve(approval_id, decision, inputs) -> RunApproval: ...
def pending_for_run(run_id) -> Optional[RunApproval]: ...
```

## Out of Scope

- Multi-approver workflows (require N-of-M approvals).
- Approval timeouts (auto-reject or auto-approve after Δ minutes). Deferred to a future "approval-timeouts" change that consumes the `services.notifications.emit("approval_requested", ...)` hook plus an APScheduler delayed task (depends on `triggers-and-scheduling`).
- Per-approver ACLs and audit trails (`resolved_by` is reserved but unused).
- Comments / attachments on the decision.
- Releasing the queue slot during the wait (future per-node `release_slot` field).
- Resuming a run after a backend restart with an approval pending (Playwright state cannot be restored).
- Notifications fan-out (deferred to the notifications change; this change wires the hook only).
- A separate `awaiting_approval` value in the `Run.status` column.
