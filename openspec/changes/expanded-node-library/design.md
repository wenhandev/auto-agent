## Context

The MVP's node catalogue is browser-shaped. Every action either drives Playwright or controls graph traversal. Real automations need non-browser steps (call an API, read a CSV, send an email) and composite steps (loop over a list, invoke another workflow). The platform's data model is ready: `Node.params: dict` accepts any per-type schema; the executor's dispatch table just needs more entries; the chat editor learns about new types by reading them in its system prompt.

This change adds eight node types and extends `condition`. The new types are split into two capability folders because they target different audiences:

- `non-browser-action-nodes` is the "I need to glue services together" surface: HTTP, files, email, parsing.
- `composite-flow-nodes` is the "I need to express loops, sub-routines, and richer branches" surface.

Both ship together in one change because the editor / planner prompts are updated once with the full catalogue, and the per-type UI forms share a common skeleton.

## Goals / Non-Goals

**Goals**

- Eight new node types, each with a tightly-scoped per-type params model and a documented output shape.
- The new actions integrate with credentials (HTTP `Authorization`, SMTP login) through the existing `{{cred...}}` token form.
- `foreach` iterates a list, runs a one-node-deep "body" subgraph per item, exposes `item` and `index` through the standard `{{nodes...}}` token form, and is capped at a hard maximum.
- `subworkflow` invokes another `Workflow` row as a nested run; the child run is a real `Run` row with `parent_run_id`. Input mapping uses the standard token form.
- `condition` grows a typed predicate evaluator that does NOT involve `eval`; backwards compatible.
- Filesystem access is sandboxed to a workspace dir; explicit security boundary.
- Editor / planner prompts updated with one example per new type so the LLMs can suggest them naturally.

**Non-Goals**

- Arbitrary `eval` / `exec` node (security boundary).
- OS command execution / shell node (security boundary).
- Database connection node (deferred change; the credential shape for DB DSNs needs its own design).
- A full templating language inside params (string concatenation and conditional defaults are out — `node-context-variables` is the only token mechanism).
- Inline JavaScript in the browser (use `fuzzy_action` for that).
- `subworkflow` mutation of the parent's context (children produce one output; cross-talk happens only via the parent's `{{nodes.<subworkflow_id>.output...}}` reference).
- Streaming / chunked HTTP responses (`http_request` reads the full body up to a 10 MB cap).
- HTTP/2 push, WebSocket actions, gRPC. POC scope is request/response over HTTP/1.1 / HTTP/2.

## Decisions

### Decision 1: Per-type params models registered through a discriminator

We extend the pydantic union the platform already uses for `Node.params`. Each new node type registers its model:

```python
class HttpRequestParams(BaseModel):
    method: Literal["GET","POST","PUT","DELETE","PATCH","HEAD"]
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None  # JSON-serialisable; str passes through as text
    body_kind: Literal["json","text","form","none"] = "json"
    timeout_ms: int = Field(default=15_000, ge=1, le=120_000)

class ReadFileParams(BaseModel):
    path: str  # relative to workspace dir; absolute paths refused
    encoding: str = "utf-8"
    max_bytes: int = Field(default=1_048_576, ge=1, le=10_485_760)  # 1 MB default, 10 MB cap
# ... etc
```

The dispatcher resolves the per-type model via the type-tag, validates `params`, and forwards the typed object to the action. Output is always a dict (validated likewise per type) so `{{nodes...}}` references work uniformly.

### Decision 2: Filesystem sandbox — per-workflow

Every file path passed to `read_file` / `write_file` SHALL be resolved against the **per-workflow** dir `WORKSPACE_DIR / <workflow_id>/`, where `WORKSPACE_DIR = backend/data/workflow_files/`. Absolute paths SHALL be rejected. `..` traversal SHALL be rejected after `Path.resolve()` normalisation; the resolved path SHALL be a subpath of the per-workflow dir. The per-workflow dir SHALL be created lazily on first access by either `read_file` or `write_file` (lifespan only creates the top-level `WORKSPACE_DIR`).

