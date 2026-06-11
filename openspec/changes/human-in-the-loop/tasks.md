## 1. Shared contract (parent worker)

- [ ] 1.1 `[shared-contract]` Extend `backend/app/schemas.py`:
  - add `"approval"` to the `NodeType` literal;
  - add `ApprovalInputSpec(BaseModel)` and `ApprovalParams(BaseModel)`;
  - register a per-type params validator so `Node(type="approval", params=...)` parses `params` into `ApprovalParams`.
- [ ] 1.2 `[shared-contract]` Add `RunApproval` SQLModel to `backend/app/db/models.py`:
  - `id: str` PK, `run_id: str` FK + index, `node_id: str`, `seq: int` (monotonic within `run_id`, indexed unique on `(run_id, seq)`);
  - `prompt: str`, `inputs_schema: list[dict]` (`sa_column=Column(JSON)`);
  - `decision: Optional[Literal["approve","reject","lost"]] = None`, `decision_inputs: dict = Field(default_factory=dict, sa_column=Column(JSON))`;
  - `requested_at: datetime`, `resolved_at: Optional[datetime] = None`, `resolved_by: Optional[str] = None` (reserved).
- [ ] 1.3 `[shared-contract]` Extend `backend/app/schemas_api.py`:
  - add `"rejected"` to the `RunStatus` literal;
  - add `"node_awaiting_approval"`, `"node_approved"`, `"node_rejected"`, `"run_rejected"` to the event-type literal;
  - add `PendingApproval(BaseModel)` (`{node_id, prompt, inputs_schema, requested_at}`);
  - add `pending_approval: Optional[PendingApproval] = None` to `RunSummary` and `RunOut`;
  - add `ApprovalDecisionRequest(BaseModel)` (`{decision: Literal["approve","reject"], inputs: dict = Field(default_factory=dict)}`) and `ApprovalDecisionResponse` (echoed decision + resolved_at).
- [ ] 1.4 `[shared-contract]` Mirror TS types in `frontend/src/types-platform.ts`:
  - `RunStatus` includes `"rejected"`;
  - event-type union grows;
  - `PendingApproval` shape;
  - `ApprovalDecisionRequest` shape;
  - `Node.params` for type `"approval"` matches `ApprovalParams` (a discriminated union per node type).
- [ ] 1.5 `[shared-contract]` Add `apiClient.runs.respondToApproval(runId, nodeId, body)` and `apiClient.runs.getPendingApproval(runId)` stubs to `frontend/src/api-platform.ts`.
- [ ] 1.6 `[shared-contract]` Add `backend/app/services/notifications.py` with the locked async `emit(event_name, payload)` no-op stub (`log.info` only) per design Decision 9. Export.
- [ ] 1.7 `[shared-contract]` Smoke-check: `python -c "from app.db.models import RunApproval; from app.schemas import Node; n = Node(id='x', type='approval', label='check', params={'prompt':'ok?'}); print('ok')"` and `cd frontend && npx tsc --noEmit` pass.

## 2. Backend (Sibling A — `[backend]`)

- [ ] 2.1 Author `backend/app/services/approvals.py` — singleton service with:
  - in-memory `_events: dict[str, asyncio.Event]` keyed by approval id;
  - `request(run_id, node_id, prompt, inputs_schema) -> RunApproval` inserts the row and registers a fresh `asyncio.Event`;
  - `resolve(approval_id, decision, inputs) -> RunApproval` validates the inputs against `inputs_schema`, updates the row, sets `resolved_at`, fires the event;
  - `wait(approval_id) -> RunApproval` awaits the event and reloads the row;
  - `pending_for_run(run_id) -> Optional[RunApproval]` returns the latest unresolved row.
- [ ] 2.2 Modify `backend/app/executor.py::run_workflow` — when `node.type == "approval"`:
  - call `approvals_service.request(...)`;
  - emit `node_awaiting_approval` with the row's `prompt` and `inputs_schema`;
  - call `notifications.emit("approval_requested", {run_id, workflow_id, node_id, prompt})`;
  - `await approvals_service.wait(approval.id)` (check abort flag at the await edges);
  - on `decision == "approve"`: set `context[node.id] = {"decision":"approve","inputs":resolved.inputs}`, emit `node_approved` AND `node_completed(output=context[node.id], attempt=1)`, continue traversal;
  - on `decision == "reject"`: emit `node_rejected` with `output={"decision":"reject","inputs":resolved.inputs}`, emit `run_rejected`, transition the run to `status="rejected"`, stop traversal;
  - on `decision == "lost"`: emit `node_failed` AND `run_failed` (this branch is only entered on restart-reaping; see §2.5).
- [ ] 2.3 Author `backend/app/routers/approvals.py` with the resolve endpoint:
  - `POST /api/runs/{run_id}/approvals/{node_id}` body `ApprovalDecisionRequest` → 200 `ApprovalDecisionResponse`;
  - look up the latest unresolved `RunApproval` for `(run_id, node_id)`; 404 if absent; 410 if the parent run is not `running`; 422 if input validation fails;
  - call `approvals_service.resolve(...)`; return echoed decision.
