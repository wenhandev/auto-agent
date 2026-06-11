## depends_on

- `auto-agent-mvp` — workflow schema (`NodeType` literal), executor, edge semantics, condition node default branch.
- `auto-agent-platform` — credential interpolation (HTTP nodes carry `Authorization` via `{{cred...}}`), workflow persistence (versions, chat editor), runtime-LLM-config.
- `per-workflow-credentials` — link-required interpolation on persisted runs (HTTP / email nodes that use credentials).
- `node-context-variables` — the new nodes' main use case is composability: an `http_request` node returns `{"status", "headers", "json", "text"}`; downstream nodes consume it via `{{nodes.<id>.output.json...}}`. `foreach` exposes an iteration variable via the same token form (`{{nodes.<foreach_id>.output.item}}`).
- `node-error-handling` (soft) — every new node interacts well with `retry` / `on_error` / `on_error` edges. Not a hard dependency: each new node works without it; users with it get much better resilience.

No dependency on `triggers-and-scheduling`, `human-in-the-loop`, or `self-healing-selectors`.

## Why

Today the executor knows exactly nine node types: `start`, `end`, `navigate`, `click`, `fill`, `extract`, `wait`, `fuzzy_action`, `condition`. Every one of them is either a browser action or a control primitive. That is the right shape for the POC (a browser-automation tool), but it means even trivial real workflows degenerate:

- "Fetch a price from a JSON API, then click the matching row on a web page" → impossible without a `fuzzy_action` that opens DevTools.
- "Read a list of order ids from a CSV, run the existing 'check order status' workflow per id" → impossible.
- "After a successful checkout, email the receipt to a fixed address" → impossible.
- "If the page reports out-of-stock, fall through to a separate sub-workflow that orders from the backup supplier" → would benefit hugely from `subworkflow` plus `on_error` edges.

We add the missing primitives in one PR-sized scope. Each new node type is small (a single action function), follows the same pattern as today's action set (params validated by a per-type pydantic model, output validated likewise), and integrates cleanly with credentials, context variables, retry/on-error, and the existing condition / edge semantics.

The new types fall into two capability buckets, both shipping in this change:

1. **Non-browser action nodes**: `http_request`, `read_file`, `write_file`, `send_email`, `parse_json`, `parse_csv`. Each is a single deterministic action with structured I/O.
2. **Composite flow nodes**: `foreach`, `subworkflow`, plus an extension to the existing `condition` node so it can branch on a typed predicate (not just a literal `true`/`false` default).

## What Changes

