## 1. Shared contract (parent worker)

- [ ] 1.1 `[shared-contract]` Extend `backend/app/schemas.py`:
  - add eight literals to `NodeType`: `"http_request"`, `"read_file"`, `"write_file"`, `"send_email"`, `"parse_json"`, `"parse_csv"`, `"foreach"`, `"subworkflow"`;
  - add per-type params models: `HttpRequestParams`, `ReadFileParams`, `WriteFileParams`, `SendEmailParams`, `ParseJsonParams`, `ParseCsvParams`, `ForeachParams`, `SubworkflowParams`;
  - extend `ConditionParams` with optional `predicate: ConditionPredicate | None`; introduce `ConditionPredicate` with the operator literal listed in design Decision 8;
  - register all per-type params models in the discriminator so `Node.params` deserialises correctly per `type`.
- [ ] 1.2 `[shared-contract]` Extend `backend/app/db/models.py::Run`:
  - add `parent_run_id: Optional[str] = Field(default=None, foreign_key="run.id", index=True)`.
- [ ] 1.3 `[shared-contract]` Author `backend/app/db/migrations.py::add_parent_run_id_on_first_run()` — `ALTER TABLE run ADD COLUMN parent_run_id TEXT NULL` (no-op if the column exists, detected via `PRAGMA table_info(run)`); writes marker `backend/.parent_run_id_added`. Wire into `lifespan` after `init_db()` and the other backfills.
- [ ] 1.4 `[shared-contract]` Author `backend/app/tools/sandbox.py` — `WORKSPACE_DIR = (Path("backend/data/workflow_files")).resolve()`, `workflow_dir(workflow_id) -> Path` (lazy-creates the per-workflow subdir per design Decision 2), `resolve_sandbox_path(user_path, *, workflow_id) -> Path`, `SandboxViolation(Exception)`. Lifespan helper creates the top-level `WORKSPACE_DIR` if missing; per-workflow subdirs are created lazily on first file-action use.
- [ ] 1.5 `[shared-contract]` Extend `backend/app/schemas_api.py`:
  - event-type literal grows by four: `"foreach_iteration_started"`, `"foreach_iteration_completed"`, `"subworkflow_started"`, `"subworkflow_completed"`;
  - per-event payload models;
  - `RunOut` / `RunListItem` include `parent_run_id: Optional[str]`;
  - `RunOut` includes `child_runs: list[RunSummary]`;
  - `GET /api/runs` accepts `?include_children: bool = False`.
- [ ] 1.6 `[shared-contract]` Mirror TS types in `frontend/src/types.ts` (new `NodeType` literals + per-type params models on `Node.params`) and `frontend/src/types-platform.ts` (new event-type literals, `RunOut.child_runs`, `parent_run_id`).
- [ ] 1.7 `[shared-contract]` Add `httpx` to `backend/pyproject.toml` (pin a current version). Append `backend/data/workflow_files/`, `.parent_run_id_added` to `.gitignore`.
- [ ] 1.8 `[shared-contract]` Smoke-check: `python -c "from app.schemas import Node, NodeType, HttpRequestParams, ForeachParams; n = Node(id='x', type='http_request', label='get', params={'method':'GET','url':'https://x'}); assert isinstance(n.params, HttpRequestParams); print('ok')"` and `cd frontend && npx tsc --noEmit` pass.

## 2. Backend non-browser nodes (Sibling A — `[backend-nodes]`)

- [ ] 2.1 Add `app/tools/actions_http.py::http_request(params: HttpRequestParams) -> dict` — uses `httpx.AsyncClient` with the configured timeout; populates `output = {status, headers, json, text, elapsed_ms}` per design Decision 3; truncates `text` at 1 MB.
- [ ] 2.2 Add `app/tools/actions_files.py::read_file(params, *, workflow_id) -> dict` and `write_file(params, *, workflow_id) -> dict`:
  - both call `sandbox.resolve_sandbox_path(path, workflow_id=workflow_id)` first; if `workflow_id is None` (ephemeral `/ws/run` path), raise `SandboxViolation("file actions require a persisted workflow")`;
  - `read_file.output = {contents: str, byte_count: int, path: str}` (where `path` is the workflow-relative path the user provided, not the absolute resolved path);
  - `write_file.output = {path: str, byte_count: int}`;
  - `read_file` enforces `max_bytes`; `write_file` creates parent dirs WITHIN the per-workflow sandbox if missing.
