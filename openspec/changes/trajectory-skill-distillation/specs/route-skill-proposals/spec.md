## ADDED Requirements

### Requirement: Persist route skill proposals

The system SHALL persist distilled route skill proposals linked to a source recording with domain, capability, url pattern, prompt, and pending status.

#### Scenario: Distill creates proposals

- **WHEN** distillation runs on a recording with two URL segments
- **THEN** the system stores one pending proposal per distilled segment

#### Scenario: Re-distill replaces pending proposals

- **WHEN** distillation runs again on the same recording
- **THEN** previous pending proposals for that recording are superseded by the new set

### Requirement: List and inspect proposals

The system SHALL list route skill proposals, filterable by source recording id.

#### Scenario: List by recording

- **WHEN** the client requests proposals for a recording id
- **THEN** the server returns all proposals for that recording ordered by creation time

### Requirement: Adopt proposal into route skill

The system SHALL allow an operator to adopt a pending proposal into the route skill store, merging into an existing skill with the same url pattern when one exists.

#### Scenario: Adopt creates new route skill

- **WHEN** the operator adopts a proposal and no route skill exists for the url pattern
- **THEN** a new route skill is created and the proposal status becomes adopted

#### Scenario: Adopt merges existing route skill

- **WHEN** the operator adopts a proposal and a route skill already exists for the url pattern
- **THEN** the existing route skill prompt is consolidated with the proposal prompt and the proposal is marked adopted

### Requirement: Dismiss proposal

The system SHALL allow an operator to dismiss a pending proposal without creating or modifying route skills.

#### Scenario: Dismiss pending proposal

- **WHEN** the operator dismisses a pending proposal
- **THEN** the proposal status becomes dismissed and no route skill is created

### Requirement: Proposals never auto-enable execution

The system SHALL NOT automatically enable adopted route skills or start workflow runs when a proposal is adopted.

#### Scenario: Adopted skill requires explicit enable

- **WHEN** a proposal is adopted into a newly created route skill
- **THEN** the route skill remains subject to the existing enabled flag and operator settings
