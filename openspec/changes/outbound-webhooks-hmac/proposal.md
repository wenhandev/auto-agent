## depends_on

- `auto-agent-platform` — `Run` lifecycle/state transitions, `services.runs`, the FastAPI `lifespan`, persistence.
- `triggers-and-scheduling` — the inbound `Trigger` machinery and the `auth_mode="hmac"` enum value that was reserved-but-unimplemented there.
- `human-in-the-loop` (soft) — the `services.notifications.emit("approval_requested", ...)` hook this change can fan out.

Consumed by the deferred `approval-timeouts` reminders. Pairs with `public-api-and-auth` (webhook subscriptions are managed through the API too).

## Why

`auto-agent` can be *triggered* by an inbound webhook, but it cannot **call out** when something happens. Skyvern POSTs **HMAC-signed callbacks on completion, with retry and replay support for reliable orchestration**. Without outbound webhooks, an integrator must poll `GET /runs/{id}` forever to learn a run finished. `ROADMAP.md` already recommends `outbound-webhooks` + `webhook-hmac-signing`; this change merges them: a configurable-URL outbound POST on run state transitions, HMAC-signed, with retry/replay and an SSRF guard.

## What Changes

- **Subscriptions**: a `WebhookSubscription` SQLModel — `id`, `url`, `events` (subset of `{run_completed, run_failed, run_rejected, run_aborted, approval_requested}`), `secret` (for HMAC, encrypted at rest), `enabled`, `workflow_id?` (null = all workflows), `created_at`. CRUD under `/api/v1/webhooks` (and an internal UI route).
- **Delivery service** `app/services/webhooks.py`: on a subscribed event, builds a JSON payload `{event, run_id, workflow_id, status, outputs_summary, ts}`, signs it (`X-AutoAgent-Signature: sha256=<hmac>` over the raw body using the subscription secret), and POSTs it. Backed by a small persistent **delivery queue** (`WebhookDelivery` rows: `attempt`, `status`, `response_code`, `next_attempt_at`, `signature`) so deliveries survive a restart and can be retried.
- **Retry**: exponential-with-cap backoff (e.g. 1m, 5m, 30m, 2h, 6h) up to `WEBHOOK_MAX_ATTEMPTS` (default 6). Each attempt is a `WebhookDelivery` row; the schedule is driven by the existing APScheduler.
- **Replay**: `POST /api/v1/webhooks/deliveries/{id}/replay` re-sends a past delivery (new attempt, same payload + signature recomputation), for when the receiver was down.
- **SSRF guard**: a `_validate_target_url` (block loopback/link-local/metadata IPs, scheme allowlist `https`/`http`) borrowed from Skyvern's `webhook_service.py` pattern; on validation failure the subscription save is rejected.
- **Signature verification helper**: documented receiver-side recipe + a shared constant-time compare snippet shipped in the SDKs.
- **UI**: a "Webhooks" Settings page (or per-workflow tab) to add/test subscriptions ("发送测试事件"), view recent deliveries with status, and replay failed ones.

## Capabilities

### New Capabilities

- `outbound-webhooks`: the `WebhookSubscription` + `WebhookDelivery` entities, the delivery service, the persistent retry queue with backoff, replay, the SSRF guard, the subscription/delivery API + UI.
- `webhook-hmac-signing`: HMAC-SHA256 signing of every outbound payload, the `X-AutoAgent-Signature` header, the documented verification recipe, and the SDK verify helper.

### Modified Capabilities

- `run-history` (from `auto-agent-platform`): run state transitions emit subscribed webhook events via the delivery service.
- `workflow-triggers` (from `triggers-and-scheduling`): the reserved `auth_mode="hmac"` is now implemented for the *signing* side; inbound HMAC validation reuses the same compare helper.
- `platform-shell`: a new "Webhooks" Settings surface.

## Impact

- **Backend**: new service + two models + a router; reuses APScheduler for retry scheduling and the Fernet key for secret storage. New dependency: none (httpx already present from `expanded-node-library`). Tests: signing correctness, SSRF rejection, retry backoff progression, replay, restart-survival of pending deliveries.
- **Frontend**: Webhooks Settings page with test + delivery log + replay.
- **Runtime**: deliveries are async + queued; a slow/broken receiver never blocks a run. Backoff bounds retry load.
- **Migration**: `create_all` makes the two tables. New settings `WEBHOOK_MAX_ATTEMPTS=6`, `WEBHOOK_BACKOFF_SCHEDULE`.
- **Out of scope**: per-event payload templating; mTLS to receivers; webhook fan-out to message queues; receiver-side dedupe beyond the `delivery_id` we include (idempotency is the receiver's job, documented).
