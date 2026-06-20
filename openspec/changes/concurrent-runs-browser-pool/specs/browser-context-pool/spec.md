## ADDED Requirements

### Requirement: Bounded isolated context pool

The system SHALL maintain a pool of up to `MAX_CONCURRENT_RUNS` isolated browser contexts over a single browser process, lending one per pooled run.

#### Scenario: Isolated contexts

- **WHEN** two pooled runs execute concurrently
- **THEN** each uses its own context with isolated cookies/storage/pages

#### Scenario: Context released on completion

- **WHEN** a pooled run finishes
- **THEN** its context is closed/released and the slot becomes available

### Requirement: Session-pinned vs pooled contexts

The system SHALL pin a session-bound run to its session's context and draw other runs from the pool.

#### Scenario: Session-bound run uses its session context

- **WHEN** a run is started with a `browser_session_id`
- **THEN** it executes against that session's pinned context, not a pooled one

### Requirement: Parked-context bound

The system SHALL cap the number of parked (approval-paused) contexts at `MAX_PARKED_CONTEXTS`.

#### Scenario: Parked contexts bounded

- **WHEN** parked contexts would exceed `MAX_PARKED_CONTEXTS`
- **THEN** further approval pauses are handled per policy (fail or hold-slot) rather than parking unboundedly
