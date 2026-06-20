## ADDED Requirements

### Requirement: API key issuance and storage

The system SHALL issue API keys shown once at creation and persist only a hash plus a display prefix, never the plaintext key.

#### Scenario: Reveal-once creation

- **WHEN** an operator creates an API key
- **THEN** the full key is returned exactly once and only its `sha256` hash + prefix are stored

#### Scenario: Plaintext never retrievable

- **WHEN** the API key is read after creation
- **THEN** only the prefix is shown; the full key cannot be retrieved

### Requirement: Authenticated public routes

The system SHALL require a valid, non-revoked API key on every `/api/v1` route, accepting `Authorization: Bearer <key>` or `x-api-key`.

#### Scenario: Missing key rejected

- **WHEN** a request to `/api/v1/...` carries no key
- **THEN** the response is HTTP 401

#### Scenario: Revoked key rejected

- **WHEN** a request uses a revoked key
- **THEN** the response is HTTP 401 and `last_used_at` is not updated

#### Scenario: Valid key accepted and tracked

- **WHEN** a request uses a valid key
- **THEN** the request is authorised and the key's `last_used_at` is updated

#### Scenario: Internal frontend routes exempt

- **WHEN** the bundled frontend calls an internal `/api/...` route same-origin
- **THEN** no API key is required (the public contract is `/api/v1`)

### Requirement: Per-key rate limiting

The system SHALL rate-limit each API key and return HTTP 429 with `Retry-After` when the limit is exceeded.

#### Scenario: Limit exceeded

- **WHEN** a key exceeds `RATE_LIMIT_PER_MIN`
- **THEN** further requests receive HTTP 429 with a `Retry-After` header until the bucket refills
