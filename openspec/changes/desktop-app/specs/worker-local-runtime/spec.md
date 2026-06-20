## ADDED Requirements

### Requirement: App-initiated local execution

The worker local runtime SHALL support runs started by the desktop app localhost API in addition to runs dispatched from the cloud via WebSocket frames.

#### Scenario: App-initiated run does not require cloud dispatch

- **WHEN** the user runs a local draft from the desktop app without cloud enqueue
- **THEN** the sidecar executes the workflow locally
- **AND** optionally uploads events to cloud if online and configured

#### Scenario: Same executor semantics

- **WHEN** a run is app-initiated versus cloud-dispatched
- **THEN** node execution, browser pool behavior, and error handling are identical
