## ADDED Requirements

### Requirement: Desktop app as primary worker client

The platform SHALL treat the desktop application as the primary path for worker registration; the CLI worker SHALL be documented as an advanced headless variant.

#### Scenario: New user onboarding

- **WHEN** documentation describes how to run workflows on a local machine
- **THEN** it directs users to install the desktop app first
- **AND** mentions CLI worker only for CI or headless servers

### Requirement: Worker session shared with desktop sidecar

The worker session token obtained at desktop login SHALL authenticate the embedded sidecar's outbound WebSocket identically to CLI `auto-agent-worker login`.

#### Scenario: Single session per app instance

- **WHEN** the desktop app is logged in
- **THEN** exactly one worker connection is registered for that user/machine pair
- **AND** duplicate CLI worker connections with the same machine_id are rejected or superseded per existing cloud rules

### Requirement: Registration subject to admin approval

Desktop and CLI worker registration SHALL honor org `desktop_client_policy` and per-worker `approval_status` as defined in `desktop-client-authorization`.

#### Scenario: Pending worker may connect but not execute

- **WHEN** a desktop app connects with `approval_status=pending`
- **THEN** the WebSocket connection MAY stay open for heartbeats and status polling
- **AND** the cloud SHALL NOT assign runs until the device is approved
