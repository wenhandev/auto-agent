## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Add `VariableResolutionError` to `backend/app/services/` (new module `variable_interpolation.py`); export from `__all__`. Keep `CredentialResolutionError` in `credential_interpolation.py` as before.
- [x] 1.2 `[shared-contract]` Add Pydantic `LastOutputShapesResponse` to `backend/app/schemas_api.py`: `{run_id: str | null, started_at: datetime | null, shapes: dict[str, Any]}`. Export.
- [x] 1.3 `[shared-contract]` Add TS mirror to `frontend/src/types-platform.ts`: `LastOutputShapesResponse`, `NodeOutputShape` (recursive `Record<string, NodeOutputShape> | unknown`).
- [x] 1.4 `[shared-contract]` Add `apiClient.workflows.getLastOutputShapes(workflowId)` stub to `frontend/src/api-platform.ts`.
- [x] 1.5 `[shared-contract]` Smoke-check: `python -c "from app.services.variable_interpolation import VariableResolutionError; print('ok')"` and `cd frontend && npx tsc --noEmit` pass.

## 2. Backend interpolation utility (Sibling A — `[backend-runtime]`)

- [x] 2.1 Author `backend/app/services/variable_interpolation.py`:
  - `resolve_params(params, *, context, session, workflow_id=None) -> dict`;
  - one tree walk; for every string field, find every `{{…}}` token via a single regex (`r"\{\{\s*([^{}]+?)\s*\}\}"`);
  - resolve `nodes.<id>[.path]` against `context`, `cred.<name>.<field>` via the existing credential helper;
  - `run.…` and `trigger.…` prefixes raise `VariableResolutionError(f"prefix '<p>' is reserved for a future change")` per design Decision 11 (no behavioural resolution; just the reserved-error);
  - any other prefix raises `VariableResolutionError(f"unknown variable prefix in '{token}'; supported prefixes: nodes, cred")`;
  - whole-token vs interpolated semantics per design Decision 3 (raw value vs `str()`/`json.dumps`);
  - non-recursive substitution per design Decision 5;
  - missing-path error per design Decision 4 lists up to 8 dot-paths of available siblings AND appends a `difflib.get_close_matches(..., n=1, cutoff=0.6)` "did you mean" suggestion when one exists.
- [x] 2.2 Modify `backend/app/executor.py::run_workflow` — hold `context: dict[str, Any] = {}`; before each action call `resolve_params(node.params, context=context, session=session, workflow_id=workflow_id)`; on action success store `context[node.id] = output`. Delete the direct call to `credential_interpolation.resolve_params` (now invoked inside the chained pass).
- [x] 2.3 Modify `backend/app/services/credential_interpolation.py` — expose an internal `_resolve_cred_token(name, field, session, workflow_id) -> str` callable that the new chained pass invokes per token. Keep `resolve_params` as a backward-compatible alias that walks params with only the credential token type (called from the legacy `/ws/run` ad-hoc path that has no `context`).
- [x] 2.4 Add unit tests `backend/tests/test_variable_interpolation.py`:
  - whole-token returns raw value for dict / list / int / bool;
  - interpolated returns JSON-stringified embedded value;
  - dot-path with numeric segment resolves list index AND string key (per Decision 2);
  - missing path raises `VariableResolutionError` whose message lists available sibling paths AND includes a "did you mean" suggestion when one is within edit-distance cutoff;
  - unknown prefix raises with `"supported prefixes: nodes, cred"`;
  - reserved-prefix `{{run.…}}` raises with `"prefix 'run' is reserved for a future change"`;
  - reserved-prefix `{{trigger.…}}` raises with `"prefix 'trigger' is reserved for a future change"`;
  - non-recursive: a resolved credential value containing `{{nodes.…}}` is preserved verbatim.
