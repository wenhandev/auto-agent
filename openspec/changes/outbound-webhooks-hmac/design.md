## Context

`triggers-and-scheduling` reserved `auth_mode="hmac"` but never signed anything, and `human-in-the-loop` introduced a `services.notifications.emit(...)` no-op hook. `REFERENCES.md` recommends promoting both. Skyvern's `webhook_service.py` provides the reference patterns: `_validate_target_url` + `BlockedHost` SSRF guard and `generate_skyvern_webhook_signature` HMAC. We adopt both and add a persistent, retryable delivery queue.

## Goals / Non-Goals

**Goals:**
- Reliable outbound delivery on run state transitions: signed, retried, replayable, restart-surviving.
- SSRF-safe target URLs.
- A receiver-verifiable signature with a shipped verify helper.

**Non-Goals:**
- Payload templating / per-subscription custom bodies.
- Message-queue sinks.
- Exactly-once delivery (at-least-once + receiver idempotency via `delivery_id`).

## Decisions

### Decision 1: Persistent delivery queue, not fire-and-forget
Each intended delivery is a `WebhookDelivery` row driven to terminal by the scheduler.
- **Why**: a fire-and-forget POST loses the event if the receiver is down or the process restarts. Skyvern's "retry and replay" requires durable state.
- **Alternative rejected**: in-memory async task (lost on restart, no replay).

### Decision 2: HMAC-SHA256 over the raw body, header `X-AutoAgent-Signature: sha256=<hex>`
Sign the exact serialized bytes; receiver recomputes over the raw body.
- **Why**: matches the GitHub/Skyvern convention; signing the parsed object invites canonicalization bugs.

### Decision 3: Capped exponential backoff via APScheduler
`next_attempt_at` follows `WEBHOOK_BACKOFF_SCHEDULE` (1m,5m,30m,2h,6h) up to `WEBHOOK_MAX_ATTEMPTS`.
- **Why**: reuse the scheduler already running for cron; bounded retry storm.

### Decision 4: SSRF guard at save time AND send time
`_validate_target_url` blocks loopback/link-local/cloud-metadata ranges and non-http(s) schemes, checked when saving a subscription and again before each POST (DNS can change).
- **Why**: a subscription that resolves to `169.254.169.254` later must still be blocked.

### Decision 5: `delivery_id` in payload + header for receiver idempotency
Every payload carries a unique `delivery_id`; replays reuse the subscription/event but get a new attempt under the same logical delivery.
- **Why**: at-least-once semantics; receivers dedupe on `delivery_id`.

### Decision 6: Secrets encrypted, signature uses plaintext at send
Subscription secret stored Fernet-encrypted; decrypted only to compute the HMAC at send.
- **Why**: consistent with the credential vault's at-rest posture.

## Risks / Trade-offs

- [Receiver down for hours] → backoff to 6h × max attempts, then mark `exhausted`; replay endpoint recovers later.
- [SSRF to internal services] → dual-time URL validation + IP-range blocklist.
- [Duplicate deliveries] → documented at-least-once + `delivery_id` idempotency.
- [Restart mid-retry] → rows persisted; the scheduler reloads pending deliveries on boot.
- [Secret leakage] → encrypted at rest; signature header is a digest, not the secret.

## Migration Plan

- `create_all` makes `webhook_subscription` / `webhook_delivery`.
- Implement signing for the reserved `auth_mode="hmac"`; inbound validation reuses the compare helper.
- New settings `WEBHOOK_MAX_ATTEMPTS`, `WEBHOOK_BACKOFF_SCHEDULE`.
- The `services.notifications.emit(...)` hook body now enqueues deliveries.

## Open Questions

- Should `approval_requested` deliveries include a resume link (deep link to the approval UI)? (Lean yes; aligns with Activepieces' embedded resume URL.)
- Configurable per-subscription backoff? (Defer; one global schedule for v1.)
