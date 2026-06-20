## ADDED Requirements

### Requirement: Declared workflow parameters

The system SHALL allow a workflow to declare typed input parameters (`name`, `type`, optional `label`/`required`/`default`/`description`), stored in the versioned workflow definition.

#### Scenario: Declare a parameter

- **WHEN** an author adds a parameter `search_term: string (required)` to a workflow
- **THEN** it is persisted in the workflow's `parameters` and appears in the Run-Now form

### Requirement: Pre-run validation

The system SHALL validate supplied parameter values against declared types before enqueuing a run, filling defaults for omitted optionals and rejecting missing required values.

#### Scenario: Missing required parameter rejected

- **WHEN** a run is requested without a value for a required parameter that has no default
- **THEN** the run is rejected before starting with an actionable validation error

#### Scenario: Default applied

- **WHEN** an optional parameter with a default is omitted
- **THEN** the default value is used

#### Scenario: Type mismatch rejected

- **WHEN** a `number` parameter is supplied a non-numeric value
- **THEN** the run is rejected with a type error

### Requirement: Parameter token resolution

The system SHALL resolve `{{params.<name>}}` to the run's parameter value in the chained interpolation pass (order: params, nodes, credentials).

#### Scenario: Node reads a parameter

- **WHEN** a node param contains `{{params.search_term}}` and the run supplied `search_term="shoes"`
- **THEN** the node receives `shoes`

### Requirement: Secret parameters masked

The system SHALL mask `secret`-typed parameter values in persisted run inputs, events, and traces.

#### Scenario: Secret not leaked

- **WHEN** a run supplies a `secret` parameter
- **THEN** `Run.parameters_json` and any trace show the masked value, never the plaintext

### Requirement: Run inputs across entry points

The system SHALL accept parameter values from manual runs, the public API, and triggers, persisting the resolved set on the run.

#### Scenario: Trigger maps body to parameters

- **WHEN** a webhook trigger fires with a body containing declared parameter names
- **THEN** those values populate the run's parameters and unmapped fields remain in `run.context_json`
