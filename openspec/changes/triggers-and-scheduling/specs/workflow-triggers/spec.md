## Description

A trigger is a persisted rule that creates a `Run` row for a workflow without a human button click. Two trigger types are in scope: `cron` (fired by a backend-resident scheduler) and `webhook` (fired by an inbound HTTP POST against a public per-trigger URL). A `manual` type is reserved for symmetry but produces no scheduler behaviour and no public endpoint.

Triggers are owned by exactly one workflow. Multiple triggers per workflow are allowed. Triggers do not bypass the existing FIFO run queue — every fire goes through `services.runs.create_queued_run(...)` and is subject to the same queueing, single-Chromium-tab, and abort semantics as a manual `POST /api/runs`.

## User stories

- **As an operator**, I configure a cron expression for a workflow so that it runs on a schedule without me clicking "Run Now".
- **As an external system** (a CRM, a CI job, a webhook fan-out service), I POST a JSON body to a per-trigger URL and have a workflow run enqueued, with the body persisted on the resulting `Run` row.
- **As an operator**, I see every triggered run in the same run-history list, with a `kind` pill identifying the trigger source.
- **As an operator**, I can disable a trigger without deleting it, and re-enable it later without touching the schedule or URL.
- **As an operator**, I can regenerate a webhook secret when I suspect it leaked, without changing the URL path.

## ADDED Requirements

### Requirement: Trigger entity per workflow

The platform SHALL persist triggers in a `trigger` table. Each row SHALL belong to exactly one workflow via `workflow_id` (foreign key, indexed) and SHALL carry exactly one `type ∈ {"cron","webhook","manual"}`. Webhook rows SHALL additionally carry an `auth_mode ∈ {"query_secret","hmac"}` defaulting to `"query_secret"`; only `"query_secret"` is accepted in this change. The pair `(type, schedule_or_path)` SHALL be globally unique for `type="webhook"`. `secret_for_webhook` SHALL store Fernet ciphertext (encrypted with the existing `backend/.secret_key`); the plaintext value SHALL exist only in process memory at create / regenerate-secret / webhook-fire time. Deleting a workflow SHALL cascade to its triggers and remove the corresponding scheduler jobs in the same operation.

#### Scenario: Multiple triggers per workflow

- **WHEN** an operator creates a cron trigger and a webhook trigger for the same workflow
- **THEN** the API SHALL accept both, the trigger list endpoint SHALL return both, and each SHALL operate independently.

#### Scenario: Webhook path globally unique

- **WHEN** the operator creates a webhook trigger with `schedule_or_path="orders"` and another workflow already has a webhook trigger with the same path
- **THEN** the create endpoint SHALL return HTTP 409 with `{"detail":"webhook path already in use"}` and SHALL NOT insert a row.

#### Scenario: Workflow delete cascades

- **WHEN** the operator deletes a workflow that has two triggers
- **THEN** the two `trigger` rows SHALL be removed in the same transaction AND the scheduler SHALL no longer have jobs for them AND a subsequent webhook POST against the deleted webhook path SHALL return HTTP 404.

### Requirement: Cron scheduler reconciles from the trigger table

The backend SHALL run an in-process `AsyncIOScheduler` started in the FastAPI `lifespan`. On startup it SHALL load every row where `enabled=True AND type="cron"` and SHALL register one job per row. On every trigger CRUD mutation the scheduler SHALL be reconciled — adding, updating, or removing the corresponding job — so the change takes effect without a backend restart. The scheduler SHALL use APScheduler's `CronTrigger.from_crontab(expr, timezone=trigger.timezone)`.

#### Scenario: Cron job fires and enqueues a run

- **WHEN** the cron expression matches and the scheduler tick reaches the registered job
- **THEN** the scheduler SHALL set `trigger.last_fired_at = now()` AND SHALL call `services.runs.create_queued_run(workflow_id, triggered_by={"kind":"cron","trigger_id":...})` which inserts a `Run` row with `status="queued"`.

#### Scenario: Disable cron trigger

- **WHEN** the operator sets `enabled=False` on a cron trigger via `PUT /api/workflows/{id}/triggers/{trigger_id}`
- **THEN** the scheduler SHALL remove the corresponding job within the same request handler AND no further cron fires SHALL occur for that trigger until it is re-enabled.

#### Scenario: Misfire dropped

- **WHEN** the backend was down at the scheduled fire time and remains down for longer than 60 s past that fire time
- **THEN** the missed tick SHALL be dropped and only the next scheduled fire SHALL produce a run.

### Requirement: Public webhook endpoint per trigger

