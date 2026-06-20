## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Add `Worker` SQLModel — include `environment_status`, `environment_checks_json`, `capabilities_json`; other fields unchanged. Optional `WorkerEnrollmentToken`. Add to `Run`: `execution_mode`, `worker_id`, `worker_pool`, `worker_assigned_at`.
- [x] 1.2 `[shared-contract]` Add Pydantic models: `WorkerLoginRequest`, `WorkerLoginResponse`, `WorkerOut` (includes `user_email`, `hostname`, `status`, `active_runs`, `tags`, `environment_status`, `environment_checks`), optional enrollment token models; extend `RunCreate` / `RunOut` with worker fields. Export from `__all__`.
- [x] 1.3 `[shared-contract]` Add migration helpers; wire into `lifespan`.
- [x] 1.4 `[shared-contract]` Add `frontend/src/types-platform.ts` mirrors including `Worker` with `user_email`, `hostname`, `status: online | offline`.
- [x] 1.5 `[shared-contract]` Add API client stubs: `workers.list`, `workers.revoke`, optional `workers.createEnrollmentToken`; extend `runs.create` with worker fields.
- [x] 1.6 `[shared-contract]` Add settings: `WORKER_HEARTBEAT_INTERVAL_SEC=30`, `WORKER_HEARTBEAT_TIMEOUT_SEC=90`, optional `EXECUTION_BACKEND=full|control_plane_only`. Document in `.env.example`.
- [x] 1.7 `[shared-contract]` Smoke-check: model/schema imports and `npx tsc --noEmit` pass.

## 2. Runtime engine extraction (parent worker)

- [x] 2.1 `[backend-runtime]` Extract `RuntimeEngine.execute(...)` from `backend/app/services/runs.py::_drive_run` body (begin_run → run_workflow → cleanup) into `backend/app/services/runtime_engine.py`. Cloud `_drive_run` delegates to it unchanged.
- [x] 2.2 `[backend-runtime]` Add injectable hooks: `emit_fn`, `llm_client_factory`, `abort_event` — worker process overrides LLM factory to call cloud proxy.
- [x] 2.3 `[backend-runtime]` Unit tests: `RuntimeEngine` with stubbed browser + stub emit produces same event sequence as legacy `_drive_run` for linear workflow.

## 3. Cloud worker hub (Sibling A — `[backend]`)

- [x] 3.1 Add `backend/app/services/worker_hub.py` — track online workers, heartbeats, assigned runs, send/receive WebSocket frames.
- [x] 3.2 Add `backend/app/routers/v1/workers.py` — `POST /login` (email+password → `wk_sess_` token + worker row upsert), `GET /` list for org, `POST /{id}/revoke`; optional enrollment token CRUD for admins; worker auth dependency.
- [x] 3.3 Add `WSS /api/v1/workers/connect` — accept `wk_sess_` token; on connect set worker `online` and broadcast to org (optional SSE for Workers page live refresh).
- [x] 3.4 Branch worker-mode runs in `services/runs.py` to `worker_hub.assign(run)` instead of `_drive_run`.
- [x] 3.5 Extend dispatcher — assign only when worker `environment_status` is `ready`, or `degraded` when run does not need missing capabilities.
- [x] 3.6 Implement event ingest from worker frames — validate ownership + seq, call `_persist_event` + `_fanout`.
- [x] 3.7 Implement abort/resume relay from existing `request_abort` and approvals service to worker hub.
- [x] 3.8 Add `POST /api/v1/internal/llm/complete` worker-auth-only LLM proxy route delegating to `get_adk_model_cached()`.
- [x] 3.9 Optional: skip Playwright lifespan when `EXECUTION_BACKEND=control_plane_only`.
- [x] 3.10 Unit tests: registration, heartbeat timeout, env-aware assignment, abort relay, seq rejection, LLM proxy auth matrix.

## 4. Livestream relay (Sibling A — `[backend]`)

- [x] 4.1 Extend `backend/app/services/livestream.py` with `ingest_frame(run_id, frame)` for worker-uploaded JPEGs.
- [x] 4.2 On viewer connect/disconnect for worker runs, send `stream_subscribe` / `stream_unsubscribe` to assigned worker via hub.
- [x] 4.3 Unit tests: worker frame ingested → viewer receives frame; `stream_ended` on terminal run.

