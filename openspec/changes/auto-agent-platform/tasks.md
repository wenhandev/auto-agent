## 1. Shared contract (parent worker — front-loaded blockers before forking siblings)

These tasks define the API and data shapes that all three siblings depend on. The parent SHALL complete them before spawning sibling agents.

- [x] 1.1 `[shared-contract]` Author `backend/app/db/__init__.py`, `backend/app/db/session.py` — engine pointing at `backend/auto_agent.db`, `get_session()` FastAPI dependency, `init_db()` that calls `SQLModel.metadata.create_all(engine)`.
- [x] 1.2 `[shared-contract]` Author `backend/app/db/models.py` containing every SQLModel entity (`Workflow`, `WorkflowVersion`, `ChatSession`, `ChatMessage`, `Run` with `status ∈ {queued, running, completed, failed, aborted}` and `queued_at/started_at/finished_at`, `RunEvent` with all event types incl. `run_queued | run_aborted`, `Credential` with ciphertext blob, `LlmConfig` with `api_key_ciphertext`).
- [x] 1.3 `[shared-contract]` Author `backend/app/db/crypto.py` — `load_or_create_key()`, `encrypt()`, `decrypt()`; resolves key from `AUTO_AGENT_SECRET_KEY` env var, then `backend/.secret_key`, then generates a fresh key (writing a sibling `.secret_key.README`).
- [x] 1.4 `[shared-contract]` Author `backend/app/schemas_api.py` with Pydantic v2 request / response models for the full API surface, including: `PatchOp` discriminated union (six ops); `RunCreate`/`RunOut`/`RunListItem`/`RunReplayResponse` with `RunStatus ∈ {queued, running, completed, failed, aborted}`; `WSStartFrame` (extended with `run_id`); `WSAbortFrame` (`{type:"abort", run_id?}`); `WSEvent` with `run_id` on every event; `CredentialCreate/Update/Out/ListItem` with masked fields only; `LlmConfigUpsert/Out/Effective` with `api_key_masked`.
- [x] 1.5 `[shared-contract]` Author `frontend/src/types-platform.ts` — TS mirrors of every API request / response shape; `import type` re-export of MVP `Workflow`/`WorkflowNode`/`WorkflowEdge` from `./types`; `RunStatus` includes `queued` and `aborted`; `WSAbortFrame` present.
- [x] 1.6 `[shared-contract]` Author `frontend/src/api-platform.ts` — typed `apiClient` skeleton with stubbed methods for `workflows`, `chat`, `runs` (incl. `abort`), `credentials`, `llmConfig`. Implementations throw `"not implemented"` — siblings fill in.
- [x] 1.7 `[shared-contract]` Author `frontend/src/routes.ts` — exports `ROUTES` constants and `routePath` helper. Siblings B and C navigate using these constants, never raw strings.
- [x] 1.8 `[shared-contract]` Wire `init_db()` into `backend/app/main.py` via FastAPI lifespan (clearly tagged "platform iteration scaffolding"). Add `sqlmodel`, `cryptography`, `python-multipart` to `backend/pyproject.toml`. Append `*.db`, `.secret_key*` patterns to `.gitignore`.
- [x] 1.9 `[shared-contract]` Smoke-check: `python -c "from app.db.models import Workflow, Run, Credential, LlmConfig; from app.schemas_api import WorkflowCreate; print('ok')"` and `cd frontend && npx tsc --noEmit` pass; first boot of backend creates `auto_agent.db` and `.secret_key`.

> Note: the credential-interpolation utility (`{{cred.<name>.<field>}}` resolver) is intentionally **not** in the shared contract — only the token syntax is contractual. The implementation lands in Sibling A as a stub at `backend/app/services/credential_interpolation.py`.

## 2. Backend platform (Sibling A — `[backend-platform]`)

Owned by Sibling A. All under `backend/app/` except where noted.

