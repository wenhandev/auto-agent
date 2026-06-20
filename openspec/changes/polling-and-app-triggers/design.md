## Context

`triggers-and-scheduling` gives us a `Trigger` entity, an `AsyncIOScheduler`, a public webhook endpoint, and `Run.triggered_by`. `integration-node-framework` gives descriptor-driven operations + typed credentials. This change combines them: polling triggers run a list operation on a tick and fire on new records; app triggers register native provider webhooks and fire on pushed events. Both are descriptor-declared, so an app's triggers are data.

## Goals / Non-Goals

**Goals**
- `poll` triggers with correct dedup (fire each record once) and backfill control.
- `app` triggers with provider subscription lifecycle, signature verification, and URL-challenge handshake.
- Descriptor `triggers[]` so app triggers are data, not code.
- Reuse the existing scheduler, run-enqueue path, and `triggered_by` enrichment.

**Non-Goals**
- Distributed/multi-process polling.
- Exactly-once across backend crashes (best-effort idempotency).
- Streaming/websocket provider connections.

## Decisions

### Decision 1: Two new `Trigger.type`s + state fields

```python
# extends triggers-and-scheduling's Trigger
type: Literal["cron","webhook","manual","poll","app"]
# poll state
poll_app: str | None; poll_resource: str | None; poll_operation: str | None
poll_dedup_path: str | None        # JSONPath-lite to a stable record id
poll_cursor: str | None            # provider cursor (when supported)
last_seen_key: str | None          # highest/most-recent processed dedup key
poll_mode: Literal["per_record","batched"] = "per_record"
on_first_poll: Literal["fire_all","fire_none","fire_latest"] = "fire_none"
min_poll_interval_s: int = 60
# app state
app_name: str | None; subscription_id: str | None; subscription_secret: str | None
```

### Decision 2: Descriptor `triggers[]`

```python
# added to IntegrationDescriptor
class TriggerDescriptor(BaseModel):
    name: str; label: str
    kind: Literal["poll","webhook"]
    # poll:
    list_operation: str | None      # which operation to call
    dedup_path: str | None          # record id path
    item_path: str | None           # array of records
    cursor_param: str | None        # how to pass the cursor back
    # webhook:
    subscribe_operation: str | None  # create-subscription op
    unsubscribe_operation: str | None
    event_item_path: str | None      # array/object in the event payload
    verification: VerificationSpec | None  # hmac/secret/challenge
```

The loader validates that referenced operations exist on the app.

### Decision 3: Poll runner

```mermaid
flowchart LR
  tick["scheduler tick"] --> guard["min_poll_interval gate"]
  guard --> call["integration list_operation (with cursor)"]
  call --> diff["new = records with dedup_key > last_seen_key / not in cursor window"]
  diff --> enq["per_record: one run each | batched: one run with all"]
  enq --> save["persist last_seen_key + cursor + last_polled_at"]
```

The poll runner is registered with the same `AsyncIOScheduler` as cron jobs, reconciled on trigger CRUD. Dedup: if the provider exposes a monotonic id/timestamp, compare against `last_seen_key`; otherwise keep a bounded set of recently-seen ids. Records that are new fire runs with the record as `run.context`; state is persisted AFTER successful enqueue so a crash re-polls rather than silently drops (at-least-once, deduped on next pass by the seen set).

### Decision 4: App webhook lifecycle

- **Enable**: call the descriptor's `subscribe_operation` with our callback URL `…/api/triggers/app/{trigger_id}` and a generated `subscription_secret`; store the returned `subscription_id`.
- **Handshake**: if the provider sends a one-time challenge (descriptor `verification.challenge`), the callback echoes the token before activation.
- **Event**: `POST /api/triggers/app/{trigger_id}` verifies the signature per `verification` (HMAC over the raw body with `subscription_secret`, or a shared secret, or provider-specific), normalizes via `event_item_path` into items, and enqueues a run with the event as `run.context`.
- **Disable/delete**: call `unsubscribe_operation` with `subscription_id`.

### Decision 5: Idempotent delivery

Each incoming event's provider id (descriptor-declared path, else a hash of the body) is recorded in a bounded `processed_events` store with a retention window; a duplicate within the window is acknowledged (HTTP 200) but not re-enqueued. This tolerates provider retries.

### Decision 6: `run`/`trigger` token realisation

`node-context-variables` reserved `{{run.*}}` and `{{trigger.*}}`. For triggered runs this change resolves them: `{{run.context.<path>}}` = the record/event payload; `{{trigger.kind}}`, `{{trigger.id}}`, `{{trigger.headers.<h>}}` (for app webhooks). For manual/cron runs, `run.context` is `{}` (or cron metadata). The reserved-prefix error from `node-context-variables` is replaced by real resolution once this change ships.

### Decision 7: Reuse the run-enqueue path

Both trigger types call `services.runs.create_queued_run(...)` with `triggered_by={kind, trigger_id, record_summary|event_summary}` and `context_json=<payload>`, exactly like the existing cron/webhook paths. No parallel execution path.

## Risks / Trade-offs

- **Provider rate limits / poll storms**: `min_poll_interval_s` + the scheduler's single-process serialization bound call volume; descriptors can declare a recommended interval. Documented.
- **Missed events between polls**: polling can miss records deleted before the next poll; app webhooks avoid this. We document poll as eventually-consistent and recommend app webhooks where available.
- **Signature scheme variety**: providers differ (Slack v0 HMAC, GitHub sha256, Notion token). The `VerificationSpec` covers HMAC + shared-secret + challenge; exotic schemes use a per-app `custom.py` verifier hook (same escape hatch as operations).
- **State growth**: the seen-id set and `processed_events` store are bounded with retention windows to avoid unbounded growth.
- **First-poll flood**: `on_first_poll=fire_none` default prevents firing on the entire backlog when a poll trigger is first enabled.

## Migration Plan

- Additive `Trigger` columns + two new `type` values; migration adds nullable columns.
- New `processed_events` bounded store (table or capped structure).
- Land after `triggers-and-scheduling` + `integration-node-framework`; `core-app-integrations` apps gain `triggers[]` as a fast-follow.

## Open Questions

- Persist `processed_events` in SQLite vs an in-memory LRU? Leaning a small SQLite table with a TTL sweep for crash-resilience; revisit if it grows hot.
