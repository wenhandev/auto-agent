## ADDED Requirements

### Requirement: HMAC-signed payloads

The system SHALL sign every outbound webhook body with HMAC-SHA256 using the subscription secret and include the digest in an `X-AutoAgent-Signature: sha256=<hex>` header.

#### Scenario: Signature present and correct

- **WHEN** a webhook is delivered
- **THEN** the request carries `X-AutoAgent-Signature` equal to HMAC-SHA256 of the exact raw body under the subscription secret

#### Scenario: Receiver can verify

- **WHEN** a receiver recomputes the HMAC over the raw body with the shared secret
- **THEN** a constant-time comparison with the header value succeeds for an authentic payload

### Requirement: Delivery idempotency id

The system SHALL include a unique `delivery_id` in every payload and header so receivers can dedupe at-least-once deliveries.

#### Scenario: Duplicate delivery deduped by receiver

- **WHEN** the same logical delivery is sent twice (retry/replay)
- **THEN** both carry the same `delivery_id` enabling receiver-side dedupe

### Requirement: Reused signing for inbound hmac triggers

The system SHALL implement the previously-reserved inbound `auth_mode="hmac"` validation using the same compare helper.

#### Scenario: Inbound hmac trigger validated

- **WHEN** an inbound webhook trigger configured with `auth_mode="hmac"` receives a signed request
- **THEN** the system validates the signature with a constant-time compare before enqueuing the run