- **New node types** added to the `NodeType` literal: `http_request`, `read_file`, `write_file`, `send_email`, `parse_json`, `parse_csv`, `foreach`, `subworkflow`. The `condition` node type is unchanged in literal but its params model is extended.
- **Per-type params models** registered through the discriminator the platform uses today. Each model lists exactly the fields the action consumes; pydantic rejects extras.
- **Per-type output shapes** documented in each spec. Output is a dict (consistent with today's action return convention) so `{{nodes.<id>.output.<path>}}` resolves naturally.
- **Actions**:
  - `http_request` via `httpx.AsyncClient` (already a transitive dependency or added here).
  - `read_file` / `write_file` against a sandboxed workspace dir (`backend/data/workflow_files/`, gitignored; default writable area), with explicit path checks.
  - `send_email` via SMTP using credentials from the vault.
  - `parse_json` / `parse_csv` via the standard library.
  - `foreach`: a small inline sub-executor that iterates a list and runs a one-node-deep "body" subgraph per item, capped at 1000 iterations.
  - `subworkflow`: invokes another `Workflow` (by id) as a single nested run, sharing the same persisted run hierarchy (parent + child rows).
  - `condition` (extension): a typed predicate `params.expr` evaluated via a small whitelist of operators (`==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`, `is_truthy`) over a left operand pulled from context variables. Backwards compatible — when `expr` is omitted the today's default-true behaviour stands.
- **Security boundaries** explicit in every spec: filesystem confined to a workspace dir, HTTP egress unrestricted (POC scope) but with credentials interpolated through `{{cred...}}`, SMTP via a configured credential, no Python eval, no OS command execution.
- **Sub-run model for `subworkflow`**: a new `Run.parent_run_id: str | null` column links child runs to their parent. Child runs are persisted exactly like top-level runs but are filtered out of the default `GET /api/runs` response (visible via the parent's detail page).
- **Editor / planner prompts**: extended with a catalogue listing for each new node type, including its params shape and output shape, plus one short example per node. Same pattern as previous changes' prompt updates.
- **UI**: the NodeInspector renders a type-specific params form for each new type. The canvas uses a distinct lucide-react icon per type via the existing `data-node-type` attribute on `GlowNode`. No CSS layout change beyond the icon mapping.
- **Pagination of the runs list**: cosmetic but necessary — `foreach`-heavy workflows produce many `subworkflow` child runs. Default page size 50; child runs hidden by default with a "显示子运行" toggle.

## Capabilities

### New Capabilities

- `non-browser-action-nodes`: `http_request`, `read_file`, `write_file`, `send_email`, `parse_json`, `parse_csv`. Action implementations, per-type params / output models, security boundaries, integration with credentials.
- `composite-flow-nodes`: `foreach`, `subworkflow`, extended `condition`. Sub-executor for `foreach`, parent / child run linkage for `subworkflow`, typed predicate evaluator for `condition`.

### Modified Capabilities

- `workflow-schema` (from `auto-agent-mvp`): `NodeType` grows by eight literals.
- `hybrid-executor` (from `auto-agent-mvp`): the dispatch table grows; the `condition` evaluator is rewritten to use the typed predicate when present.
- `run-history` (from `auto-agent-platform`): `Run.parent_run_id` column added; child runs filterable. New event-type entries (`foreach_iteration_started`, `foreach_iteration_completed`, `subworkflow_started`, `subworkflow_completed`).
- `chat-authoring` (from `auto-agent-platform`): editor system prompt grows by the per-type catalogue.
- `nl-workflow-planner` (from `auto-agent-mvp`): planner system prompt grows likewise.
- `credential-vault` (from `auto-agent-platform`): SMTP credentials are a new credential `kind="smtp"` recommended but not enforced; the existing `kind` enum already allows `"other"` for flexibility.

## Impact

- **Backend**: 8 new per-type action functions (~30–120 LOC each in `app/tools/actions.py`, except `foreach` / `subworkflow` which live in their own modules under `app/tools/`). New `app/tools/sandbox.py` for the workspace path checks. New dependency `httpx` (likely already transitive; pinned here). New column `Run.parent_run_id` (SQLite `ALTER TABLE ADD COLUMN` is safe). Estimated ~800 LOC of implementation + ~400 LOC of tests.
- **Frontend**: 8 per-type params forms (~40–100 LOC each), 8 new lucide icon entries, one new "显示子运行" toggle on the runs-list page, one pagination control. Estimated ~600 LOC.
- **Runtime**: the new actions are cheap (HTTP / file / parse). `foreach` blocks for its iteration body's duration; the cap of 1000 iterations is the operator's circuit breaker. `subworkflow` reuses the executor recursively — the single Chromium tab is the bottleneck, so a `foreach` over a `subworkflow` that does browser work is sequential per iteration regardless.
- **Migration**: `ALTER TABLE run ADD COLUMN parent_run_id TEXT NULL`. The default `NULL` makes every existing row a "top-level" run. New `data/workflow_files/` directory created on first boot (lifespan helper).
- **Out of scope**: arbitrary Python `eval` / `exec` node (security boundary — explicitly refused); OS command execution (`shell` node — security boundary — explicitly refused); a database query node (separate change later when we agree on the credential model for connection strings); built-in templating beyond what `node-context-variables` provides (no Jinja, no string formatting helpers); message queues (Kafka / Redis Streams) as triggers or sinks; SFTP / S3 file nodes; CSV writing back to a file (only reading in v1, write to JSON is supported via `write_file` + `parse_json` reverse).
