## Why

The MVP (see `auto-agent-mvp/proposal.md`) proved the core loop: a natural-language description becomes a `Workflow` JSON, the canvas renders it, a single Chromium window executes it, and node glow tracks the real run. Everything lives in memory and dies with the process.

Users now want to **author and reuse** workflows, not just run a one-shot demo:

1. Save workflows. Today every reload destroys the planner's output.
2. Author workflows by **chat**, not by one-shot generation. The MVP planner produces a workflow in a single call; users want a multi-turn conversation that generates a workflow, lets them run it, then iterates on it ("now also click the cart, then check out").
3. Store sensitive inputs (account credentials, API tokens) **encrypted at rest** so workflows can refer to them by name instead of inlining secrets in node `params`.
4. Inspect past runs — what events fired, what each node returned, what failed.
5. Configure the LLM provider, model, base URL, and API key from the web UI rather than editing `.env` and restarting the backend.

This change graduates the POC into a single-user local **platform**: persistent workflows, a chat-based editor agent, a credential vault, a run history with replay, and runtime-editable LLM settings. Architecture and data model deliberately leave room for a future `owner_id` so a later change can add multi-user support without a rewrite.

## What Changes

- Persist everything in **SQLite + SQLModel** under `backend/data/auto_agent.db`. New module `backend/app/db/` with engine, session, and entity models.
- Add a **credential vault** using `cryptography.Fernet`. Master key from `AUTO_AGENT_SECRET_KEY` env var; if unset, generated once into `backend/.secret_key` (file-locked, 0600 on POSIX, ACL note for Windows).
- Add a **chat-authoring** flow: per-workflow `ChatSession` with `ChatMessage` rows. Each user turn calls a new `EditorAgent` (ADK `LlmAgent` with `output_schema=WorkflowPatch`) given (current `Workflow` JSON + recent messages + new instruction). Editor returns a patch — a list of ops over the node/edge set — which the backend applies atomically and saves as a new `WorkflowVersion`. Full replacement is allowed when the diff is too large to be a sensible patch.
- Add **run history**: every run persists a `Run` row plus an ordered `RunEvent` stream containing exactly the JSON frames already sent over `/ws/run`. A new `GET /api/runs/{id}` returns the stream so the frontend can replay a past run on the canvas.
- Add **runtime LLM config**: a `LlmConfig` table holds provider/model/api-key/base-url. API key is encrypted with the Fernet key. Settings layer prefers an active DB row over `.env`. Activating a config evicts a cached ADK model object so the next call uses the new settings without a process restart.
- Restructure the **frontend** into a multi-page shell: sidebar nav (`Workflows`, `Credentials`, `Run history`, `Settings`), `react-router-dom` for routing, page-level layouts. Workflow detail page hosts canvas (left) + chat (top right) + run log (bottom right).
- Add a **"Run Now"** flow: a `POST /api/runs` creates a `Run` row; the frontend then opens `/ws/run` with the `run_id` and the server persists events as they stream.
- Keep `GET /api/sample-workflow`, `POST /api/workflow/generate`, and `WebSocket /ws/run` working. `/api/workflow/generate` becomes a thin wrapper that creates a new persisted workflow seeded with the planner's output and a fresh `ChatSession`.

## Capabilities

### New Capabilities

- `workflow-persistence`: SQLModel entities for `Workflow`, `WorkflowVersion`, `ChatSession`, `ChatMessage`, `Run`, `RunEvent`, `Credential`, `LlmConfig`. A `db.session` helper and a startup hook that creates tables.
- `credential-vault`: Fernet-encrypted secret storage, master-key bootstrap, masked read endpoints, lookup-by-name at action time so node `params` can carry `{ "credential": "bosch-corp-login" }` instead of plain values.
- `chat-authoring`: Multi-turn editor agent that mutates the current workflow via a structured patch (`add_node`, `remove_node`, `update_node`, `add_edge`, `remove_edge`, `set_start`) or a full replacement. Per-workflow chat session with full history.
- `run-history`: Persisted `Run` + `RunEvent` rows, run-list endpoint, run-detail endpoint with full event stream, frontend replay player that drives the existing canvas glow logic from stored events.
- `runtime-llm-config`: DB-backed LLM settings, masked CRUD endpoints, hot-reload of the cached ADK model object on activation, fallback chain (active DB row → `.env` → error).
- `platform-shell`: Sidebar navigation, `react-router-dom` routing, list pages for workflows/credentials/runs, settings page, layout primitives.

### Modified Capabilities

- `nl-workflow-planner` (from `auto-agent-mvp`): `POST /api/workflow/generate` now persists the generated workflow as a new `Workflow` row with an initial `WorkflowVersion` and a fresh `ChatSession` whose first messages are the user's description and the planner's structured output.
- `live-event-stream` (from `auto-agent-mvp`): `/ws/run` start frame additionally accepts `run_id` (when provided, the server persists each emitted event as a `RunEvent` row in order).
- `adk-model-helper` (from `auto-agent-mvp`): `get_adk_model()` becomes cache-aware. Cache key is the active `LlmConfig` row id. `invalidate_model_cache()` is called whenever a config row is activated or edited.

## Impact

- **Backend**: New `backend/app/db/` (models + session), new routers under `backend/app/routers/`, new services for chat, runs, credentials, llm-config. New dependencies: `sqlmodel`, `cryptography`. SQLite file under `backend/data/`. New file `backend/.secret_key` (gitignored).
- **Frontend**: New top-level pages and a sidebar layout. New dependencies: `react-router-dom`. Canvas and `GlowNode` are reused unchanged from the MVP; the chat panel is new.
- **Runtime**: Single Chromium singleton and one-run-at-a-time concurrency are unchanged. Persistence adds startup time of the order of milliseconds (table creation + key load).
- **Migration**: No data to migrate (the MVP is in-memory). First boot of the platform creates the DB and the secret-key file. Users who had a working `.env`-based LLM setup keep working; the `.env` is the fallback when no `LlmConfig` row is active.
- **Out of scope**: multi-user auth, cloud deployment, concurrent runs, credential sharing across machines, programmatic patches outside the chat editor.