The backend SHALL expose `POST /api/triggers/webhook/{path}?secret=<secret>` as a public endpoint (no `Authorization` header required). The endpoint SHALL look up a `Trigger` where `type="webhook" AND schedule_or_path=path AND enabled=True AND auth_mode="query_secret"`; return HTTP 404 if no such row exists (independent of secret correctness, to avoid trigger-enumeration leaks); decrypt the stored Fernet-encrypted `secret_for_webhook` once per request; validate the supplied secret in constant time via `secrets.compare_digest` against the decrypted plaintext and return HTTP 401 on mismatch; cap the incoming JSON body at 64 KiB; enqueue a run with `triggered_by={"kind":"webhook","trigger_id":...,"body":<parsed body>,"ip":<remote addr>}` (with `"truncated":true` added if the body exceeded the cap); set `trigger.last_fired_at = now()`; and return HTTP 202 with `{"run_id":...,"status":"queued"}`.

#### Scenario: Happy path webhook fire

- **WHEN** an external system POSTs `{"order_id":"O-42"}` to `/api/triggers/webhook/orders?secret=<correct>` and the trigger exists and is enabled
- **THEN** the response SHALL be HTTP 202 with the new `run_id`, a `Run` row SHALL exist with `status="queued"` and `triggered_by={"kind":"webhook","trigger_id":...,"body":{"order_id":"O-42"},"ip":...}`, AND `trigger.last_fired_at` SHALL be updated.

#### Scenario: Wrong secret

- **WHEN** the POST carries a secret that differs from the stored one
- **THEN** the response SHALL be HTTP 401, no `Run` row SHALL be created, AND the comparison SHALL use `secrets.compare_digest` (constant-time).

#### Scenario: Disabled webhook trigger

- **WHEN** the POST targets a webhook path whose trigger has `enabled=False`
- **THEN** the response SHALL be HTTP 404 (NOT 403), preserving the property that an attacker cannot distinguish disabled from missing paths.

#### Scenario: Oversized body

- **WHEN** the POST body exceeds 64 KiB
- **THEN** the body SHALL be truncated to 64 KiB before parsing, the resulting `triggered_by.body` SHALL carry `"truncated":true`, AND the run SHALL still be enqueued.

### Requirement: Run rows carry `triggered_by`

Every `Run` row SHALL carry a `triggered_by: dict | null` JSON column. New rows produced by `POST /api/runs` SHALL default to `{"kind":"manual"}`. Cron-fired rows SHALL be `{"kind":"cron","trigger_id":...}`. Webhook-fired rows SHALL be `{"kind":"webhook","trigger_id":...,"body":...,"ip":...}`. The field SHALL be included on every `RunSummary` and `RunOut` response.

#### Scenario: Manual run defaults

- **WHEN** the operator clicks "Run Now" and the frontend calls `POST /api/runs`
- **THEN** the resulting `Run.triggered_by` SHALL be `{"kind":"manual"}`.

#### Scenario: Backfill on first boot

- **WHEN** the backend starts for the first time after this change ships
- **THEN** every pre-existing `Run` row whose `triggered_by IS NULL` SHALL be updated to `{"kind":"manual"}` once, a marker file `backend/.triggered_by_backfilled` SHALL be written, AND subsequent boots SHALL NOT re-run the backfill.

### Requirement: Secret rotation

`POST /api/workflows/{id}/triggers/{trigger_id}/regenerate-secret` SHALL replace `secret_for_webhook` with a freshly generated `secrets.token_urlsafe(24)` value (encrypted with the existing Fernet key before persistence), return the new secret in full exactly once in the response (`secret_full` field), and SHALL NOT change the trigger's `schedule_or_path`, `auth_mode`, or any other field. Subsequent GETs SHALL return `secret_masked` only (`"abcd…XYZ"`, first 4 + ellipsis + last 3 chars).

#### Scenario: Regenerate returns secret once

- **WHEN** the operator calls regenerate-secret
- **THEN** the response SHALL include `secret_full` AND a subsequent `GET /api/workflows/{id}/triggers/{trigger_id}` SHALL NOT include `secret_full` (only `secret_masked`).

### Requirement: Cron expression validated at write time

Cron triggers SHALL be validated by parsing `schedule_or_path` through `apscheduler.triggers.cron.CronTrigger.from_crontab(expr, timezone=timezone)` at create / update time. Invalid expressions SHALL return HTTP 422 with the parser's error message in `detail`. The `timezone` field SHALL accept any IANA timezone name; invalid names SHALL also return HTTP 422.