- [ ] 2.3 Add `app/tools/actions_email.py::send_email(params, session, *, workflow_id) -> dict`:
  - looks up the credential by name (`smtp_credential`); the credential fields `{host, port, username, password, use_tls}` are loaded via the existing credential resolver (so per-workflow link enforcement applies);
  - sends via `aiosmtplib` (add as a dependency in §1.7);
  - attachments resolved via `sandbox.resolve_sandbox_path(att, workflow_id=workflow_id)` so attachments share the per-workflow sandbox AND fail with `SandboxViolation` when `workflow_id is None`;
  - returns `{message_id, accepted, rejected}`.
- [ ] 2.4 Add `app/tools/actions_parse.py::parse_json(params) -> dict` and `parse_csv(params) -> dict`:
  - `parse_json.output = {parsed: Any}`;
  - `parse_csv.output = {rows: list[dict|list], header: list[str]|null}`;
  - both raise `ValueError` on malformed input (caught by the executor as `node_failed`).
- [ ] 2.5 Wire the five new action functions into the executor's dispatch table. The dispatch site SHALL pass `workflow_id` (the parent run's `Run.workflow_id`, or `None` for the legacy ephemeral path) into `read_file`, `write_file`, and `send_email`. HTTP / parse nodes do NOT receive `workflow_id` because they do not touch the sandbox.
- [ ] 2.6 Add unit tests:
  - `backend/tests/test_actions_http.py` — happy path GET against an `httpx.MockTransport`, 4xx returns completion (not failure), network error raises;
  - `backend/tests/test_actions_files.py` — happy read / write within a per-workflow sandbox, `..` rejected, absolute path rejected, `max_bytes` enforced, `workflow_id=None` raises `SandboxViolation("file actions require a persisted workflow")`, two workflows with the same relative filename (`t.txt`) write to and read from DIFFERENT files (no cross-workflow leakage), per-workflow dir is lazily created on first write;
  - `backend/tests/test_actions_email.py` — credentials resolved correctly, attachments sandboxed per-workflow, attachment outside per-workflow dir rejected, `aiosmtplib` mocked;
  - `backend/tests/test_actions_parse.py` — JSON parse round-trip, CSV with / without header, malformed input raises.
- [ ] 2.7 Smoke-check: `pytest backend/tests/test_actions_http.py backend/tests/test_actions_files.py backend/tests/test_actions_email.py backend/tests/test_actions_parse.py -v` passes.

## 3. Backend composite flow nodes (Sibling B — `[backend-flow]`)

- [ ] 3.1 Add `app/tools/actions_foreach.py::foreach(params, context, session, *, emit) -> dict`:
  - iterates `params.items` (resolved already by the variable-interpolation pass);
  - per item: builds a child `context` containing `{item, index}` exposed under `_iter` (so tokens read `{{nodes.<foreach_id>.output.item}}` resolved at the parent level via a small remapping shim — see design Decision 6);
  - runs `params.body_workflow` via a recursive call into the executor's `run_workflow` with the child context;
  - emits `foreach_iteration_started(index)` and `foreach_iteration_completed(index, output)` per iteration;
  - respects `max_iterations` cap;
  - on iteration failure, consults the foreach node's `on_error` per `node-error-handling` (if installed) OR falls back to today's "fail_run" default;
  - returns `{item_count, succeeded, failed, results}`.
- [ ] 3.2 Add `app/services/sub_runs.py::run_subworkflow(parent_run_id, workflow_id, version_id, input) -> SubworkflowResult`:
  - creates a `Run` row with `parent_run_id` set;
  - inserts an `_input` synthetic context entry (so `{{nodes._input.output.<key>}}` resolves in the child);
  - recursively dispatches into the executor's `run_workflow`;
  - returns `{child_run_id, status, final_output}`;
  - enforces a recursion-depth cap (5) — checked via a counter on the current asyncio task using `contextvars`.
- [ ] 3.3 Add `app/tools/actions_subworkflow.py::subworkflow(params, ...) -> dict` thin wrapper that calls `sub_runs.run_subworkflow(...)` and emits the two new events `subworkflow_started` and `subworkflow_completed`.
- [ ] 3.4 Extend `app/executor.py::condition` evaluator with the typed predicate per design Decision 8:
  - when `params.predicate` is present, evaluate via a small typed evaluator (no `eval`);
  - emit `condition_evaluated` payload (within the existing `node_completed.output`) with `{predicate, result}`;
  - when `params.predicate` is absent, fall back to today's behaviour (`when=="true"` edge).
- [ ] 3.5 Wire the three new flow node actions into the executor dispatch table. Update workflow validation to reject:
  - nested `foreach` inside another `foreach`'s `body_workflow`;
  - `subworkflow.workflow_id` referencing the workflow itself at the same `version_id` (self-recursion at the same version);
  - `subworkflow` recursion depth > 5 at runtime.
