## ADDED Requirements

### Requirement: Worker-mode dispatch branch

When a queued run has `execution_mode="worker"`, the dispatcher SHALL assign it to a connected worker with available capacity instead of admitting it to the in-process cloud browser pool.

#### Scenario: Cloud pool unaffected by worker runs

- **WHEN** three cloud-mode runs and two worker-mode runs are active
- **THEN** cloud-mode runs consume `MAX_CONCURRENT_BROWSER_RUNS` slots on the server
- **AND** worker-mode runs consume capacity only on their assigned workers

#### Scenario: Worker run not admitted locally

- **WHEN** a worker-mode run is promoted from the queue
- **THEN** the cloud SHALL NOT spawn `_drive_run` in the API process for that run

## MODIFIED Requirements

### Requirement: Bounded concurrent dispatch

The system SHALL admit up to `MAX_CONCURRENT_RUNS` **cloud-mode** runs simultaneously, queuing the rest with a reported queue position. Worker-mode runs SHALL be governed by per-worker capacity instead of the cloud browser pool cap.

#### Scenario: Runs admitted up to the cap

- **WHEN** `MAX_CONCURRENT_RUNS=3` and five **cloud-mode** runs are requested
- **THEN** three run concurrently in-process and two remain `queued` with positions 1 and 2

#### Scenario: Single-run compatibility mode

- **WHEN** `MAX_CONCURRENT_RUNS=1`
- **THEN** the system behaves identically to the prior one-run-at-a-time platform for cloud-mode runs

#### Scenario: Worker runs bypass cloud cap

- **WHEN** `MAX_CONCURRENT_RUNS=1` and a worker-mode run is queued while one cloud-mode run is active
- **THEN** the worker-mode run MAY still start on an available worker without waiting for the cloud run to finish