- [x] 2.5 Add `backend/app/routers/workflows.py::get_last_output_shapes` — `GET /api/workflows/{id}/last-output-shapes` returns `LastOutputShapesResponse`. Loads the most recent `Run` for `workflow_id` with `status="completed"`; iterates its `RunEvent` rows with `event_type="node_completed"`; assembles `shapes[node_id] = event.payload_json["output"]`. Empty map and null run id when no successful run exists.
- [x] 2.6 Add unit tests `backend/tests/test_last_output_shapes.py` — empty when no successful run; correct map when one successful run; only most recent successful run is used; failed runs are skipped even if more recent.
- [x] 2.7 Smoke-check: `pytest backend/tests/test_variable_interpolation.py backend/tests/test_last_output_shapes.py -v` passes.

## 3. Backend editor prompt (Sibling A continued — `[backend-runtime]`)

- [x] 3.1 Modify `backend/app/agents/editor.py` system prompt — append a paragraph:
  - "You can reference an earlier node's output via `{{nodes.<id>.output[.path.to.field]}}`. The token is resolved at run time against that node's actual output. Example: a click-product node `n4` returns `{"product_id": "P-42"}`; a later navigate node can set `"url": "https://shop.com/p/{{nodes.n4.output.product_id}}"`. Avoid using literal `{{` in any string you emit — it will be interpreted as the start of a token."
- [x] 3.2 Modify `backend/app/agents/planner.py` system prompt — append the same paragraph so the planner can suggest tokens at workflow-generation time too.
- [x] 3.3 Add unit test `backend/tests/test_editor_prompt.py` verifying the new paragraph is present (a literal substring check; cheap regression).

## 4. Frontend (Sibling B — `[frontend]`)

- [x] 4.1 Author `frontend/src/inspector/AvailableVariablesTab.tsx` — calls `apiClient.workflows.getLastOutputShapes(workflowId)`. Computes the predecessor set of the selected node from the current workflow graph (BFS over `edges` in reverse). For each predecessor that has a shape entry, renders a collapsible tree of dot-paths. Each leaf shows the value preview (truncated to 80 chars) and copies `{{nodes.<id>.output.<path>}}` on click. Empty state: "尚无运行历史，先成功跑一次以获取输出样例".
- [x] 4.2 Mount the new tab inside the NodeInspector (semantic role — the existing right-rail inspector that shows node metadata). The tab order: `属性 | 可用变量 | (future tabs)`.
- [x] 4.3 Author `frontend/src/inspector/TokenChip.tsx` and a small `TokenTextField` wrapper around the existing string-input control. Detects `{{nodes.…}}` and `{{cred.…}}` tokens in the value and renders each as a chip with an icon. Click → popover with the resolved-from-latest-run value if available; otherwise "未知（运行后可见）". Delete the chip removes the full token from the underlying string value.
- [x] 4.4 Wire `TokenTextField` into the NodeInspector's params editor for every string-typed field across all node types currently rendered (`navigate.url`, `click.selector`, `fill.selector`, `fill.value`, `extract.query`, `wait.ms` as string-or-number, `fuzzy_action.instruction`, `condition.expr`).
- [x] 4.5 Add a small "插入变量" affordance next to each string field that opens the AvailableVariablesTab in a popover for one-click insertion at the cursor.
- [x] 4.6 Smoke-check: `pnpm build` clean; `tsc --noEmit` clean; manually open a workflow with at least one successful run, open a downstream node, confirm the "可用变量" tab renders predecessor outputs and clicking a leaf inserts the correct token.

## 5. Verification (parent worker)

