## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Add `Trigger` SQLModel to `backend/app/db/models.py` — fields per design (`id`, `workflow_id` FK + index, `type` literal, `schedule_or_path`, `enabled`, `last_fired_at`, `secret_for_webhook` storing Fernet **ciphertext** bytes per Decision 3, `auth_mode: Literal["query_secret","hmac"] = "query_secret"`, `timezone`, `created_at`, `updated_at`), unique constraint `(type, schedule_or_path)` partial for `type='webhook'`. Add `triggered_by: Optional[dict] = Field(sa_column=Column(JSON))` to `Run`. Export from `__all__`.
- [x] 1.2 `[shared-contract]` Add Pydantic v2 request / response models to `backend/app/schemas_api.py`: `TriggerCreate`, `TriggerUpdate`, `TriggerOut` (with `secret_masked` only on list/detail, `secret_full` only on create / regenerate), `TriggeredBy` (discriminated union `manual | cron | webhook`), `WebhookFireResponse(run_id, status="queued")`. Extend `RunOut` / `RunListItem` to include `triggered_by: TriggeredBy`. Export from `__all__`.
- [x] 1.3 `[shared-contract]` Add `backend/app/db/migrations.py::backfill_triggered_by_on_first_run()` — sets every existing `Run.triggered_by` to `{"kind":"manual"}`; writes marker `backend/.triggered_by_backfilled`; logs one `WARNING` line. Wire into `lifespan` after `cleanup_credentials_on_first_run` and before `build_scheduler`.
- [x] 1.4 `[shared-contract]` Add `frontend/src/types-platform.ts` mirrors: `Trigger`, `TriggerKind`, `TriggerCreate`, `TriggerUpdate`, `TriggeredBy` (TS discriminated union). Extend `RunListItem` / `RunOut`.
- [x] 1.5 `[shared-contract]` Add `frontend/src/api-platform.ts` methods (stubs that throw "not implemented"): `apiClient.workflows.triggers.list / create / update / delete / regenerateSecret`. Public webhook endpoint is NOT in the API client (it is fired by external systems, not by the frontend).
- [x] 1.6 `[shared-contract]` Add `apscheduler>=3.10` to `backend/pyproject.toml` (bundles cron parsing — no `croniter` dependency needed). Append `.triggered_by_backfilled` to `.gitignore`.
- [ ] 1.7 `[shared-contract]` Smoke-check: `python -c "from app.db.models import Trigger; from app.schemas_api import TriggerCreate, TriggeredBy; print('ok')"` and `cd frontend && npx tsc --noEmit` pass.

## 2. Backend (Sibling A — `[backend]`)

