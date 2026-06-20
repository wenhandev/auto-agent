## ADDED Requirements

### Requirement: Webhook subscriptions

The system SHALL let operators subscribe a URL to a set of run events, optionally scoped to one workflow, with an encrypted signing secret.

#### Scenario: Create a subscription

- **WHEN** an operator subscribes a URL to `run_completed` and `run_failed`
- **THEN** a `WebhookSubscription` is stored with the secret encrypted at rest

#### Scenario: Scoped subscription

- **WHEN** a subscription sets `workflow_id`
- **THEN** only events for that workflow are delivered to it

### Requirement: Persistent delivery with retry

The system SHALL deliver subscribed events via a persistent queue that retries with capped exponential backoff and survives restarts.

#### Scenario: Delivered on completion

- **WHEN** a run reaches `completed` and a matching subscription exists
- **THEN** a `WebhookDelivery` is enqueued and POSTed to the URL

#### Scenario: Retry on failure

- **WHEN** a delivery POST fails
- **THEN** the system schedules the next attempt per the backoff schedule until `WEBHOOK_MAX_ATTEMPTS`, then marks it `exhausted`

#### Scenario: Survives restart

- **WHEN** the backend restarts with pending deliveries
- **THEN** the scheduler reloads and continues retrying them

### Requirement: Replay

The system SHALL allow replaying a past delivery.

#### Scenario: Replay a failed delivery

- **WHEN** an operator replays a delivery whose receiver was down
- **THEN** the payload is re-sent as a new attempt under the same logical delivery id

### Requirement: SSRF protection

The system SHALL validate target URLs at save time and before each send, rejecting loopback, link-local, cloud-metadata addresses, and non-http(s) schemes.

#### Scenario: Block internal target

- **WHEN** a subscription URL resolves to a blocked address (e.g. `169.254.169.254`)
- **THEN** the save is rejected and no delivery is attempted
