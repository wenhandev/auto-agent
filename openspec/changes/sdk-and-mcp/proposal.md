## depends_on

- `public-api-and-auth` — the `/api/v1` surface + API-key auth the SDKs and MCP server wrap.
- `vision-action-mode` (soft) — `run_task` is most useful with vision; not required.

No dependency on other in-flight changes.

## Why

An API is only as adopted as its clients. Skyvern ships a **Python SDK, a TypeScript SDK, an MCP server, and a CLI** so the platform plugs into scripts, CI, and AI assistants (Claude/Cursor/Windsurf) with one import. To "做到和 Skyvern 一样" `auto-agent` needs thin, ergonomic clients over its `/api/v1` surface and an MCP server so the agent can be driven from inside an AI IDE.

## What Changes

- **Python SDK** (`sdk/python/auto_agent_sdk/`): a thin client `AutoAgent(base_url, api_key)` with `run_task(prompt, url=..., **opts) -> Run`, `run_workflow(id, parameters=...)`, `get_run(id)`, `list_runs(...)`, `cancel_run(id)`, `wait(run, timeout=...)` (polls to terminal), plus `workflows` / `credentials` sub-clients. Typed via pydantic models generated from / aligned with the OpenAPI contract. Sync + a thin async variant.
- **TypeScript SDK** (`sdk/typescript/`): the same surface (`new AutoAgent({ baseUrl, apiKey })`, `runTask`, `runWorkflow`, `getRun`, `waitForRun`, `cancelRun`), shipped as an ESM package with types. Mirrors Skyvern's `skyvern.runTask({...})` ergonomics.
- **MCP server** (`mcp/`): a Model Context Protocol server exposing tools `run_task`, `run_workflow`, `get_run`, `cancel_run`, `list_workflows` so an AI assistant can drive `auto-agent`. Reads `AUTO_AGENT_BASE_URL` + `AUTO_AGENT_API_KEY` from env. Ships a ready-to-paste config snippet for Cursor/Claude.
- **CLI** (`auto-agent` console script, in the Python SDK package): `auto-agent run-task "<prompt>" --url ...`, `auto-agent run <workflow_id>`, `auto-agent runs`, `auto-agent get <run_id> [--watch]`, `auto-agent cancel <run_id>`. Streams status to the terminal.
- **Examples + docs**: a short README per SDK with the quick-start, and one end-to-end example (`run_task` → poll → print outputs/artifacts).

## Capabilities

### New Capabilities

- `python-sdk`: the Python client + models + sync/async surface + the `auto-agent` CLI.
- `typescript-sdk`: the TypeScript client + types + ESM packaging.
- `mcp-server`: the MCP tool server over `/api/v1` with an IDE config snippet.

### Modified Capabilities

(none — additive new packages; depends on the `/api/v1` contract but does not change it)

## Impact

- **Repo layout**: new top-level `sdk/python/`, `sdk/typescript/`, `mcp/` packages with their own build/publish metadata (`pyproject.toml`, `package.json`). Independent versioning from the backend.
- **Backend**: none beyond the `/api/v1` contract (this change consumes it). The curated OpenAPI is the source of truth for generated models.
- **Runtime**: clients are stateless HTTP wrappers; `wait`/`--watch` poll `GET /api/v1/runs/{id}` (no WS dependency for v1 simplicity; a streaming variant is future work).
- **Migration**: none.
- **Out of scope**: WebSocket/event-stream subscription in the SDKs (poll-only v1; a `run.stream()` is future); auto-generated SDKs in more languages; publishing to PyPI/npm (the change ships the packages; release pipelines are a separate ops concern); MCP resource exposure beyond tools.