Cross-workflow file sharing is **explicitly OUT OF SCOPE**. A workflow that needs data produced by another workflow MUST copy it explicitly (e.g. invoke the producing workflow via `subworkflow` and consume its output via `{{nodes.<sub>.output.final_output...}}`, or have the operator manually copy files using their OS file manager). Rationale: the sandbox is the enforcement boundary for a future multi-user `owner_id` scheme (already reserved on every relevant table); a shared workspace would force a re-architecture at that point. The cost today is one extra `subworkflow` call when sharing is genuinely needed.

```python
# backend/app/tools/sandbox.py
WORKSPACE_DIR = Path("backend/data/workflow_files").resolve()

def workflow_dir(workflow_id: str) -> Path:
    """Return the per-workflow sandbox dir; create it lazily on first access."""
    wf_dir = (WORKSPACE_DIR / workflow_id).resolve()
    if not str(wf_dir).startswith(str(WORKSPACE_DIR) + os.sep):
        # Defensive: workflow_id is a server-generated opaque id, but never trust.
        raise SandboxViolation(f"invalid workflow_id for sandbox: {workflow_id!r}")
    wf_dir.mkdir(parents=True, exist_ok=True)
    return wf_dir

def resolve_sandbox_path(user_path: str, *, workflow_id: str) -> Path:
    if Path(user_path).is_absolute():
        raise SandboxViolation("absolute paths refused")
    base = workflow_dir(workflow_id)
    resolved = (base / user_path).resolve()
    if not str(resolved).startswith(str(base) + os.sep) and resolved != base:
        raise SandboxViolation(f"path escapes workspace for workflow {workflow_id}: {user_path}")
    return resolved
```

The executor passes `workflow_id` through to the file actions. Ephemeral runs (`/ws/run` with a workflow payload, no `workflow_id`) SHALL NOT be allowed to use `read_file` / `write_file` — the actions SHALL raise `SandboxViolation("file actions require a persisted workflow")` if `workflow_id is None`. This matches `per-workflow-credentials`'s pattern of degrading the legacy ephemeral path.

When a workflow is deleted (`DELETE /api/workflows/{id}`), its per-workflow dir SHALL be removed in the same operation (best-effort `shutil.rmtree(..., ignore_errors=True)`; failures are logged but do not block the API response). Documented in the spec.

### Decision 3: `http_request` output shape is fixed

```json
{
  "status": 200,
  "headers": { "content-type": "application/json", ... },
  "json": {...} | null,
  "text": "...",
  "elapsed_ms": 123
}
```

`json` is populated only when the response's `content-type` matches `application/json` AND parsing succeeds; otherwise `null`. `text` is always populated (truncated to 1 MB; truncation marker `"text_truncated": true` added). This shape is stable so downstream nodes can rely on `{{nodes.<http>.output.json.products[0].id}}` without conditional checks.

HTTP errors (`4xx`/`5xx`) do NOT raise — the node completes with the response shape. Operators who want "fail on 4xx" wrap the node with `node-error-handling`'s `on_error` semantics combined with a downstream `condition` node checking `{{nodes.<http>.output.status}}`.

Network errors (DNS, refused, timeout) DO raise — they're action failures, not response shapes — and trigger `node_failed` / retry / on-error per the existing rules.

### Decision 4: `send_email` uses SMTP, credential by name

```python
class SendEmailParams(BaseModel):
    smtp_credential: str   # cred name; the cred carries host/port/username/password/use_tls
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    body_kind: Literal["text","html"] = "text"
    attachments: list[str] = Field(default_factory=list)   # sandbox-resolved paths
```

The credential is loaded via the standard credential interpolation pass (so per-workflow link enforcement still applies). The credential's stored fields are conventionally `{host, port, username, password, use_tls}`; documented in the spec. We do NOT bake the SMTP host into a global setting because the operator likely uses a different SMTP per workflow (corporate vs personal vs a transactional provider).