- [ ] 2.4 Modify `backend/app/routers/runs.py` — every list / detail response computes `pending_approval` from `approvals_service.pending_for_run(...)` (or a single `SELECT … LIMIT 1` per run for list, batched via `IN` for the runs-list endpoint).
- [ ] 2.5 Modify `backend/app/main.py::lifespan` — after `init_db()` AND after the credential backfill, run `reap_lost_approvals_on_startup()` which:
  - finds every `RunApproval` row with `decision IS NULL` whose parent `Run.status == "running"`;
  - marks `decision = "lost"`, sets `resolved_at = now()`;
  - transitions each affected `Run` to `status = "failed"`, `finished_at = now()`;
  - appends a `run_failed` `RunEvent` with payload `{"reason":"approval lost across backend restart","approval_id":...}`;
  - logs one `WARNING` line per affected run.
- [ ] 2.6 Modify `backend/app/services/runs.py` — recognise the new terminal `"rejected"` status everywhere it does today's `completed|failed|aborted` switching: scheduler dequeue, abort short-circuit, `RunOut` serialisation, `run_rejected` event handling. Abort during an approval wait still transitions to `"aborted"`, NOT `"rejected"`.
- [ ] 2.7 Add unit tests `backend/tests/test_approvals_service.py`:
  - `request` inserts a pending row;
  - `resolve(approve)` sets the row + fires the event;
  - `resolve(reject)` likewise;
  - `wait` blocks until `resolve` is called from another task;
  - duplicate `resolve` against an already-resolved row raises;
  - `pending_for_run` returns the latest unresolved row.
- [ ] 2.8 Add unit tests `backend/tests/test_approvals_router.py`:
  - happy path approve resumes the run and produces `node_completed` with the inputs in `output.inputs`;
  - reject terminates the run as `rejected` with a `run_rejected` event;
  - duplicate POST returns 409; invalid inputs return 422; non-`running` parent run returns 410.
- [ ] 2.9 Add unit tests `backend/tests/test_lifespan_reap_lost_approvals.py` — pre-seed a pending `RunApproval` + a `running` `Run`, call the reap helper, assert decision=`lost`, run.status=`failed`, `run_failed` event appended.
- [ ] 2.10 Update `backend/app/agents/editor.py` and `backend/app/agents/planner.py` system prompts — append a paragraph describing the `approval` node type with one example.
- [ ] 2.11 Smoke-check: `pytest backend/tests/test_approvals_service.py backend/tests/test_approvals_router.py backend/tests/test_lifespan_reap_lost_approvals.py -v` passes.

## 3. Frontend (Sibling B — `[frontend]`)

- [ ] 3.1 Author `frontend/src/approval/PendingApprovalBanner.tsx` — given the workflow's currently-running run, polls `apiClient.runs.getPendingApproval(runId)` every 2 s (and on socket `node_awaiting_approval` event) for backup. When pending, renders a prominent banner at the top of the detail page with:
  - the prompt text;
  - the inputs form (one field per `ApprovalInputSpec`; required fields marked with an asterisk; default values pre-populated);
  - 同意 / 拒绝 buttons (labels from `approve_label` / `reject_label` if present);
  - elapsed-time text ("已等待 N 分钟").
- [ ] 3.2 Author `frontend/src/approval/ApprovalForm.tsx` — small form helper rendering string / number / boolean inputs. Validation: required fields blocking submit; type coercion on submit (number input → JS number).
- [ ] 3.3 Mount `<PendingApprovalBanner runId={...}/>` at the top of the workflow detail page when its current run is in a pending-approval state. Hidden otherwise.
- [ ] 3.4 Update the runs-list page to render a distinct `等待审批` pill when `pending_approval != null`. The pill links to the parent workflow's detail page (with the run pre-selected).
- [ ] 3.5 Update the runs-list page to render a `已拒绝` pill for the new `rejected` terminal status. Style: neutral / amber (NOT red, which is for `failed`).
- [ ] 3.6 Update the RunLog renderer (semantic role — the live event stream) to render `node_awaiting_approval`, `node_approved`, `node_rejected`, `run_rejected` events with appropriate icons.
- [ ] 3.7 Update the RunReplay player to handle the four new event types (render them, no actual blocking — replay just shows the event in sequence). The wait between `node_awaiting_approval` and the resolving event is compressed to 0 (same rule as `wait` and `node_retry`).
- [ ] 3.8 Update the canvas to render the `approval` node type with a distinct lucide icon (use the same data-node-type approach the canvas already uses for other types; no CSS layout change).
- [ ] 3.9 Smoke-check: `pnpm build` clean; `tsc --noEmit` clean.

## 4. Verification (parent worker)