#### Scenario: Bad cron string

- **WHEN** the operator submits `schedule_or_path="not a cron"`
- **THEN** the response SHALL be HTTP 422 AND no row SHALL be inserted.

### Requirement: Triggered runs visible in run history

The existing run-list and run-detail responses SHALL include `triggered_by`. The frontend run-list page SHALL render a small pill identifying the kind (`手动` / `定时` / `Webhook`). Hovering the pill on webhook-fired runs SHALL surface a short summary of `triggered_by.body`.

#### Scenario: Pill renders for each kind

- **WHEN** the run list contains one manual, one cron, and one webhook run
- **THEN** three different pills SHALL render, AND the webhook pill SHALL show the body summary on hover.

## API contract

| Method | Path | Request | Response | Notes |
| --- | --- | --- | --- | --- |
| `GET` | `/api/workflows/{id}/triggers` | — | `TriggerOut[]` | ordered by `created_at` desc; secrets masked |
| `POST` | `/api/workflows/{id}/triggers` | `TriggerCreate` | `TriggerOut` (with `secret_full` for webhook type) | 422 on bad cron / bad path; 409 on path collision |
| `PUT` | `/api/workflows/{id}/triggers/{trigger_id}` | `TriggerUpdate` | `TriggerOut` (masked secret) | reconciles scheduler within the request |
| `DELETE` | `/api/workflows/{id}/triggers/{trigger_id}` | — | 204 | removes scheduler job if cron |
| `POST` | `/api/workflows/{id}/triggers/{trigger_id}/regenerate-secret` | — | `TriggerOut` (with new `secret_full`) | webhook only; 400 if cron |
| `POST` | `/api/triggers/webhook/{path}?secret=<>` | arbitrary JSON | `{run_id, status:"queued"}` HTTP 202 | public; 404 / 401 per Requirements |

`TriggerCreate` shape:

```json
{
  "type": "cron" | "webhook" | "manual",
  "schedule_or_path": "0 9 * * MON-FRI" | "orders" | null,
  "timezone": "Asia/Shanghai",
  "enabled": true
}
```

`TriggerOut` shape:

```json
{
  "id": "trg_…",
  "workflow_id": "wf_…",
  "type": "webhook",
  "schedule_or_path": "orders",
  "auth_mode": "query_secret",
  "timezone": "Asia/Shanghai",
  "enabled": true,
  "last_fired_at": "2026-…" | null,
  "secret_masked": "abcd…XYZ" | null,
  "secret_full": "<one-shot>" | null,
  "created_at": "2026-…",
  "updated_at": "2026-…"
}
```

`TriggeredBy` shape (added to `Run`):

```json
{ "kind": "manual" }
{ "kind": "cron",    "trigger_id": "trg_…" }
{ "kind": "webhook", "trigger_id": "trg_…", "body": {...} | null, "ip": "203.0.113.5", "truncated"?: true }
```

## Data model

```python
class Trigger(SQLModel, table=True):
    __tablename__ = "trigger"
    id: str = Field(primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True)
    type: Literal["cron", "webhook", "manual"]
    schedule_or_path: Optional[str] = None
    timezone: str = "Asia/Shanghai"
    enabled: bool = True
    last_fired_at: Optional[datetime] = None
    # Fernet ciphertext (encrypted with backend/.secret_key); plaintext is never persisted.
    secret_for_webhook: Optional[bytes] = None
    # Forward-compatible auth selector. Only "query_secret" is implemented in this change;
    # a future "webhook-hmac" change introduces "hmac" without endpoint route churn.
    auth_mode: Literal["query_secret", "hmac"] = "query_secret"
    created_at: datetime
    updated_at: datetime
    __table_args__ = (
        UniqueConstraint(
            "type", "schedule_or_path",
            name="uq_trigger_webhook_path",
            sqlite_where=text("type='webhook'"),
        ),
    )
```

`Run` gains:

```python
triggered_by: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```

## Out of Scope

- Distributed scheduling (multi-process / multi-host APScheduler).
- Retry of missed cron ticks beyond APScheduler's misfire grace time.
- Calendar-aware skip dates (holidays, business-hours windows).
- HMAC body signing for webhooks (the `auth_mode="hmac"` literal is reserved on the schema for a future "webhook-hmac" change; this change only implements `"query_secret"`).
- Per-trigger IP allowlists.
- Cross-workflow trigger fan-out (one trigger firing N workflows).
- Throttling / debouncing cron fires when the queue is deep.
- A separate `trigger_fire_event` audit table (the `triggered_by` field on `Run` is the audit trail).