- [ ] 5.1 `[verification]` Author a tiny end-to-end test workflow: `start → extract (returns {"x": 42}) → echo (returns its params)`. Set the echo node's params to `{"value": "{{nodes.<extract_id>.output.x}}"}`. Run it. Confirm the `node_completed.output` of the echo node contains `{"value": 42}` (raw int, not string).
- [ ] 5.2 `[verification]` Interpolated form: set the value to `"answer={{nodes.<extract_id>.output.x}}"`. Confirm the echo output's `value` is the string `"answer=42"`.
- [ ] 5.3 `[verification]` Missing path: set the value to `"{{nodes.<extract_id>.output.missing}}"`. Confirm the run fails at the echo node with a `node_failed` event whose message contains `"path 'output.missing' missing on node"` AND lists `'output.x'` among available siblings.
- [ ] 5.4 `[verification]` Unknown prefix: set the value to `"{{run.foo}}"`. Confirm the failure message contains `"supported prefixes: nodes, cred"`.
- [ ] 5.5 `[verification]` Chained pass: set the value to `"user={{cred.bosch-login.username}}-prod={{nodes.<extract_id>.output.x}}"`. With a linked credential, confirm both tokens resolve correctly into the same string.
- [ ] 5.6 `[verification]` UI: open the workflow detail page; on the echo node, the "可用变量" tab shows the extract node's output shape with `x: 42` as a clickable leaf; clicking inserts the correct token into the focused params field.
- [ ] 5.7 `[verification]` Backward compat: the seeded `示例工作流` (which has no `{{nodes.…}}` tokens) still runs end-to-end with no change in behaviour.
- [ ] 5.8 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

Two sibling workers after the parent lands §1.

### Sibling A — Backend runtime `[backend-runtime]`

**Mission.** Implement `variable_interpolation`, wire it into the executor, expose `last-output-shapes`, update the editor / planner system prompts. All of §2 and §3.

**Owns.** `backend/app/services/variable_interpolation.py` (new), `backend/app/services/credential_interpolation.py` (internal refactor for the token-callable surface), `backend/app/executor.py` (per-run context dict + entry-point swap), `backend/app/routers/workflows.py` (new endpoint), `backend/app/agents/editor.py` and `backend/app/agents/planner.py` (system-prompt paragraph), all of `backend/tests/test_variable_interpolation.py`, `backend/tests/test_last_output_shapes.py`, `backend/tests/test_editor_prompt.py`.

**Must NOT touch.** Anything under `frontend/`, `backend/app/tools/actions.py` (the action signatures are unchanged), `backend/app/agents/fuzzy.py` / `extractor.py` (no behavioural changes), the `Workflow` / `Node` / `Edge` MVP schemas (no schema change).

**Independent verification.** `pytest backend/tests/test_variable_interpolation.py backend/tests/test_last_output_shapes.py backend/tests/test_editor_prompt.py` passes; a tiny script runs the sample workflow with one extra `{{nodes.…}}` token and asserts the run completes with the resolved value in the final node's output event.

**Estimated tasks.** ~10 (2.1–2.7 + 3.1–3.3).

### Sibling B — Frontend `[frontend]`

**Mission.** Inspector tab, token chip rendering, "插入变量" affordance. All of §4.

**Owns.** `frontend/src/inspector/AvailableVariablesTab.tsx` (new), `frontend/src/inspector/TokenChip.tsx` (new), `frontend/src/inspector/TokenTextField.tsx` (new), wiring edits to the existing NodeInspector's params editor (semantic role; the implementer picks the existing file that owns it during the in-flight shadcn migration). One implementation of the `apiClient.workflows.getLastOutputShapes` method body.

**Must NOT touch.** Backend files, `frontend/src/store.ts` (consumes via existing public API only), `frontend/src/chat/`.

**Shared contract deps (§1).** `LastOutputShapesResponse` TS type, `apiClient.workflows.getLastOutputShapes` stub.

**Independent verification.** Against a running Sibling-A backend, open a workflow with a successful run, open a node, confirm the "可用变量" tab populates and clicking inserts the correct token.

**Estimated tasks.** ~6 (4.1–4.6).

### Rationale

The interpolation pass and the inspector tab share only the API shape `LastOutputShapesResponse`. Once that shape is in the shared contract, neither sibling blocks the other. The editor / planner prompt updates live on the backend sibling because they ship together with the runtime change (no point updating prompts that resolve tokens before the resolver exists).
