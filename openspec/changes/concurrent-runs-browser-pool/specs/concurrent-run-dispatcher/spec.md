## ADDED Requirements

### Requirement: Bounded concurrent dispatch

The system SHALL admit up to `MAX_CONCURRENT_RUNS` runs simultaneously, queuing the rest with a reported queue position.

#### Scenario: Runs admitted up to the cap

- **WHEN** `MAX_CONCURRENT_RUNS=3` and five runs are requested
- **THEN** three run concurrently and two remain `queued` with positions 1 and 2

#### Scenario: Single-run compatibility mode

- **WHEN** `MAX_CONCURRENT_RUNS=1`
- **THEN** the system behaves identically to the prior one-run-at-a-time platform

### Requirement: Per-workflow ordering

The system SHALL serialise runs of the same workflow by default unless `allow_parallel_per_workflow` is set.

#### Scenario: Same-workflow runs serialise

- **WHEN** two runs of the same workflow are queued and `allow_parallel_per_workflow` is off
- **THEN** the second starts only after the first finishes, even if a pool slot is free

### Requirement: Fairness across workflows

The system SHALL admit queued runs round-robin across workflows so no single workflow starves others.

#### Scenario: Round-robin admission

- **WHEN** workflow A has 10 queued runs and workflow B has 1
- **THEN** B's run is admitted without waiting for all of A's

### Requirement: Approval releases the slot

The system SHALL free a run's dispatch slot while it is paused awaiting approval and re-acquire one on resume.

#### Scenario: Paused run frees a slot

- **WHEN** a run pauses on an approval node
- **THEN** its pool slot is released so another queued run can start
- **AND** on approval the run re-acquires a slot (queuing if the pool is full)

### Requirement: Queue backpressure

The system SHALL reject new runs beyond `MAX_QUEUE_DEPTH` with HTTP 429.

#### Scenario: Queue full

- **WHEN** the queue is at `MAX_QUEUE_DEPTH`
- **THEN** a new run request receives HTTP 429
