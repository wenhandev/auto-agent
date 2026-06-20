## ADDED Requirements

### Requirement: Recording session

The system SHALL start a recording in a live browser session that captures the user's browser actions as an intent-bearing trace.

#### Scenario: Start and capture

- **WHEN** a user starts a recording and performs clicks, typing, and navigations
- **THEN** each action is captured with its perception element index, an accessible description, and a screenshot

#### Scenario: Live step list

- **WHEN** the user performs actions during recording
- **THEN** the captured steps appear in a live list in the UI

### Requirement: Sensitive input protection

The system SHALL detect sensitive fields (password, one-time-code) and never store their typed values.

#### Scenario: Password not recorded

- **WHEN** the user types into a password or 2FA field during recording
- **THEN** the value is not stored and the step is marked as a sensitive input for later credential mapping

### Requirement: Stop and persist trace

The system SHALL persist the recorded trace and its screenshots as artifacts on stop.

#### Scenario: Trace persisted

- **WHEN** the user stops a recording
- **THEN** the action trace and linked screenshots are stored and available to synthesis