Output:

```json
{
  "message_id": "<uuid>",
  "accepted": ["alice@example.com"],
  "rejected": []
}
```

### Decision 5: `parse_json` / `parse_csv` are pure transforms

Both nodes consume a string (typically `{{nodes.<read_file>.output.contents}}` or `{{nodes.<http>.output.text}}`) and return a parsed structure. They do not touch the filesystem or the network. Rationale: a single-purpose parser node is easier to compose than overloading `read_file` with a `parse: bool` flag.

```python
class ParseJsonParams(BaseModel):
    input: Any   # typically a {{nodes...}} reference resolved to str

class ParseCsvParams(BaseModel):
    input: Any
    has_header: bool = True
    delimiter: str = ","
```

`parse_json.output = {"parsed": <Any>}`. `parse_csv.output = {"rows": list[dict|list], "header": list[str]|null}`.

### Decision 6: `foreach` semantics

```python
class ForeachParams(BaseModel):
    items: Any           # typically {{nodes.<id>.output.<list>}} resolved to a list
    body_workflow: "Workflow"  # inline sub-workflow JSON; one start_id, one end_id, no nested foreach in v1
    max_iterations: int = Field(default=1000, ge=1, le=10_000)
    parallel: bool = False  # MUST be False in v1 (the single Chromium tab forces sequential)
```

The cap is enforced by pydantic (`le=10_000`). There is NO `unsafe_max_iterations` escape hatch. Rationale: real workflows that need >10k iterations are almost always either (a) a bug that the cap helpfully catches, or (b) a missing-pagination problem (the right fix is to add a pagination step to the source data, not to lift the cap). The rare legitimate "process 100k rows" case is punted to a future change that designs proper batching primitives. Per-node opt-out would let the cap erode silently — explicit policy is "if you hit the cap, the system makes you rethink the design".

The executor walks `items` and, per item, runs the `body_workflow` with a per-iteration context that exposes:

- `{{nodes.<foreach_id>.output.item}}` — the current item
- `{{nodes.<foreach_id>.output.index}}` — 0-based iteration index

