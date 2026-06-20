## ADDED Requirements

### Requirement: Workflow editor in desktop app

The desktop app SHALL host the workflow canvas, node inspector, and related authoring tools inside the main window (not requiring an external browser tab).

#### Scenario: Open workflow from local list

- **WHEN** the user selects a workflow from the desktop workflow list
- **THEN** the canvas editor opens with the same node types and edge semantics as the web editor

#### Scenario: Insert and configure nodes

- **WHEN** the user adds or edits nodes in the desktop editor
- **THEN** changes persist to the local draft store
- **AND** validation behavior matches the web editor

### Requirement: Recording entry in desktop app

The desktop app SHALL provide access to browser action recording and workflow synthesis from the main navigation.

#### Scenario: Start recording session

- **WHEN** the user starts a recording from the desktop app
- **THEN** a local browser session opens under Playwright control
- **AND** captured steps appear in the recording UI within the app

#### Scenario: Synthesize draft workflow

- **WHEN** the user stops recording and requests synthesis
- **THEN** the app produces a local draft workflow using the local LLM configuration
- **AND** opens the draft in the canvas editor for review

### Requirement: Autonomous task launcher

The desktop app SHALL allow starting autonomous-mode tasks (objective + optional start URL) from the app UI.

#### Scenario: Run autonomous task locally

- **WHEN** the user submits an autonomous objective from the desktop app
- **THEN** execution runs on the local sidecar with local browser and local LLM
- **AND** progress is shown in the run console