- [ ] 2.1 Add `sqlmodel` and `cryptography` to `backend/pyproject.toml`. Add `data/` to gitignore.
- [ ] 2.2 Add `app/services/crypto.py` — Fernet key bootstrap (env / file / generate), `encrypt`, `decrypt`, masked helpers (`mask_secret`, `mask_api_key`).
- [ ] 2.3 Add `app/services/llm_settings.py` — `effective_settings()`, `get_adk_model_cached()` (`lru_cache(maxsize=1)` keyed by fingerprint), `invalidate_model_cache()`. Make existing `app/agents/model.py::get_adk_model()` delegate here.
- [ ] 2.4 Add `app/services/patch.py` — `apply_patch(current: Workflow, ops: list[PatchOp]) -> Workflow` with re-validation; raises `PatchValidationError` on any failure.
- [ ] 2.5 Add `app/services/credentials.py` — `resolve_params(params, session)` interpolation pass for `{{cred.name.field}}` tokens; per-field merge for partial updates.
- [ ] 2.6 Add `app/services/runs.py` — `create_queued_run(workflow_id, version_id?)`, `transition_run(run_id, status, ...)`, `record_event(run_id, payload)`, FIFO scheduler that promotes the oldest `queued` row when no `running` row exists, abort plumbing (sets cancel flag, drives `queued → aborted` shortcut, drives `running → aborted` through the executor's cleanup hook); persistence-failure isolation (`try/except/log`).
- [ ] 2.7 Add `app/agents/editor.py` — `EditorAgent` ADK `LlmAgent` with `output_schema=EditorResponse`, system prompt (patches preferred over full replacement, op-set listing, vocabulary rule). Reuses `get_adk_model_cached()`.
- [ ] 2.8 Add `app/routers/workflows.py` — `GET/POST/PUT/DELETE /api/workflows`, `GET /api/workflows/{id}`, `GET /api/workflows/{id}/versions`.
- [ ] 2.9 Add `app/routers/chat.py` — `GET /api/chat/{session_id}`, `POST /api/chat/{session_id}/messages` (runs editor turn, applies patch via `services.patch`, writes new `WorkflowVersion`).
- [ ] 2.10 Add `app/routers/credentials.py` — `GET/POST/PUT/DELETE /api/credentials`, 409 on delete if referenced by any workflow's current version.
- [ ] 2.11 Add `app/routers/runs.py` — `GET /api/runs`, `POST /api/runs` (always enqueues; returns `{run_id, status:"queued"}`), `GET /api/runs/{id}`, `POST /api/runs/{id}/abort` (mirrors the `{type:"abort"}` WS frame; works for both queued and running rows).
- [ ] 2.12 Add `app/routers/llm_config.py` — full CRUD + `/activate` + `/effective`, calls `invalidate_model_cache()` on activate / update-of-active / delete-of-active.
- [ ] 2.13 Extend `app/main.py` — include the five new routers and extend the `/ws/run` handler to (a) accept `{type:"start", run_id}` (wait for scheduler pickup, load workflow version, persist events via `services.runs`), (b) accept `{type:"abort", run_id?}` (set cancel flag, drive run to `aborted`), (c) on socket disconnect mid-run also drive `running → aborted`. The startup hook (table create + Fernet key load) is already wired in §1.8.
- [ ] 2.14 Modify `app/main.py::generate_workflow` — after the planner returns, create `Workflow` + `WorkflowVersion` + `ChatSession` + seed messages; wrap response `{workflow_id, chat_session_id, workflow}`.
- [ ] 2.15 Modify `app/executor.py::run_workflow` — accept an optional `record_event` callback that mirrors each emit to the run-events service; default is `None` (ephemeral runs unchanged).
- [ ] 2.16 Modify `app/tools/actions.py` — call `services.credentials.resolve_params(params, session)` once per action invocation; on `ValueError`, raise so the executor emits `node_failed`.
- [ ] 2.17 Add unit tests for `services/patch.py`: each op happy path + each failure mode (unknown id, type-changes-after-merge, orphaned `start_id`).
- [ ] 2.18 Add unit tests for `services/credentials.py::resolve_params`: known token, unknown name, unknown field, recursive interpolation refusal.
- [ ] 2.19 Add unit tests for `services/crypto.py`: round-trip encrypt / decrypt, env-var override of file, mode 0600 on POSIX (skip on Windows).
- [ ] 2.20 Add unit tests for `services/llm_settings.py`: DB wins over env, cache invalidation on activate, refuse partial DB row.
- [ ] 2.21 Smoke-check: `pip install -e .`, `uvicorn app.main:app`, then run a tiny script that hits every new endpoint and confirms 200 / clean DB row.

## 3. Frontend platform shell (Sibling B — `[frontend-shell]`)

Owned by Sibling B. All under `frontend/src/` except where noted.

- [ ] 3.1 Add `react-router-dom` to `frontend/package.json`. Add `data/` etc. to gitignore. (`pnpm install` step deferred to verification.)
- [ ] 3.2 Author `frontend/src/main.tsx` — `RouterProvider` wrapping `Shell`.
- [ ] 3.3 Author `frontend/src/shell/Shell.tsx` and `Shell.css` — sidebar + `<Outlet/>` layout, brand title link to `/workflows`.
- [ ] 3.4 Author `frontend/src/shell/Sidebar.tsx` — four nav entries with `NavLink` highlighting.
- [ ] 3.5 Author `frontend/src/pages/WorkflowsListPage.tsx` — calls `apiClient.listWorkflows`, renders table, "New workflow" modal (reuses existing `NLInput` for the generate path; calls `POST /api/workflow/generate` then navigates to `/workflows/:id`).
- [ ] 3.6 Author `frontend/src/pages/WorkflowDetailPage.tsx` — three-pane skeleton with placeholder slots. Mounts existing `<WorkflowCanvas/>`. Slots for chat panel (filled by Sibling C) and run log (existing `<RunLog/>`).
- [ ] 3.7 Add "Run Now" button + WS lifecycle in `WorkflowDetailPage`: `POST /api/runs` → `startRun(workflow, run_id)` (reuses `ws.ts` after a tiny modification to send `run_id` when present — see shared contract change in 1.5 if needed).
- [ ] 3.8 Author `frontend/src/pages/CredentialsPage.tsx` — list + create/edit/delete modals; never pre-fills plaintext on edit.
- [ ] 3.9 Author `frontend/src/pages/RunsListPage.tsx` — list runs (filter by `?workflow_id=` query param), each row links to `/runs/:id`.
- [ ] 3.10 Author `frontend/src/pages/RunReplayPage.tsx` — fetches `/api/runs/{id}`, renders the existing `WorkflowCanvas`, drives `store.applyEvent(payload_json)` in order. Speed controls: instant / 1× / 2× (1× caps inter-event wait at 2 s, never replays `wait` node delays).
- [ ] 3.11 Author `frontend/src/pages/SettingsPage.tsx` — LLM config CRUD UI, "Currently in use" banner from `/api/llm-config/effective`.
- [ ] 3.12 Author `frontend/src/pages/NotFoundPage.tsx`.
- [ ] 3.13 Author `frontend/src/platformStore.ts` — zustand: sidebar collapsed, last opened workflow id; small.
- [ ] 3.14 Add `frontend/src/App.tsx` redirect → routes file; remove top-bar globals it used to own (moved into `WorkflowDetailPage`).
- [ ] 3.15 Style work — keep MVP dark theme, BUT do not edit any file under `frontend/src/components/`. New CSS lives under `shell/` and `pages/`.
- [ ] 3.16 Smoke-check: `pnpm install && pnpm build` (or `tsc --noEmit` + `vite build`) succeeds.

## 4. Frontend chat authoring (Sibling C — `[frontend-chat]`)

Owned by Sibling C. Touches only the chat panel and the slot it mounts into.

- [ ] 4.1 Author `frontend/src/chat/ChatPanel.tsx` and `ChatPanel.css` — message list + composer (textarea + send button). Renders user / assistant bubbles with markdown.
- [ ] 4.2 Author `frontend/src/chat/useChatReducer.ts` — local state machine: idle, sending, error. Optimistically appends user message; on success, appends assistant message and dispatches `setWorkflow(workflow)` if the response includes a new version.
- [ ] 4.3 Author `frontend/src/chat/api.ts` — thin wrappers over `apiClient.getChat` and `apiClient.postChatMessage` (defined in the shared contract).
- [ ] 4.4 Author `frontend/src/chat/PatchPreview.tsx` — given an assistant message that carries `patch_json`, renders a one-line summary per op (e.g. `+ node n7 (click "购物车")`, `~ node n3.params.value`). On hover, shows the corresponding node id highlighted on the canvas (via `useStore.getState().selectNode(id)`).
- [ ] 4.5 Mount `<ChatPanel session_id={chat_session_id}/>` inside `WorkflowDetailPage`'s top-right slot. The only edit to a Sibling-B file is this single mount line.
- [ ] 4.6 Handle the error case where the editor returned no version (validation failure): show the error block inline in the assistant bubble with a "Retry" button that re-sends the user's last message.
- [ ] 4.7 Smoke-check: `tsc --noEmit` clean, and a manual end-to-end: open a workflow, send "add a node to click the cart", confirm a new node appears on the canvas and the chat shows the patch summary.

## 5. Verification (parent worker — after siblings merge)

- [ ] 5.1 `[verification]` Boot backend: `pip install -e .`, `playwright install chromium` if not already installed, `uvicorn app.main:app --port 8000`. Confirm `backend/data/auto_agent.db` and `backend/.secret_key` are created.
- [ ] 5.2 `[verification]` `curl http://localhost:8000/api/health` returns `{"ok":true}`. `curl http://localhost:8000/api/llm-config/effective` returns `{source:"env", ...}` on a fresh DB with `.env` configured.
- [ ] 5.3 `[verification]` Boot frontend: `pnpm install && pnpm dev`. Verify Vite serves on 5173 and the sidebar renders with all four entries.
- [ ] 5.4 `[verification]` Generate-flow: open `/workflows`, create from description, confirm a workflow appears, navigate to detail, run it, confirm canvas glow and run log show six node pairs, confirm a `Run` row exists in the runs list afterwards.
- [ ] 5.5 `[verification]` Chat-flow: on the detail page, send a follow-up like "在结尾加一个等待 2 秒的节点", confirm the editor returns a new version, canvas updates, chat panel shows the patch summary.
- [ ] 5.6 `[verification]` Credentials: create a `bosch-login` credential with fields `{username, password}`, manually edit a workflow's `fill` node to use `{{cred.bosch-login.password}}`, run it, confirm the plaintext is NEVER in any API response or log line.
- [ ] 5.7 `[verification]` LLM-config swap: in `/settings`, create a second `LlmConfig` row pointing at a different model, activate it, immediately fire a chat turn, confirm the response actually came from the newly active model (model id surfaced in a debug header or visible in the editor's metadata; if absent, confirm `GET /api/llm-config/effective` returns the new row).
- [ ] 5.8 `[verification]` Replay: open `/runs/:id` for a past run, run the replay at 1× and instant, confirm glow sequence matches the original.
- [ ] 5.9 `[verification]` Encrypted-at-rest: `sqlite3 backend/data/auto_agent.db "select encrypted_blob from credential limit 1"` returns opaque bytes; the plaintext SHALL NOT appear in `select * from credential` or `select * from llmconfig`.
- [ ] 5.10 `[verification]` Backwards compatibility: `GET /api/sample-workflow` still returns the original six-node `Workflow` shape with HTTP 200, and `WebSocket /ws/run` with the ephemeral `{type:"start", workflow}` frame still runs without touching the DB.
- [ ] 5.11 `[verification]` Kill both processes after verification.

## 6. README and final summary

- [ ] 6.1 Update `auto-agent/README.md` to reflect the platform layout: SQLite location, `.secret_key` bootstrap, Settings page for LLM config, chat-authoring loop, run history.
- [ ] 6.2 Document `AUTO_AGENT_SECRET_KEY` env var, the consequence of losing `.secret_key`, and the gitignore policy.
- [ ] 6.3 Document deferred features (auth, parallel run execution, theming, pagination). Note that concurrent run queueing and run abort ARE in this iteration.

---

## Parallel Implementation Plan

After tasks 1.1–1.7 land on `main` (the parent worker writes them first because every sibling imports from them), the parent forks three sibling agents in parallel. The cut below maximizes parallelism by isolating the chat panel from both the backend and the rest of the shell.

### Sibling A — Backend platform `[backend-platform]`

**Mission.** Implement every backend endpoint and service required by the four other specs (`workflow-persistence`, `credential-vault`, `chat-authoring`, `run-history`, `runtime-llm-config`) plus the executor / generate-endpoint changes. No frontend code.

**Owns (read/write):**
- `backend/app/db/` (already created in 1.1–1.2; extends if needed)
- `backend/app/routers/workflows.py`, `chat.py`, `credentials.py`, `runs.py`, `llm_config.py`
- `backend/app/services/crypto.py`, `llm_settings.py`, `patch.py`, `credentials.py`, `runs.py`
- `backend/app/agents/editor.py`
- `backend/app/main.py` (extend only — wiring + `/ws/run` persistence path)
- `backend/app/agents/model.py` (collapse to delegate to `llm_settings.get_adk_model_cached`)
- `backend/app/executor.py` (add `record_event` callback)
- `backend/app/tools/actions.py` (call `resolve_params`)
- `backend/pyproject.toml`, `backend/.gitignore`
- All `backend/tests/`

**Must NOT touch:**
- Anything under `frontend/`.
- `backend/app/schemas.py` (the MVP `Workflow`/`Node`/`Edge` shapes are locked).
- `backend/app/sample.py` (sample workflow stays as-is).
- `backend/app/agents/planner.py`, `app/agents/fuzzy.py`, `app/agents/extractor.py` (no behavioural changes; they still receive the same model from the cache).
- `backend/app/tools/browser.py` (singleton unchanged).

**Shared contract dependencies (from §1):** `backend/app/db/models.py`, `backend/app/schemas_api.py`.

**Verification on its own:** `pip install -e .`, `uvicorn` boots; pytest passes (services + a router smoke test); a tiny `httpx` script hits every new endpoint and asserts 200 paths plus the queue/abort lifecycle (`POST /api/runs` returns `queued`, second `POST /api/runs` also returns `queued`, `POST /api/runs/{id}/abort` drives queued → aborted). No frontend needed.

**Estimated task count:** ~21 implementation tasks (2.1–2.21) plus the editor-mode system prompt and tests.

### Sibling B — Frontend platform shell `[frontend-shell]`

**Mission.** Build the sidebar shell, the page routes, and all list/detail pages except the chat panel. Mount existing canvas + run log inside the workflow detail page. Wire the "Run Now" flow end-to-end. Build the settings, credentials, runs-list, and runs-replay pages.

**Owns (read/write):**
- `frontend/src/main.tsx`, `frontend/src/App.tsx`
- `frontend/src/shell/` (new directory: `Shell.tsx`, `Sidebar.tsx`, `Shell.css`)
- `frontend/src/pages/` (new directory: every page listed in §3)
- `frontend/src/platformStore.ts` (new)
- `frontend/src/ws.ts` (small extension: accept `run_id`)
- `frontend/package.json`, `frontend/vite.config.ts` (only if router demands a tweak)

**Must NOT touch:**
- `frontend/src/components/GlowNode.tsx`, `GlowNode.css`, `WorkflowCanvas.tsx`, `RunLog.tsx`, `RunLog.css`, `NodeInspector.tsx`, `NodeInspector.css`, `ResultPanel.tsx`, `ResultPanel.css`.
- `frontend/src/store.ts` (the canvas store stays as-is; pages call `setWorkflow` / `applyEvent` from it).
- `frontend/src/types.ts` (MVP `Workflow`/`Node`/`Edge` types are locked).
- `frontend/src/chat/` (owned by Sibling C — leave a single import-and-mount line as the only Sibling-B touchpoint there).
- Any backend file.

**Shared contract dependencies (from §1):** `frontend/src/api/client.ts`, `frontend/src/api/types.ts`, `frontend/src/routes.ts`.

**Verification on its own:** `pnpm install && pnpm build` clean; `tsc --noEmit` clean. A manual flow against a stubbed `apiClient` (or a running Sibling-A backend) shows: sidebar nav works, workflows list loads, credentials CRUD works, runs list + replay drives the canvas without the chat panel mounted.

**Estimated task count:** ~16 (3.1–3.16).

### Sibling C — Frontend chat authoring `[frontend-chat]`

**Mission.** Build the multi-turn chat panel, its reducer, its API integration, and patch visualization on the canvas. Touches `WorkflowDetailPage` only for the single mount line.

**Owns (read/write):**
- `frontend/src/chat/` (new directory: `ChatPanel.tsx`, `useChatReducer.ts`, `api.ts`, `PatchPreview.tsx`, `ChatPanel.css`)
- One line in `frontend/src/pages/WorkflowDetailPage.tsx` (the `<ChatPanel/>` mount) — agreed upfront so Sibling B leaves a `{/* chat panel */}` placeholder.

**Must NOT touch:**
- Anything in `frontend/src/shell/` or `frontend/src/pages/` except the agreed mount line.
- `frontend/src/components/`.
- `frontend/src/store.ts` (chat dispatches `setWorkflow` and `selectNode` via the existing public API only).
- Any backend file.

**Shared contract dependencies (from §1):** `frontend/src/api/client.ts`, `frontend/src/api/types.ts` (specifically `ChatMessageOut`, `EditorResponse`, `PatchOp`, `PostChatMessageResponse`).

**Verification on its own:** `tsc --noEmit` clean; mount the panel inside a tiny ad-hoc test page or against a running Sibling-A backend; send a message, confirm an assistant reply appears, confirm the canvas updates when the server returns a new workflow version. The replay page and other pages are not required to be functional for Sibling C to declare done.

**Estimated task count:** ~7 (4.1–4.7).

### Rationale for this cut

- The chat panel is the only frontend work that needs to know about ADK / editor semantics, so isolating it as Sibling C lets the rest of the frontend (mostly forms + lists + a router) proceed in parallel without waiting on the patch / editor API shapes to stabilize.
- The backend is its own sibling because (a) it owns the longest dependency chain (Fernet bootstrap → DB → services → routers → executor wiring) and (b) it can be verified independently with curl / a tiny httpx script, with no frontend at all.
- The shared-contract block (§1) is small and front-loadable: types, routes, API client, DB models, Pydantic API schemas. Once these are in, all three siblings can start without further synchronization until the verification step.

### Estimated totals

- Shared contract (§1): 7 tasks
- Sibling A backend (§2): 21 tasks
- Sibling B shell (§3): 16 tasks
- Sibling C chat (§4): 7 tasks
- Verification (§5): 11 tasks
- README (§6): 3 tasks
- **Grand total: ~65 tasks**
