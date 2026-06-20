## ADDED Requirements

### Requirement: Worker session token from user login

The system SHALL issue worker session tokens with prefix `wk_sess_` when a user authenticates via the worker login endpoint. These tokens SHALL be bound to the authenticated user and org and SHALL authorize only worker control-plane operations (WebSocket connect, event upload, stream upload, LLM proxy).

#### Scenario: Login returns worker session

- **WHEN** a user posts valid credentials to `POST /api/v1/workers/login`
- **THEN** the response includes `{worker_session_token, worker_id, org_id, expires_at}`
- **AND** does not include a general-purpose API key

#### Scenario: Worker token cannot list workflows

- **WHEN** a client presents a worker session token to `GET /api/v1/workflows`
- **THEN** the system returns HTTP 403

#### Scenario: Worker token connects WebSocket

- **WHEN** a worker presents a valid `wk_sess_` token on `WSS /api/v1/workers/connect`
- **THEN** the connection is accepted and the worker becomes visible in the org Workers list

#### Scenario: Revoke worker session

- **WHEN** an org admin revokes a worker from Settings or the user logs out from the worker app
- **THEN** existing worker session tokens for that connection are invalidated
- **AND** subsequent WebSocket or proxy calls return HTTP 401

### Requirement: Optional enrollment token hashing

When admin enrollment tokens (`wk_enroll_`) are enabled, they SHALL be stored hashed with the same approach as API keys (SHA-256 of the full token, display prefix only in list responses).

#### Scenario: Enrollment token leak from DB

- **WHEN** an attacker reads the enrollment token table
- **THEN** they cannot derive usable enrollment secrets from stored hashes