- [ ] 4.1 `[verification]` Author a 4-node workflow: `start → navigate(test page) → approval(prompt="确认继续？", inputs=[{name:"note", type:"string", required:true}]) → end`. Run it; confirm a `node_awaiting_approval` event appears AND that the run sits in `running` state with `pending_approval != null` for at least 30 s.
- [ ] 4.2 `[verification]` UI: open the detail page during the wait; confirm the banner renders, the inputs form requires the `note` field, the elapsed-time text increments.
- [ ] 4.3 `[verification]` Submit approve with `note="ok"`; confirm `node_approved`, `node_completed(output={decision:"approve", inputs:{note:"ok"}})`, and the workflow runs to completion.
- [ ] 4.4 `[verification]` Re-run; submit reject; confirm `node_rejected`, `run_rejected`, run terminates with `status="rejected"` AND that the runs-list shows the `已拒绝` pill.
- [ ] 4.5 `[verification]` Token resolution (depends on `node-context-variables`): add a `log` node after the approval that reads `{{nodes.<approval_id>.output.inputs.note}}`; confirm the note text is interpolated correctly when chained with the variables change.
- [ ] 4.6 `[verification]` Restart resilience: start an approval-blocked run, kill the backend with `Ctrl-C`, restart, confirm one `WARNING` log line per reaped approval AND that the affected run is now `failed` with the documented `run_failed` event.
- [ ] 4.7 `[verification]` Abort during approval: start an approval-blocked run, click 停止 (existing button), confirm the run transitions to `aborted` (NOT `rejected`) AND that subsequent POSTs against the approval endpoint return 410.
- [ ] 4.8 `[verification]` Invalid inputs: POST `{decision:"approve", inputs:{}}` against an approval whose schema requires `note`; confirm HTTP 422 AND that the approval row stays `decision IS NULL` AND that a corrected POST then resolves it.
- [ ] 4.9 `[verification]` Notifications hook: confirm a `log.info` line `notifications.emit approval_requested ...` appears whenever an approval is requested.
- [ ] 4.10 `[verification]` Kill all dev processes.

## 5. README

- [ ] 5.1 Update `auto-agent/README.md` — new "审批 / Approvals" section: node params shape, banner UX, queue-slot-held caveat, restart-loss caveat.

---

## Parallel Implementation Plan

Two sibling workers after the parent lands §1.

### Sibling A — Backend `[backend]`

**Mission.** `RunApproval` table, approvals service, executor branch, resolve endpoint, lifespan reaper, `rejected` status plumbing, editor / planner prompt updates. All of §2.

**Owns.** `backend/app/services/approvals.py` (new), `backend/app/routers/approvals.py` (new), `backend/app/services/notifications.py` (new no-op stub per §1.6 — parent-owned stub, sibling owns any internal helpers), `backend/app/executor.py` (approval branch), `backend/app/services/runs.py` (rejected status + pending_approval computation), `backend/app/routers/runs.py` (pending_approval on list/detail responses), `backend/app/main.py` (lifespan reaper wiring), `backend/app/agents/editor.py` and `planner.py` (system-prompt paragraph), all of `backend/tests/test_approvals_*.py`, `backend/tests/test_lifespan_reap_lost_approvals.py`.

**Must NOT touch.** Anything under `frontend/`, `backend/app/tools/actions.py` (approval is not a tool — the executor handles it inline), other agents (`fuzzy.py`, `extractor.py`).

**Shared contract deps (§1).** `RunApproval` model, `ApprovalParams`, `RunStatus` extension, event-type literal extension, `PendingApproval`, `ApprovalDecisionRequest`, notifications stub.

**Independent verification.** `pytest backend/tests/test_approvals_*.py backend/tests/test_lifespan_reap_lost_approvals.py` passes; a scripted run drives a workflow with one approval node through approve, then reject, then restart-reap; finally asserts HTTP 410 on a post-finalisation POST.

**Estimated tasks.** ~11 (2.1–2.11).

### Sibling B — Frontend `[frontend]`

**Mission.** Banner, form, history pills, log / replay rendering for new events, canvas icon. All of §3.

**Owns.** `frontend/src/approval/PendingApprovalBanner.tsx` (new), `frontend/src/approval/ApprovalForm.tsx` (new), wiring edits to the workflow detail page (mount the banner), runs-list page (two new pills), RunLog / RunReplay (new event-type cases), canvas (one new node-type icon).

**Must NOT touch.** Backend files, `frontend/src/store.ts` (consumes via existing public API only), `frontend/src/chat/`.

**Shared contract deps (§1).** `PendingApproval`, `ApprovalDecisionRequest`, `RunStatus` extension, event-type extension, `apiClient.runs.respondToApproval / getPendingApproval` stubs.

**Independent verification.** Against a running Sibling-A backend, set up an approval workflow via the chat editor, run it, confirm the banner appears, submit both approve and reject paths, see the `等待审批` and `已拒绝` pills.

**Estimated tasks.** ~9 (3.1–3.9).

### Rationale

The approval primitive cleanly splits into a backend suspension/resume mechanic and a frontend banner/form. The contract between them is the `RunApproval` row shape + the `pending_approval` derived field + the two new API endpoints — all parent-owned in §1. Each sibling is small (~150–250 LOC of implementation, ~150 of tests). The notifications service stub is parent-owned so neither sibling has to coordinate on its signature with the deferred notifications change.