- [ ] 3.6 Modify `app/routers/runs.py`:
  - `GET /api/runs` filters `parent_run_id IS NULL` by default; `?include_children=true` returns the unfiltered list;
  - `GET /api/runs/{id}` populates `child_runs` from `SELECT … WHERE parent_run_id = id`.
- [ ] 3.6a Modify `app/routers/workflows.py::delete_workflow` — after the cascade deletes (versions, sessions, runs, triggers, credential links), best-effort `shutil.rmtree(sandbox.workflow_dir(id), ignore_errors=True)` to remove the per-workflow sandbox dir. Failures SHALL be logged at `WARNING` but SHALL NOT block the delete response.
- [ ] 3.7 Add unit tests:
  - `backend/tests/test_actions_foreach.py` — iterates a list of 3, each iteration completes; `max_iterations` rejected beyond cap; on-error continue skips failing iteration;
  - `backend/tests/test_actions_subworkflow.py` — parent + child run linkage, `final_output` captured, recursion-depth cap fires;
  - `backend/tests/test_condition_predicate.py` — each operator returns the expected bool; missing left-side fails loudly; backward-compat (no predicate, no expr) falls back to `when=="true"`.
- [ ] 3.8 Smoke-check: `pytest backend/tests/test_actions_foreach.py backend/tests/test_actions_subworkflow.py backend/tests/test_condition_predicate.py -v` passes.

## 4. Backend agent prompts (Sibling A continued — `[backend-nodes]`)

- [ ] 4.1 Modify `backend/app/agents/editor.py` system prompt — append the per-type catalogue from design Decision 9 with one example per new type.
- [ ] 4.2 Modify `backend/app/agents/planner.py` system prompt — append the same catalogue.
- [ ] 4.3 Smoke-check: `pytest backend/tests/test_editor_prompt.py` (extended from a prior change if present, otherwise a new tiny regression test) asserts the new substrings are present.

## 5. Frontend (Sibling C — `[frontend]`)

- [ ] 5.1 Add per-type params forms inside the NodeInspector (semantic role — the existing inspector that renders per-type params controls):
  - `http_request`: method dropdown, URL text, headers key-value editor, body editor with `body_kind` dropdown, timeout numeric;
  - `read_file`: path text, encoding text, max_bytes numeric;
  - `write_file`: path text, contents textarea, encoding text;
  - `send_email`: smtp_credential picker (lists linked credentials with `kind` in `{smtp, other}`), to / cc / bcc multi-text, subject text, body textarea + body_kind dropdown, attachments multi-text;
  - `parse_json`: single `input` text (typically a token);
  - `parse_csv`: input text, has_header switch, delimiter text;
  - `foreach`: items text (typically a token), nested workflow editor (re-uses the existing canvas component to render `body_workflow`; cap reminder under the field), max_iterations numeric;
  - `subworkflow`: workflow picker (lists existing workflows), version picker (defaults to current), input key-value editor;
  - `condition`: existing default-true UI gains a `predicate` sub-form (left text, op dropdown, right text) — collapsed by default if the legacy node has no predicate.
- [ ] 5.2 Update the canvas icon map (semantic role — the existing per-node-type icon assignment on the GlowNode renderer):
  - `http_request → Globe`, `read_file → FileText`, `write_file → Save`, `send_email → Mail`, `parse_json → Braces`, `parse_csv → Table`, `foreach → Repeat`, `subworkflow → Workflow`.
- [ ] 5.3 Update the runs-list page (semantic role) to:
  - hide child runs by default (`parent_run_id != null` rows);
  - add a "显示子运行" toggle that flips `?include_children=true`;
  - paginate at 50 rows per page.
- [ ] 5.4 Update the run-detail page (semantic role) to render the `child_runs` list as a nested table when present, with one row per child workflow + status + duration + a deep-link to the child's detail page.
- [ ] 5.5 Update the RunLog renderer to handle the four new event types (`foreach_iteration_*`, `subworkflow_*`):
  - foreach iteration rows nested under the parent foreach row;
  - subworkflow rows link to the child run.
- [ ] 5.6 Update the RunReplay player to handle the four new event types (render only; no real waiting).
- [ ] 5.7 Update the chat-panel patch-preview component to render summaries for the new node types (`+ http_request "GET /orders"`, `+ foreach over {{nodes.parse.output.rows}}`).
- [ ] 5.8 Smoke-check: `pnpm build` clean; `tsc --noEmit` clean.

## 6. Verification (parent worker)

