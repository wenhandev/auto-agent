## ADDED Requirements

### Requirement: Live browser session lifecycle

The system SHALL provide live browser sessions that maintain a browser context across multiple operations, with a maximum lifetime of 24 hours.

#### Scenario: Create a live session

- **WHEN** a client creates a browser session
- **THEN** a `BrowserSession` row is created with `status=live` and `expires_at = now + 24h`
- **AND** a live Playwright context is held in memory keyed by the session id

#### Scenario: Session expires after 24h

- **WHEN** a session's `expires_at` is reached
- **THEN** the reaper closes the context and sets `status=expired`
- **AND** subsequent attempts to attach a run to it fail with a clear error

#### Scenario: Idle eviction

- **WHEN** a live session has no activity for `SESSION_IDLE_MINUTES`
- **THEN** the reaper closes it and sets `status=idle`→`closed`

#### Scenario: Restart invalidates live sessions

- **WHEN** the backend restarts
- **THEN** all previously-live sessions are marked `expired` (the in-memory context is gone)

### Requirement: Attach a run to a session

The system SHALL allow a run to attach to an existing live session so the run reuses that session's cookies and page context.

#### Scenario: Run attaches to live session

- **WHEN** a run is started with `browser_session_id` of a live session
- **THEN** the run executes against that session's existing context (not a fresh one)
- **AND** the session's `last_activity_at` is updated

#### Scenario: Max live sessions enforced

- **WHEN** creating a session would exceed `MAX_LIVE_SESSIONS`
- **THEN** the request is rejected with HTTP 429 and an actionable message
