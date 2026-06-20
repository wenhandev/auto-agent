## ADDED Requirements

### Requirement: Synthesise a draft workflow

The system SHALL synthesise a valid draft `Workflow` from a recorded action trace, using deterministic nodes where targets are unambiguous and vision nodes where actions are goal-shaped.

#### Scenario: Trace becomes a workflow

- **WHEN** synthesis runs on a recorded trace
- **THEN** it produces a schema-valid `Workflow` with nodes mapped from the recorded actions

#### Scenario: Goal-shaped step becomes vision node

- **WHEN** a recorded action is better expressed as an intent (e.g. search then pick a result)
- **THEN** synthesis emits a `vision_act`/`vision_navigate` node rather than a brittle selector node

### Requirement: Parameter inference

The system SHALL convert non-sensitive typed values into `{{params.<name>}}` candidates with the recorded value as default.

#### Scenario: Search term parameterised

- **WHEN** the user typed a search term during recording
- **THEN** synthesis emits a workflow parameter and references it via `{{params...}}`, defaulting to the recorded value

### Requirement: Sensitive input becomes a login node

The system SHALL convert recorded credential entry into a `login` node referencing a credential rather than literal text.

#### Scenario: Login synthesised

- **WHEN** the trace includes a sensitive credential entry
- **THEN** synthesis inserts a `login` node and prompts the user to select or create a credential

### Requirement: Reviewable draft, no auto-run

The system SHALL open the synthesised workflow as an editable draft with per-node screenshots and a seeded chat, without executing it.

#### Scenario: Draft opens for review

- **WHEN** synthesis completes
- **THEN** the draft opens in the editor with screenshots attached and a seeded refinement chat, and no run starts automatically