- [ ] 6.1 `[verification]` HTTP node: workflow `start → http_request(GET https://httpbin.org/json) → end`. Run; confirm `http_request.output.status == 200` and `output.json` is a dict.
- [ ] 6.2 `[verification]` File nodes: workflow A: `start → write_file(path="t.txt", contents="hello-A") → read_file(path="t.txt") → end`. Run; confirm round-trip AND that `backend/data/workflow_files/<A_id>/t.txt` exists with the expected contents. Sandbox escape: edit the `write_file` to `path="../escape.txt"` and confirm `node_failed` with `SandboxViolation`. **Per-workflow isolation**: create workflow B that does `read_file(path="t.txt")` — confirm it fails with a `FileNotFoundError` (NOT `hello-A`), proving the two workflows have isolated sandboxes. Cross-workflow sharing requires explicit `subworkflow` use.
- [ ] 6.2a `[verification]` Workflow delete cascades sandbox: delete workflow A via `DELETE /api/workflows/<A_id>`; confirm `backend/data/workflow_files/<A_id>/` no longer exists OR (if `shutil.rmtree` failed for a benign reason) a `WARNING` log line was emitted explaining the failure AND the API still returned 200.
- [ ] 6.3 `[verification]` Email node: with a configured SMTP credential, workflow sends a one-line message to a known inbox; confirm `accepted` contains the recipient.
- [ ] 6.4 `[verification]` Parse nodes: `read_file → parse_json` and `read_file → parse_csv` against fixture files; confirm output shapes match the spec.
- [ ] 6.5 `[verification]` Foreach: a 4-step workflow that reads a fixture CSV, parses it, foreaches over rows, each iteration logs the row. Confirm `foreach.output.item_count` matches the row count AND that `foreach_iteration_completed` events fire per item. Hit the iteration cap by setting `max_iterations=2` on a 4-row input AND confirm the run fails with a clear cap-exceeded error.
- [ ] 6.6 `[verification]` Subworkflow: workflow A (the parent) has a single `subworkflow(workflow_id=B)` node; workflow B is a 3-node `extract → log` chain. Run A; confirm a child `Run` row with `parent_run_id=<A's run id>` exists AND that `subworkflow.output.final_output` matches B's last node output. Visit A's detail page and confirm the child run is listed.
- [ ] 6.7 `[verification]` Subworkflow recursion cap: workflow C subworkflows itself; confirm `node_failed` with the recursion-depth message AND that the cap activates at depth 5.
- [ ] 6.8 `[verification]` Condition predicate: workflow with `http_request → condition(left="{{nodes.http.output.status}}", op=">=", right=400)` and two outgoing edges (`when="true"` to error branch, `when="false"` to happy path). Use `httpbin.org/status/500` for failure; confirm the error branch is followed. Switch to `httpbin.org/status/200` and confirm the happy path.
- [ ] 6.9 `[verification]` Backwards compat: a workflow generated before this change runs unchanged AND every existing condition-node (without `predicate`) keeps following `when=="true"`.
- [ ] 6.10 `[verification]` Editor catalogue: open the chat panel, ask "添加一个 HTTP 节点查询 https://api.example.com 然后用 foreach 处理结果"; confirm the editor emits valid `http_request` AND `foreach` nodes with the right params shapes.
- [ ] 6.11 `[verification]` Runs list filtering: with at least one parent + one child run present, confirm default `GET /api/runs` hides the child AND the "显示子运行" toggle reveals it.
- [ ] 6.12 `[verification]` Pagination: with >50 runs, confirm the runs-list page paginates and the next page loads.
- [ ] 6.13 `[verification]` Kill all dev processes.

## 7. README

- [ ] 7.1 Update `auto-agent/README.md` — new "节点库 / Node library" section: catalogue of all node types (existing + new), per-type params shape, output shape, security boundary for `read_file` / `write_file` (workspace dir), HTTP unrestricted-egress caveat, SMTP credential shape, foreach iteration cap, subworkflow recursion cap.

---

## Parallel Implementation Plan

Three sibling workers after the parent lands §1. The change is the largest in the roadmap (`L` effort) and the cleanest split is by node category: A owns non-browser actions, B owns composite flow nodes + executor changes, C owns the frontend.

### Sibling A — Backend non-browser actions `[backend-nodes]`

**Mission.** Six new action functions (HTTP, file r/w, email, JSON / CSV parse), wire them into dispatch, editor / planner prompt extensions. All of §2 and §4.

**Owns.** `backend/app/tools/actions_http.py` (new), `backend/app/tools/actions_files.py` (new), `backend/app/tools/actions_email.py` (new), `backend/app/tools/actions_parse.py` (new), the dispatch additions in `backend/app/executor.py` for the six new types, `backend/app/agents/editor.py` / `planner.py` (system-prompt catalogue), all of `backend/tests/test_actions_http.py`, `test_actions_files.py`, `test_actions_email.py`, `test_actions_parse.py`.