A foreach iteration that fails is governed by `on_error` on the FOREACH node (not the body's failing node): `fail_run` (default) stops the foreach AND the parent run; `continue` skips the item and proceeds; `branch` requires a `kind="on_error"` edge from the foreach node, which is followed once any iteration fails.

`foreach.output = {"item_count": N, "succeeded": K, "failed": N-K, "results": [<each iteration's body's last node output>, ...]}`.

Sub-workflow per-iteration limit: nested `foreach` inside `body_workflow` is REJECTED at workflow validation time in v1 (we want one clear iteration boundary). Nested `subworkflow` is allowed.

The `parallel: false` constraint is hard-coded for v1; the field exists for forward compatibility but raises `ValidationError` when set to `true`. Rationale: the single-Chromium-tab constraint means any browser-touching iteration must be sequential; non-browser iterations could parallelise but the complexity is not worth the v1 win.

```mermaid
sequenceDiagram
    participant P as Parent Executor
    participant F as Foreach action
    participant B as Body sub-executor
    P->>F: dispatch foreach with items=[a,b,c]
    loop per item
        F->>B: run(body_workflow, context += {item, index})
        B-->>F: body's last output
        F->>F: append to results; check max_iterations
        F-->>P: emit foreach_iteration_completed(index, output)
    end
    F-->>P: return {item_count, succeeded, failed, results}
```

### Decision 7: `subworkflow` reuses the run table

```python
class SubworkflowParams(BaseModel):
    workflow_id: str
    version_id: Optional[str] = None   # default: current_version_id
    input: dict[str, Any] = Field(default_factory=dict)
```

The action calls into `services.runs.run_subworkflow(parent_run_id, workflow_id, version_id, input)`. The child run is created as a regular `Run` row with `parent_run_id = parent_run_id`; the executor recurses into it; the child's `node_completed.output` events are persisted normally. When the child terminates, the parent's `subworkflow` action returns:

```json
{
  "child_run_id": "run_…",
  "status": "completed",
  "final_output": <output of the child's last node, or null>
}
```

The parent run's context dict has `nodes.<subworkflow_node>.output` set to the above. Downstream nodes can reference `{{nodes.<subworkflow_node>.output.final_output.<path>}}`.

Child runs share the same Chromium singleton — they don't start a new browser. Because the executor's lock is process-wide, a child run holds the same single tab as the parent (the parent's "running" status persists; the child's status is also "running" briefly while the recursion is active). We do NOT add a new "executing-child" status; both rows just show "running".

`input` is passed via a synthetic `nodes._input.output` entry in the child's context dict, accessible as `{{nodes._input.output.<key>}}` inside the child's body. The reserved id `_input` is documented; the planner / editor are told not to use ids beginning with `_`.

### Decision 8: Extended `condition` predicate

Today's `condition` evaluates `params.expr` in a "small restricted context (defaulting to truthy)" per the existing spec. We replace the restricted-context interpreter with a tiny typed evaluator:

```python
class ConditionPredicate(BaseModel):
    left: Any                     # typically a {{nodes...}} reference
    op: Literal["==","!=",">",">=","<","<=","in","not_in","is_truthy","is_falsy"]
    right: Optional[Any] = None    # required for binary ops; absent for is_truthy / is_falsy

class ConditionParams(BaseModel):
    predicate: Optional[ConditionPredicate] = None
    # backward-compat: legacy condition nodes whose params.expr is absent or "true" → predicate=None
```

When `predicate` is `None` (or the legacy `expr` field is present and the predicate is not), the executor falls back to today's "default to `when=='true'` edge" behaviour. When `predicate` is set, the typed evaluator returns a bool and the executor follows the edge whose `when` matches.

No `eval`, no expression DSL, no `and` / `or` combinators in v1. Compound conditions are expressed by chaining two `condition` nodes.

Output:

```json
{
  "predicate": {...},
  "result": true | false
}
```

### Decision 9: Editor / planner prompt catalogue

Both prompts grow by a section:

```text
Available non-browser action node types (one example per):

- http_request: { method:"GET", url:"https://api.example.com/orders/{{nodes.n1.output.order_id}}",
                  headers:{"Authorization":"Bearer {{cred.api.token}}"}, timeout_ms:5000 }
  → output { status, headers, json, text, elapsed_ms }
- read_file:    { path:"orders.csv" }
  → output { contents, byte_count, path }
- write_file:   { path:"out/{{nodes.n2.output.id}}.json", contents:"{{nodes.parse.output.parsed}}" }
  → output { path, byte_count }
- send_email:   { smtp_credential:"corp-smtp", to:["alice@x"], subject:"...", body:"..." }
  → output { message_id, accepted, rejected }
- parse_json:   { input:"{{nodes.http.output.text}}" } → output { parsed }
- parse_csv:    { input:"{{nodes.read.output.contents}}", has_header:true }
                → output { rows, header }
- foreach:      { items:"{{nodes.parse.output.parsed.items}}",
                  body_workflow:{ ... small Workflow JSON ... } }
                → output { item_count, succeeded, failed, results }
- subworkflow:  { workflow_id:"wf_…", input:{ "order_id": "{{nodes.n1.output.id}}" } }
                → output { child_run_id, status, final_output }

The condition node now accepts a typed predicate:
- condition: { predicate:{ left:"{{nodes.http.output.status}}", op:">=", right:400 } }
```

Same paragraph in `planner.py` and `editor.py`. No code changes besides the string updates.

### Decision 10: Run-history extensions

`Run` gains `parent_run_id: Optional[str] = Field(default=None, foreign_key="run.id", index=True)`. `GET /api/runs` filters to `parent_run_id IS NULL` by default; a `?include_children=true` query parameter returns the unfiltered list. `GET /api/runs/{id}` includes `child_runs: list[RunSummary]` populated by `SELECT … FROM run WHERE parent_run_id = id`.

Four new event types: `foreach_iteration_started`, `foreach_iteration_completed`, `subworkflow_started`, `subworkflow_completed`. All persisted via existing `record_event` plumbing.

### Decision 11: Per-type icons via existing data-node-type

The MVP's `GlowNode` already attaches `data-node-type` to its DOM element. The frontend's icon map gains entries for each new type, mapping to lucide-react icons (e.g. `Globe` for `http_request`, `FileText` for `read_file`, `Save` for `write_file`, `Mail` for `send_email`, `Braces` for `parse_json`, `Table` for `parse_csv`, `Repeat` for `foreach`, `Workflow` for `subworkflow`). No CSS layout change.

## Risks / Trade-offs

- **HTTP egress is unrestricted**: a workflow can call any URL. Mitigation: documented; future change can add an allowlist. Credentials interpolated through `{{cred...}}` so secret leakage is minimised.
- **File sandbox path bypass**: relies on `Path.resolve()` correctness. We add unit tests for `..`, symlink escapes, absolute paths, Windows drive letters (`C:\…`), UNC paths (`\\server\share`).
- **SMTP credentials**: stored as Fernet-encrypted blobs like any other credential; the operator chooses the host. We do NOT enforce TLS in v1 (`use_tls` is per-credential); documented.
- **`foreach` blowing out the queue**: a 1000-iteration foreach over a 30 s browser body is an 8-hour run. Cap is the operator's circuit breaker. Mitigation: the foreach action checks the abort flag between iterations.
- **`subworkflow` recursion depth**: a workflow that subworkflows itself loops infinitely. Mitigation: max recursion depth of 5 enforced at the executor level (raises `RecursionError` translated to `node_failed`); documented.
- **Nested `foreach` inside `subworkflow`**: explicitly allowed (a sub-workflow can do its own iteration). Nested `foreach` inside a `foreach` body is rejected at validation. This is asymmetric on purpose: the validation rule says "your inline body cannot itself foreach" because debugging two-level inline loops is painful, but a sub-workflow with a foreach is a separately authored unit and is fine.
- **`condition` predicate left-side resolution**: `left` is typically a `{{nodes...}}` token. The token is resolved before the predicate is evaluated (existing interpolation pass). A missing path fails the condition node loudly per the variables change's rule, which is the desired behaviour.

## Migration Plan

1. `ALTER TABLE run ADD COLUMN parent_run_id TEXT NULL` on first boot. Existing rows have `NULL`. Idempotent helper writes marker `backend/.parent_run_id_added`.
2. Create `backend/data/workflow_files/` directory in lifespan if missing.
3. Workflow schema literal extensions are application-level; pydantic deserialises old workflow JSON unchanged.
4. New event types are append-only; existing replay logic ignores unknown event types.
5. Editor / planner prompt extensions take effect on the next backend restart.

## Resolved Decisions

The two original open questions were closed by the user before implementation:

1. **Sandbox dir scope** → **per-workflow** (`workflow_files/<workflow_id>/`) per Decision 2 above. Cross-workflow file sharing is explicitly OUT OF SCOPE; users must copy via the workflow they own (e.g. via `subworkflow`). Rationale: the sandbox is the enforcement boundary for a future multi-user `owner_id` scheme; a shared workspace would force a re-architecture at that point.
2. **`foreach.max_iterations`** → **default 1000, hard cap 10000**, NO `unsafe_max_iterations` escape hatch (see updated foreach params in Decision 6). Real workflows >10k iterations are almost always a bug or a missing-pagination problem; the rare legitimate case is punted to a future "batch-processing" change rather than letting the cap erode silently.

## Open Questions

All design decisions resolved as of 2026-05-15.
