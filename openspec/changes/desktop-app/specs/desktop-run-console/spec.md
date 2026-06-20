## ADDED Requirements

### Requirement: In-app run console

The desktop app SHALL provide a run console showing active and recent runs executed on this device.

#### Scenario: View active run

- **WHEN** a run is executing on the local sidecar
- **THEN** the run console shows status, current node, and a scrolling event log
- **AND** the user can abort the run from the app

#### Scenario: Live browser preview

- **WHEN** livestream is enabled for a run on this device
- **THEN** the run console displays a live viewport preview within the app window
- **AND** behavior matches the web LiveStream panel semantics

### Requirement: Local run history

The desktop app SHALL list run history for executions on this machine, including app-initiated and cloud-dispatched runs.

#### Scenario: Filter to this device

- **WHEN** the user opens run history in the desktop app
- **THEN** the list defaults to runs whose `worker_id` or local sidecar identity matches this machine

#### Scenario: Open run detail and replay

- **WHEN** the user selects a completed run
- **THEN** the app shows event timeline, outputs, artifacts, and failure reasons
- **AND** replay UX is consistent with web run detail where applicable

### Requirement: Optional cloud run sync

When online, the desktop app MAY upload run metadata and events to the cloud so team members can view runs in the web UI.

#### Scenario: Sync after local run

- **WHEN** a local run completes and cloud connectivity is available
- **THEN** run events are persisted to the cloud using the existing worker event relay protocol
- **AND** the run appears in org run history