- [x] 2.1 Add `backend/app/services/scheduler.py` — singleton `AsyncIOScheduler` wrapper. Exports `build_scheduler()` (called from `lifespan`), `shutdown_scheduler()`, `reconcile_trigger(trigger_id)`, `remove_job(trigger_id)`. Memory job store; misfire grace 60 s; per-job timezone from `Trigger.timezone`. Each job's coroutine sets `last_fired_at` then calls `services.runs.create_queued_run(workflow_id, triggered_by={"kind":"cron","trigger_id":...})`.
- [x] 2.2 Extend `backend/app/services/runs.py::create_queued_run` to accept an optional `triggered_by: dict | None = None` keyword. Default `{"kind":"manual"}`. Stored on the `Run` row.
- [x] 2.3 Add `backend/app/routers/triggers.py` — CRUD endpoints under `/api/workflows/{id}/triggers` (list, create, update, delete, regenerate-secret). On every mutation call `scheduler.reconcile_trigger(trigger_id)` so APScheduler stays in sync. Cron string validation via `apscheduler.triggers.cron.CronTrigger.from_crontab` — invalid syntax returns 422 with the parser's message. Webhook `schedule_or_path` validated against `^[a-z0-9-]{3,64}$`. On webhook create / regenerate-secret, encrypt the generated `secrets.token_urlsafe(24)` via the existing Fernet helper before persisting; return the plaintext exactly once in the response's `secret_full` field. `auth_mode` accepts only `"query_secret"` in this change; any other value SHALL return HTTP 422.
- [x] 2.4 Add the public webhook endpoint to `backend/app/routers/triggers.py`: `POST /api/triggers/webhook/{path}?secret=…`. Loads the `Trigger` by `(type="webhook", schedule_or_path=path)`; returns 404 if absent or disabled OR if `auth_mode != "query_secret"` (future HMAC mode rejected by this endpoint); decrypts `secret_for_webhook` via the existing Fernet key; constant-time secret compare via `secrets.compare_digest` against the decrypted plaintext; on success caps body at 64 KiB, enqueues a run with `triggered_by={"kind":"webhook","trigger_id":...,"body":...,"ip":...}`, sets `last_fired_at`, returns 202 with `WebhookFireResponse`.
- [x] 2.5 Modify `backend/app/main.py::lifespan` — after `init_db()`, `cleanup_credentials_on_first_run()`, `backfill_triggered_by_on_first_run()`, call `build_scheduler()`. On shutdown call `shutdown_scheduler()`.
- [x] 2.6 Modify `backend/app/routers/workflows.py::delete_workflow` — cascade-delete `Trigger` rows for the workflow and remove their scheduler jobs before deleting the workflow.
- [x] 2.7 Modify `backend/app/routers/runs.py` — every existing run-list / run-detail response now includes `triggered_by` (already covered by §1.2's `RunOut` extension; this task is the router serialisation wiring).
- [x] 2.8 Add unit tests `backend/tests/test_scheduler.py` — `build_scheduler` is idempotent against duplicate calls, `reconcile_trigger` adds / replaces / removes jobs, `_fire` sets `last_fired_at` BEFORE enqueueing.
- [x] 2.9 Add unit tests `backend/tests/test_triggers_router.py` — CRUD round-trip, secret never leaks in list response, duplicate path returns 409, webhook fire with wrong secret returns 401 in constant time.
- [x] 2.10 Add unit tests `backend/tests/test_webhook_endpoint.py` — body capped at 64 KiB with `truncated=true`, disabled trigger returns 404 (not 403, to avoid trigger-enumeration), happy path enqueues a `Run` with `triggered_by.kind == "webhook"`.
- [x] 2.11 Smoke-check: `pip install -e .`, `uvicorn app.main:app`, `scripts/triggers_smoke.py` creates a cron trigger for `*/1 * * * *` and a webhook trigger, fires the webhook with `curl`, confirms a queued `Run` row with the correct `triggered_by`.

## 3. Frontend (Sibling B — `[frontend]`)

- [x] 3.1 Author `frontend/src/pages/WorkflowTriggersPanel.tsx` — tab content for the workflow detail page. Top-level tab switcher between `Cron` and `Webhook` lists.
- [x] 3.2 Author the cron sub-panel: list of cron triggers + inline editor (cron string field, timezone field, enabled switch, "next 3 fires" preview computed client-side via a small `croniter`-compatible JS lib OR rendered from a server-side preview endpoint — choose the JS lib for offline editability; allowed dependency: `cron-parser`). Save / delete / disable buttons.
- [x] 3.3 Author the webhook sub-panel: list of webhook triggers with the full URL, masked secret, "复制 URL" button, "复制 curl 示例" button (renders `curl -X POST <full_url>?secret=<secret_full once-shown OR masked>` with a help tooltip explaining the secret is only visible once), "重新生成 secret" button that calls `POST .../regenerate-secret` and reveals the new `secret_full` once.
- [x] 3.4 Add the "触发器" tab to the workflow detail page (semantic role only — referred to in the spec by tab name, not by a CSS file name).
- [x] 3.5 Update the workflow detail page's tab order: existing canvas / chat / run log / 凭证 panels remain; add 触发器 to the right-hand stack as a collapsible section OR as a new sibling tab — pick whichever fits the page's current right-rail layout. The implementer decides during the in-flight shadcn migration.
- [ ] 3.6 Update `RunsListPage` (or whatever semantic role lists runs) to render a small `kind` pill next to each row: `手动` / `定时` / `Webhook`. Hover shows `triggered_by.body` summary for webhook runs.
- [x] 3.7 Add an empty-state for the cron sub-panel ("还没有定时触发器，第一次创建吗？") and for the webhook sub-panel ("还没有 Webhook 触发器").
- [x] 3.8 Smoke-check: `pnpm install && pnpm build` clean; `tsc --noEmit` clean.

## 4. Verification (parent worker)

- [ ] 4.1 `[verification]` Boot backend and confirm `lifespan` logs the backfill (or the marker-already-present skip) and the scheduler-start line ("scheduler started with N cron jobs").
- [ ] 4.2 `[verification]` `curl -X POST http://localhost:8000/api/triggers/webhook/<bad-path>?secret=x` returns 404. `curl -X POST .../webhook/<good-path>?secret=wrong` returns 401. `curl -X POST .../webhook/<good-path>?secret=right` returns 202 and a `Run` appears in the queue with `triggered_by.kind == "webhook"`.
- [ ] 4.3 `[verification]` Create a cron trigger via the UI for `*/1 * * * *`, wait 90 s, confirm at least one `Run` appears with `triggered_by.kind == "cron"`.
- [ ] 4.4 `[verification]` Disable the cron trigger via the UI, wait 90 s, confirm NO new `Run` appears.
- [ ] 4.5 `[verification]` Delete a workflow that has triggers; confirm the trigger rows are gone AND that hitting the webhook URL afterwards returns 404.
- [ ] 4.6 `[verification]` Kill the backend, restart, confirm the scheduler rebuilds from the `trigger` table and that already-deleted-then-restored triggers are NOT resurrected (no APScheduler SQL job store).
- [ ] 4.7 `[verification]` Kill all dev processes.

## 5. README

- [ ] 5.1 Update `auto-agent/README.md` — new "Triggers" section: cron, webhook URL shape, secret rotation, network exposure caveat (default bind `127.0.0.1`), missed-fire policy.
- [ ] 5.2 Document the `APScheduler` dependency and the misfire grace time.

---

## Parallel Implementation Plan

This change is small enough for 2 sibling workers. The parent writes §1 (shared contract: model, schemas, TS types, API client stubs, dependency, lifespan wiring), then forks:

### Sibling A — Backend `[backend]`

**Mission.** All scheduler + router + service work in §2.

**Owns.** `backend/app/services/scheduler.py`, `backend/app/routers/triggers.py`, `backend/app/services/runs.py` (extend), `backend/app/main.py` (lifespan wiring), all of `backend/tests/test_scheduler*.py`, `backend/tests/test_triggers_*.py`.

**Must NOT touch.** `backend/app/executor.py`, `backend/app/tools/`, `backend/app/agents/`, anything under `frontend/`, the `Workflow`/`Node`/`Edge` MVP schemas.

**Shared contract deps (§1).** `Trigger` model, `TriggerCreate/Out`, `TriggeredBy`, `backfill_triggered_by_on_first_run`.

**Independent verification.** `pip install -e .`, `uvicorn` boots, `pytest backend/tests/test_scheduler.py backend/tests/test_triggers_router.py backend/tests/test_webhook_endpoint.py` pass, `scripts/triggers_smoke.py` exits 0.

**Estimated tasks.** ~11 (2.1–2.11).

### Sibling B — Frontend `[frontend]`

**Mission.** Triggers tab on the workflow detail page + run-list pill.

**Owns.** `frontend/src/pages/WorkflowTriggersPanel.tsx` (new), cron / webhook sub-components, one wiring edit to the workflow detail page to host the new tab, one wiring edit to the run-list page to render the `kind` pill. May add `cron-parser` to `frontend/package.json`.

**Must NOT touch.** `frontend/src/components/GlowNode.*`, `frontend/src/components/WorkflowCanvas.*`, `frontend/src/store.ts`, `frontend/src/chat/`, any backend file.

**Shared contract deps (§1).** `Trigger` TS types, `apiClient.workflows.triggers.*` stubs.

**Independent verification.** `pnpm build` clean; manually open `/workflows/:id`, navigate to the new 触发器 tab, render an empty state, create a trigger (against a running Sibling-A backend), confirm the URL + secret are displayed and "复制 curl 示例" works.

**Estimated tasks.** ~8 (3.1–3.8).

### Rationale

The scheduler / webhook endpoint and the UI panel touch entirely different files. The shared contract (§1) is small (one model, one router-input schema, a handful of TS types, one new pydantic literal union). Two siblings can ship in parallel; a single integration session brings them together.
