## ADDED Requirements

### Requirement: Worker event upload

The worker SHALL upload run events to the cloud using the same payload shape as the in-process executor, including monotonic `seq` per run.

#### Scenario: Node started relay

- **WHEN** the worker executor emits `{event:"node_started", node_id, ts, ...}`
- **THEN** the worker sends `{type:"run_event", run_id, seq, payload}` over the worker WebSocket
- **AND** the cloud persists a `RunEvent` row
- **AND** fans out to existing `/ws/run` subscribers for that run

#### Scenario: Terminal event relay

- **WHEN** the worker emits `run_completed`, `run_failed`, or `run_aborted`
- **THEN** the cloud updates `Run.status` and `finished_at` using the same status map as in-process runs
- **AND** enqueues outbound webhooks when configured

### Requirement: Sequence validation

The cloud SHALL reject worker events whose `seq` is less than or equal to the last persisted seq for that run.

#### Scenario: Out-of-order seq

- **WHEN** the cloud already persisted seq 5 for a run and receives seq 4
- **THEN** the cloud rejects the event
- **AND** marks the run `failed` with a relay error

#### Scenario: Duplicate seq

- **WHEN** the cloud receives the same seq twice with identical payload
- **THEN** the cloud treats the second frame as idempotent and does not duplicate fanout

### Requirement: Run ownership check

The cloud SHALL accept worker events only from the worker currently assigned to that run.

#### Scenario: Wrong worker sends event

- **WHEN** worker A sends a `run_event` for a run assigned to worker B
- **THEN** the cloud rejects the frame with an authorization error

### Requirement: Subscriber transparency

Frontend run replay and live log subscribers SHALL NOT need to distinguish cloud-mode from worker-mode events.

#### Scenario: Replay worker run

- **WHEN** a client loads `GET /api/runs/{id}` for a completed worker-mode run
- **THEN** the returned `RunEvent` list is ordered by `seq` and replays identically to a cloud-mode run
