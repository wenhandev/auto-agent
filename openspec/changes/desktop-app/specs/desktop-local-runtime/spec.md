## ADDED Requirements

### Requirement: Embedded Python runtime sidecar

The desktop app SHALL start and supervise a local Python runtime process that hosts the existing workflow executor and Playwright browser pool.

#### Scenario: Sidecar starts on app launch

- **WHEN** the desktop app launches after successful login
- **THEN** it starts the bundled runtime sidecar process
- **AND** waits until a localhost health endpoint responds success

#### Scenario: Sidecar stops on quit

- **WHEN** the user quits the desktop app
- **THEN** the app terminates the sidecar gracefully
- **AND** any in-flight runs receive abort handling consistent with worker mode today

### Requirement: Localhost control API

The runtime sidecar SHALL expose an HTTP API bound to `127.0.0.1` only for the desktop shell to start runs, stream events, and query status.

#### Scenario: Start run from app UI

- **WHEN** the user clicks Run on a workflow in the desktop app
- **THEN** the shell calls the localhost API to start execution with the workflow payload and parameters
- **AND** run events are streamed back to the UI without requiring a separate CLI worker

#### Scenario: Cloud-dispatched run on same runtime

- **WHEN** the cloud assigns a run via the worker WebSocket while the app is open
- **THEN** the sidecar executes the run using the same executor path as app-initiated runs
- **AND** events are relayed to the cloud per existing worker protocol

### Requirement: Automatic worker WebSocket registration

When logged in, the sidecar SHALL maintain an outbound WebSocket to the cloud worker hub, equivalent to `auto-agent-worker start`.

#### Scenario: Appears in cloud Workers list

- **WHEN** the desktop app is connected
- **THEN** the machine appears online in cloud Settings → Workers with hostname and user email
- **AND** no separate CLI worker installation is required
