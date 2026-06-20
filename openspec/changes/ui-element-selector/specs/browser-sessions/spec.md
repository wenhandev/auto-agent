## ADDED Requirements

### Requirement: Picker lock on browser sessions

The system SHALL track an optional picker lock on live browser sessions, distinct from run attachment (`attached_run_id`).

While picker lock is active:

- The session SHALL NOT allow workflow run attachment.
- Picker API endpoints SHALL require a valid `picker_token` issued by `picker/enable`.
- `last_activity_at` SHALL be updated on picker API calls.

#### Scenario: Picker and run mutually exclusive

- **WHEN** a session has `attached_run_id` set
- **THEN** `picker/enable` SHALL return HTTP 409

#### Scenario: Picker lock expires with session

- **WHEN** a session is closed or expires
- **THEN** any active picker lock is cleared

### Requirement: Session navigate for picker context

Live browser sessions SHALL support explicit navigation via the picker API without requiring an attached workflow run.

#### Scenario: Navigate without run

- **WHEN** picker/enable is active and navigate is called
- **THEN** the session page URL changes without creating a workflow run
