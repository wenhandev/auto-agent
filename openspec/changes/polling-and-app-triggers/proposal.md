## depends_on

- `triggers-and-scheduling` — hard dependency. This change adds two new `Trigger.type`s (`poll`, `app`) on top of the existing `Trigger` entity, the cron scheduler, the public webhook endpoint, and the `Run.triggered_by` enrichment.
- `integration-node-framework` — hard dependency. Poll/app triggers are descriptor-driven: a trigger reads from an integration operation (poll) or registers a provider webhook subscription (app), reusing typed credentials + auth injection.
- `items-data-model` — each polled record / received event becomes an item carried into the run as `run.context`.
- `node-context-variables` — the `run`/`trigger` token prefixes (reserved there) are realised here for trigger payloads.

Soft synergy with `core-app-integrations` (the curated apps gain trigger descriptors). No browser dependency.

## Why

`triggers-and-scheduling` added cron + generic webhook entry points. n8n's real trigger power is **app triggers**: "when a new row appears in this sheet", "when a Slack message is posted", "when a Notion DB item changes". Two mechanisms cover the long tail: **polling** (periodically call a list operation, detect new items, fire once per new item) and **native app webhooks** (subscribe to the provider's push events). Without these, automations can only be time-based or rely on a partner manually POSTing to a generic URL. This change makes the integration framework's apps event-sources, not just action targets.

## What Changes

- **New trigger type `poll`**: a descriptor-driven trigger that runs an integration *list* operation on the cron scheduler's tick, detects new records since the last poll via a **dedup key + cursor**, and enqueues one run per new record (or one run with all new records, configurable) with the record(s) as `run.context`. Poll state (`last_seen_key`, `cursor`, `last_polled_at`) is persisted per trigger.
- **New trigger type `app`**: a native webhook subscription. On enable, the framework calls the provider's "create subscription/hook" operation (descriptor-declared) pointing at our public callback; on disable, it deletes the subscription. Incoming provider events hit `POST /api/triggers/app/{trigger_id}`, are **signature-verified** per the provider's scheme (HMAC/secret/challenge), normalized into items, and enqueued as runs.
- **Trigger descriptors on integrations**: the integration descriptor schema gains an optional `triggers[]` section: each declares `kind ∈ {poll, webhook}`, the operation/subscription details, the dedup key path, the event normalization (`item_path`), and the signature-verification scheme. So an app's triggers are data, like its operations.
- **Provider handshake support**: many providers require a one-time URL verification challenge (e.g. echo a token). The app-trigger endpoint handles the descriptor-declared challenge before activation.
- **Dedup + replay safety**: polling uses a persisted `last_seen_key`/cursor so a record fires exactly once; webhook delivery is idempotent via a provider event id (dropped if already processed within a retention window).
- **Backfill control**: on first enable of a poll trigger, `on_first_poll ∈ {fire_all, fire_none, fire_latest}` controls whether existing records trigger runs (default `fire_none` to avoid a flood).
- **UI**: the "触发器" tab gains poll and app trigger editors (pick app/resource/operation for poll; "Connect & subscribe" for app, showing subscription status); run-history pills show the `poll`/`app` kind and the source record summary.

## Capabilities

### New Capabilities

- `polling-triggers`: the `poll` trigger type, descriptor `triggers[kind=poll]`, scheduler integration, dedup-key/cursor state, per-record vs batched run enqueue, and `on_first_poll` backfill control.
- `app-webhook-triggers`: the `app` trigger type, provider subscription create/delete on enable/disable, the `POST /api/triggers/app/{id}` callback, signature verification + URL-challenge handshake, event normalization to items, and idempotent delivery.

### Modified Capabilities

- `workflow-triggers` (from `triggers-and-scheduling`): `Trigger.type` gains `poll` and `app`; the entity gains poll-state and subscription-state fields; the scheduler reconciles poll jobs alongside cron jobs.
- `integration-descriptor` (from `integration-node-framework`): the descriptor schema gains an optional `triggers[]` section.
- `run-history` (from `auto-agent-platform`): `triggered_by.kind` gains `poll`/`app` with the source record/event summary.
- `node-output-interpolation` (from `node-context-variables`): the reserved `run`/`trigger` prefixes resolve to the trigger payload for triggered runs.
- `chat-authoring` / `nl-workflow-planner`: prompts note app triggers as workflow entry points.

## Impact

- **Backend**: extend `Trigger` (poll-state + subscription fields) + migration; `app/services/poll_runner.py` (tick → list op → diff → enqueue); `app/routers/triggers.py` gains the app callback + verification; subscription create/delete via the integration framework; descriptor `triggers[]` models + loader validation. ~600 LOC + ~400 LOC tests (dedup correctness, backfill modes, signature verify, challenge handshake, idempotent delivery).
- **Frontend**: poll + app trigger editors, subscription status, source-record pills. ~400 LOC.
- **Runtime**: poll triggers add list-operation calls per tick (respecting provider rate limits + a min poll interval); app webhooks are push (no polling cost).
- **Security**: app callbacks MUST verify provider signatures; the generic webhook secret remains for the `webhook` type; poll/app callbacks never expose secrets in events (framework redaction).
- **Migration**: additive trigger types + columns; existing cron/webhook triggers unaffected.
- **Out of scope**: a distributed/multi-process poller (single-process scheduler, consistent with `triggers-and-scheduling`); guaranteed exactly-once under backend crashes (best-effort idempotency within a retention window); streaming/websocket provider connections (poll + webhook only); per-tenant subscription isolation beyond what credentials provide.
