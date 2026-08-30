## ADDED Requirements

### Requirement: Atomize trace into URL-scoped segments

The system SHALL split a recorded action trace into segments grouped by normalized page URL, dropping incidental scroll and wait noise.

#### Scenario: Multi-page recording produces multiple segments

- **WHEN** a stopped recording contains navigations to two distinct normalized URLs
- **THEN** distillation produces at least two segments, each with its events and url pattern

#### Scenario: Scroll and wait events are ignored

- **WHEN** a trace contains scroll or wait events
- **THEN** atomization excludes them from segment event lists

### Requirement: Classify segment capability

The system SHALL assign each segment a capability slug derived from its event shapes (e.g. login, search, form interaction).

#### Scenario: Sensitive fill classified as login

- **WHEN** a segment contains a sensitive fill event
- **THEN** the capability slug indicates login-style authentication

#### Scenario: Generic clicks classified as interaction

- **WHEN** a segment contains only non-sensitive clicks and fills
- **THEN** the capability slug defaults to a generic interaction label

### Requirement: Distill route prompt from segment

The system SHALL convert each segment into a human-readable numbered instruction prompt suitable for route skill injection, without literal secret values.

#### Scenario: Prompt lists actionable steps

- **WHEN** a segment contains click and fill events with descriptions
- **THEN** the distilled prompt references those descriptions as ordered steps

#### Scenario: Sensitive values omitted

- **WHEN** a segment includes sensitive fill events
- **THEN** the prompt describes credential entry without storing typed secrets

### Requirement: Distill recording on demand

The system SHALL expose an API to distill a stopped recording into workflow graph output and route skill proposals.

#### Scenario: Distill stopped recording

- **WHEN** the client POSTs distill on a stopped recording
- **THEN** the response includes segment metadata, route skill proposals, and a workflow graph

#### Scenario: Active recording rejected

- **WHEN** the client POSTs distill on an active recording
- **THEN** the server returns HTTP 409

### Requirement: Optional LLM workflow distillation

When an LLM is configured and the client requests LLM distillation, the system SHALL attempt LLM-based workflow graph generation and fall back to rule-based synthesis on validation failure.

#### Scenario: LLM unavailable uses rules

- **WHEN** no LLM API key is configured
- **THEN** workflow distillation uses the existing rule-based graph builder

#### Scenario: LLM invalid output falls back

- **WHEN** LLM distillation returns invalid workflow JSON
- **THEN** the system falls back to rule-based synthesis without failing the request
