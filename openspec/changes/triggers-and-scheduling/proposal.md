## depends_on

- `auto-agent-mvp` — workflow schema, executor, action set.
- `auto-agent-platform` — `Run` table, run scheduler with FIFO queue per workflow, FastAPI `lifespan` startup hook, `WorkflowVersion.current_version_id` pointer.

No dependency on `per-workflow-credentials` (credentials are unrelated to triggers); no dependency on any other change in the current batch.

## Why

Today a workflow only runs when a human clicks "Run Now" on its detail page. That is fine for authoring but blocks the most common automation request: "run this every weekday at 9 AM" and "kick this off when our CRM posts here". The platform already has a persistent `Run` table, a FIFO queue per workflow, and an executor that doesn't care who created the run row — every piece needed to add non-manual entry points is in place.

This change adds two new ways to create a `Run` row:

1. **Cron triggers**: a backend-resident scheduler reads enabled cron triggers at startup and re-evaluates them on a tick. When a cron expression matches, the scheduler enqueues a run for the workflow exactly as the manual "Run Now" path does.
2. **Webhook triggers**: a public `POST /api/triggers/webhook/{path}?secret=…` endpoint matches the path against an enabled webhook trigger, validates the secret, and enqueues a run whose `triggered_by` carries the incoming JSON body as run-context. Later nodes can read this body via the `{{nodes...}}` interpolation introduced in `node-context-variables`, but the current change does NOT require that — the body lands on the `Run` row regardless and is available to the executor as `run.context_json`.

Both paths go through the existing `services.runs.create_queued_run(...)`, so behaviour around queueing, abort, and the `RunEvent` stream is unchanged. Triggers are a thin layer above the run scheduler, not a parallel execution path.

## What Changes

- **Data**: new `Trigger` SQLModel — `id`, `workflow_id` (FK), `type ∈ {"cron","webhook","manual"}`, `schedule_or_path: str`, `enabled: bool`, `last_fired_at: datetime | null`, `secret_for_webhook: str | null`, `created_at`, `updated_at`. A `"manual"` row is allowed for symmetry with the UI but is a no-op for the scheduler (manual runs continue to come from `POST /api/runs`).
- **Run table**: add `triggered_by: dict | null` (JSON column) capturing `{kind: "manual"|"cron"|"webhook", trigger_id?: str, body?: dict, ip?: str}`. Existing rows are migrated to `{"kind":"manual"}` at startup via an idempotent helper.
- **API**: CRUD `/api/workflows/{id}/triggers`, plus the public `POST /api/triggers/webhook/{path}` endpoint.
- **Scheduler**: a new `app/services/scheduler.py` registers an APScheduler `AsyncIOScheduler` in the FastAPI `lifespan`. On startup it reads every `enabled=True` cron trigger and registers a job. On trigger CRUD the scheduler is reconciled — adds / removes / updates the corresponding job. On backend shutdown it stops cleanly.
- **UI**: a new "触发器" tab on the workflow detail page. The cron editor accepts a cron string with inline preview ("next 3 fires at …"). The webhook editor shows the full URL with copy button, a masked secret with reveal-once and "重新生成 secret" controls, and example `curl`. Triggered runs appear in the run history list with a pill identifying their `kind`.

## Capabilities

### New Capabilities

- `workflow-triggers`: trigger entity, CRUD endpoints, public webhook endpoint, cron scheduler reconciliation, `Run.triggered_by` enrichment, UI tab.

### Modified Capabilities

- `run-history` (from `auto-agent-platform`): `Run` rows now carry `triggered_by`; `RunSummary` / `RunOut` include the field; UI run-list shows a `kind` pill. The existing `POST /api/runs` path defaults to `{"kind":"manual"}`.
- `platform-shell` (from `auto-agent-platform`): the workflow detail page grows a "触发器" tab alongside the existing canvas / chat / run log / 凭证 panels.

## Impact

- **Backend**: new dependency `APScheduler` (>=3.10, async support). One new router (`backend/app/routers/triggers.py`), one new service (`backend/app/services/scheduler.py`), one new model (`Trigger`), one alteration to `Run` (`triggered_by` column). The scheduler is owned by the FastAPI process; on a `uvicorn --reload` development restart it is fully re-built from `Trigger` rows, so cron jobs survive restarts without any persistence beyond the table itself.
- **Frontend**: a new "触发器" tab inside the workflow detail page. No new top-level pages; sidebar navigation unchanged. New API client methods on `apiClient.workflows.triggers`.
- **Runtime**: webhook endpoint is publicly reachable. The secret query parameter is the only auth (a deliberate single-user POC choice; see Design open trade-offs).
- **Migration**: `triggered_by` defaults to `{"kind":"manual"}` for pre-existing `Run` rows via a one-time backfill in the lifespan (marker file `backend/.triggered_by_backfilled`, same pattern as `per-workflow-credentials`).
- **Out of scope**: distributed scheduler (single-process AsyncIOScheduler only), retry queues for failed cron pickups, calendar-aware skip dates (holidays), webhook HMAC signing (the secret is a shared query-string token).