**Must NOT touch.** Anything under `frontend/`, the foreach / subworkflow / condition logic (Sibling B), the workflow / runs routers (Sibling B for child-run plumbing, Sibling C for UI), `backend/app/tools/browser.py`, `backend/app/tools/actions.py` (the existing browser actions are unchanged; new action functions live in separate modules to avoid file-level conflicts with Sibling B).

**Shared contract deps (§1).** Six per-type params models, eight new `NodeType` literals (Sibling A consumes 6 of them), `sandbox.py`, new `httpx` and `aiosmtplib` dependencies.

**Independent verification.** `pytest backend/tests/test_actions_*.py` passes; a tiny script wires each new action into a one-node workflow via the existing executor and asserts the output shape.

**Estimated tasks.** ~10 (2.1–2.7 + 4.1–4.3).

### Sibling B — Backend composite flow + runs router `[backend-flow]`

**Mission.** `foreach`, `subworkflow`, condition extension, parent/child run linkage in the runs router. All of §3.

**Owns.** `backend/app/tools/actions_foreach.py` (new), `backend/app/tools/actions_subworkflow.py` (new), `backend/app/services/sub_runs.py` (new), `backend/app/executor.py` (foreach / subworkflow dispatch + condition evaluator rewrite), `backend/app/routers/runs.py` (parent/child filtering + child_runs population + include_children query param), workflow-validation rejection rules for nested foreach + recursion depth, all of `backend/tests/test_actions_foreach.py`, `test_actions_subworkflow.py`, `test_condition_predicate.py`.

**Must NOT touch.** Anything under `frontend/`, the six non-browser action modules (Sibling A), the editor / planner system prompts (Sibling A — keeps the catalogue in one place), `backend/app/tools/actions.py` (browser actions unchanged), the workflows / chat / credentials routers.

**Shared contract deps (§1).** `Run.parent_run_id` column, `ConditionPredicate` model, `ForeachParams` / `SubworkflowParams` models, four new event-type literals, sibling A's contributed per-type params models (read-only).

**Independent verification.** `pytest backend/tests/test_actions_foreach.py test_actions_subworkflow.py test_condition_predicate.py` passes; a scripted end-to-end run drives a foreach over a tiny list and a self-subworkflow to confirm recursion cap fires.

**Estimated tasks.** ~8 (3.1–3.8).

### Sibling C — Frontend `[frontend]`

**Mission.** Per-type params forms, canvas icons, runs-list filter + pagination, child-run rendering on run detail, RunLog / RunReplay event handling. All of §5.

**Owns.** The eight new per-type params forms (semantic role — inside the existing NodeInspector), the canvas icon-map extension (semantic role — the GlowNode renderer), the runs-list page extensions (filter toggle + pagination), the run-detail page extension (child_runs nested table), the RunLog / RunReplay event-type case extensions, the chat patch-preview node-type cases.

**Must NOT touch.** Backend files, `frontend/src/store.ts` (consumes via existing public API only), `frontend/src/chat/` internals beyond the patch-preview component.

**Shared contract deps (§1).** Eight new `NodeType` TS literals + per-type params models, four new event-type literals, `parent_run_id` and `child_runs` on `RunOut`.

**Independent verification.** Against running Sibling-A + Sibling-B backends, author a workflow that uses one node of each new type via the chat editor, confirm forms render correctly for each, run the workflow, confirm the runs-list filtering hides child runs and the run-detail page lists them.

**Estimated tasks.** ~8 (5.1–5.8).

### Rationale for the three-way split

- The non-browser actions (Sibling A) and the composite flow nodes (Sibling B) live in separate modules with separate test files; their only contact in `executor.py` is the dispatch table, which Sibling A and Sibling B touch through different conditional branches (`if node.type in {"http_request", …}: …` vs `if node.type in {"foreach", "subworkflow"}: …`). With a small "register-your-types-here" convention in the parent §1, they don't conflict.
- The frontend (Sibling C) consumes the schema additions and event-type extensions from §1 and renders per-type UI. The eight forms are independent of each other and of any backend implementation detail beyond the params shape.
- The runs router lives with Sibling B because the parent/child filtering AND the `child_runs` population are tightly coupled to the `subworkflow` action's behaviour.
- Editor / planner prompts go with Sibling A even though they describe both action and flow nodes, because we want the catalogue update to land as a single string edit rather than two siblings racing on the same file.
