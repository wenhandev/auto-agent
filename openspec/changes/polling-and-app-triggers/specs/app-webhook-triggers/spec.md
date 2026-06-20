## Description

An `app` trigger registers a native webhook subscription with a provider (via a descriptor-declared subscribe operation) pointing at our callback, handles the provider's URL-verification challenge, verifies incoming event signatures, normalizes events into items, and enqueues idempotent runs carrying the event as `run.context`. Subscriptions are torn down on disable.

## User stories

- **As a workflow author**, I want my workflow to run the instant a Slack message is posted or a provider event fires, without polling.
- **As an operator**, I want incoming events cryptographically verified so a stranger cannot trigger my workflow.
- **As an operator**, I want provider retries of the same event to not double-fire my workflow.

## ADDED Requirements

### Requirement: App Trigger Subscription Lifecycle

`Trigger.type` SHALL accept `app`. On enable, the framework SHALL call the descriptor's `subscribe_operation` with the callback URL `…/api/triggers/app/{trigger_id}` and a generated `subscription_secret`, storing the returned `subscription_id`. On disable/delete, it SHALL call `unsubscribe_operation` with the stored `subscription_id`.

#### Scenario: Subscribe on enable

- **WHEN** an `app` trigger is enabled
- **THEN** the provider subscribe operation SHALL be called with our callback URL AND the returned subscription id SHALL be persisted.

#### Scenario: Unsubscribe on disable

- **WHEN** an enabled `app` trigger is disabled
- **THEN** the provider unsubscribe operation SHALL be called with the stored subscription id.

### Requirement: URL-Verification Challenge Handshake

When the descriptor declares a verification challenge, the callback SHALL respond to the provider's one-time challenge (echoing the declared token/field) before the subscription is considered active.

#### Scenario: Challenge echoed

- **WHEN** the provider POSTs a challenge `{"challenge": "abc"}` and the descriptor declares challenge verification
- **THEN** the callback SHALL respond with the challenge value `abc` and SHALL NOT enqueue a run.

### Requirement: Signature Verification

The app callback `POST /api/triggers/app/{trigger_id}` SHALL verify each event per the descriptor's `verification` scheme (HMAC over the raw body with `subscription_secret`, a shared secret, or a per-app custom verifier). An event failing verification SHALL be rejected without enqueuing a run.

#### Scenario: Valid signature accepted

- **WHEN** an event arrives with a valid HMAC signature
- **THEN** the event SHALL be normalized and a run SHALL be enqueued.

#### Scenario: Invalid signature rejected

- **WHEN** an event arrives with an invalid signature
- **THEN** the callback SHALL reject it (no run enqueued) and respond with an auth error.

### Requirement: Event Normalization And Triggered Run

A verified event SHALL be normalized via the descriptor's `event_item_path` into one or more items and enqueued through `create_queued_run` with `triggered_by.kind == "app"` (plus `trigger_id` and an event summary) and `run.context` set to the event payload.

#### Scenario: Event becomes a run

- **WHEN** a verified Slack message event arrives
- **THEN** a run SHALL be enqueued with the message available via `{{run.context...}}`.

### Requirement: Idempotent Delivery

The callback SHALL record each event's provider id (or a body hash) in a bounded store with a retention window; a duplicate within the window SHALL be acknowledged (HTTP 200) but SHALL NOT enqueue a second run.

#### Scenario: Provider retry deduped

- **WHEN** the provider re-delivers the same event id within the retention window
- **THEN** the callback SHALL return 200 AND SHALL NOT enqueue a second run.

## Out of Scope

- Exactly-once delivery across backend crashes (best-effort idempotency within the window).
- Streaming/websocket provider connections.
- Provider signature schemes beyond HMAC/shared-secret/challenge without a custom verifier.
