## 1. Data model

- [x] 1.1 `WebhookSubscription` SQLModel (`url`, `events`, encrypted `secret`, `enabled`, `workflow_id?`)
- [x] 1.2 `WebhookDelivery` SQLModel (`attempt`, `status`, `response_code`, `next_attempt_at`, `signature`, `delivery_id`)
- [x] 1.3 Settings `WEBHOOK_MAX_ATTEMPTS=6`, `WEBHOOK_BACKOFF_SCHEDULE`

## 2. Delivery service

- [x] 2.1 Create `app/services/webhooks.py`: build payload `{event, run_id, workflow_id, status, outputs_summary, ts, delivery_id}`
- [x] 2.2 HMAC-SHA256 sign raw body → `X-AutoAgent-Signature`
- [x] 2.3 Persistent queue + capped exponential backoff via APScheduler
- [x] 2.4 Reload pending deliveries on startup
- [x] 2.5 `_validate_target_url` SSRF guard (save-time + send-time)

## 3. Event wiring

- [x] 3.1 Emit deliveries on run state transitions (`completed/failed/rejected/aborted`)
- [x] 3.2 Route the `services.notifications.emit("approval_requested", ...)` hook through delivery
- [x] 3.3 Implement inbound `auth_mode="hmac"` validation with the shared compare helper

## 4. API & replay

- [x] 4.1 CRUD `/api/v1/webhooks` (+ internal route)
- [x] 4.2 `POST /api/v1/webhooks/deliveries/{id}/replay`
- [x] 4.3 "发送测试事件" endpoint

## 5. Frontend

- [x] 5.1 Webhooks Settings page: add/edit subscriptions
- [x] 5.2 Delivery log with status + replay button
- [x] 5.3 Test-event button

## 6. SDK helper & tests

- [x] 6.1 Ship a constant-time verify helper in the SDKs + documented recipe
- [x] 6.2 Tests: signing correctness, SSRF rejection, backoff progression, replay, restart survival