## 5. Worker package (Sibling B — `[worker]`)

- [x] 5.0 Add `worker/preflight.py` — checks: `playwright_installed`, `chromium_binary`, `chromium_smoke`, `cloud_reachable`, `headed_display`, `disk_space`, `memory`; aggregate to `ready|degraded|not_ready`; CLI `auto-agent-worker doctor`.
- [x] 5.1 Add `worker/` package with entry point `auto-agent-worker = worker.cli:main`.
- [x] 5.2 Implement login UI / `auto-agent-worker login` — collect URL + email + password; call `POST /api/v1/workers/login`; persist token to `~/.auto-agent-worker/credentials`.
- [x] 5.3 Implement `auto-agent-worker start` — run preflight first; block connect on `not_ready`; if saved session valid, connect with env payload; else prompt login; heartbeat includes environment summary.
- [x] 5.4 Handle `execute_run`, `abort`, `resume_run` frames.
- [x] 5.5 Upload `run_event` and `stream_frame` frames.
- [x] 5.6 Implement `logout` — close WSS, delete saved credentials.
- [ ] 5.7 Optional: `connect --enrollment-token` for headless admin path. *(deferred — documented in worker/README.md)*
- [x] 5.8 Integration test: login → connect → worker appears in `GET /api/v1/workers` as online.

## 6. Frontend (Sibling C — `[frontend]`)

- [x] 6.1 Add Settings page **Workers** — table: display name / hostname, user email, status pill, **environment badge** (就绪/降级/未就绪) with tooltip showing failed checks, tags, active runs, last seen; Revoke per row.
- [x] 6.2 Auto-refresh or poll Workers list every 10s so user sees machine appear shortly after worker login.
- [x] 6.3 Extend run dialog on workflow detail — execution mode toggle (cloud/worker), worker pool selector, optional worker pin.
- [x] 6.4 Run list/detail — show execution mode badge and assigned worker name; show `waiting_for_worker` / `waiting_for_ready_worker` queue reason.
- [x] 6.5 Smoke-check: `npm run build` clean.

## 7. Verification (parent worker)

- [ ] 7.1 `[verification]` Cloud-only deploy with `EXECUTION_BACKEND=control_plane_only` starts without Playwright. *(code in place; manual deploy not run)*
- [ ] 7.2 `[verification]` User logs in on worker app → within 10s cloud Settings → Workers shows machine **在线** with correct email and hostname.
- [ ] 7.3 `[verification]` User logs out on worker → cloud shows **离线**.
- [ ] 7.4 `[verification]` Enqueue worker-mode sample workflow; Chromium opens on worker machine; run completes; events replay in cloud UI.
- [ ] 7.5 `[verification]` Worker without Chromium: `doctor` fails, worker does not connect, cloud does not assign runs.
- [ ] 7.6 `[verification]` After `playwright install chromium`, worker becomes `ready` and accepts runs.
- [ ] 7.7 `[verification]` Kill worker mid-run; cloud marks run failed after heartbeat timeout.
- [x] 7.8 `[verification]` Cloud-mode run still works unchanged (regression).

## 8. README

- [x] 8.1 Update root `README.md` — Worker install flow: download → login → appear in cloud Workers page → run workflow on worker.
- [x] 8.2 Add `worker/README.md` — install, `doctor`, login, start, tags, headed/headless, profile/credential local setup.

---

## Parallel Implementation Plan

Three sibling workers after the parent lands §1–§2.

### Sibling A — Backend `[backend]`

**Mission.** §3 worker hub, dispatcher branch, LLM proxy, §4 livestream relay.

**Do NOT touch:** `worker/` package, frontend.

### Sibling B — Worker `[worker]`

**Mission.** §5 worker CLI and local runtime.

**Do NOT touch:** cloud dispatcher UI, frontend.

**Depends on:** §2 `RuntimeEngine` API frozen by parent.

### Sibling C — Frontend `[frontend]`

**Mission.** §6 Workers settings and run enqueue UX.

**Do NOT touch:** backend, worker package.

**Depends on:** §1.4–§1.5 types and API stubs only (can mock until §3 lands).
