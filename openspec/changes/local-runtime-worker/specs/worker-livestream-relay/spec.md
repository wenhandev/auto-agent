## ADDED Requirements

### Requirement: Worker stream frame upload

When executing a worker-mode run, the worker SHALL capture CDP screencast frames locally and upload them to the cloud as `{type:"stream_frame", run_id, seq, width, height, jpeg_base64}` frames.

#### Scenario: Frame ingest

- **WHEN** the cloud receives a valid stream frame for a running worker-mode run
- **THEN** it forwards the frame to all viewers connected on `/ws/stream/{run_id}`

#### Scenario: Headed worker still relays

- **WHEN** the worker runs a headed browser locally
- **THEN** viewers on the cloud web UI still receive live frames via the relay path

### Requirement: Relay lifecycle matches in-process livestream

The worker SHALL start screencast capture only when the cloud signals at least one viewer is connected, and stop when the cloud signals no viewers remain.

#### Scenario: Viewer connects on cloud

- **WHEN** a client opens `/ws/stream/{run_id}` for a worker-mode run
- **THEN** the cloud sends `{type:"stream_subscribe", run_id}` to the assigned worker
- **AND** the worker starts CDP screencast

#### Scenario: Last viewer disconnects

- **WHEN** the last viewer disconnects from `/ws/stream/{run_id}`
- **THEN** the cloud sends `{type:"stream_unsubscribe", run_id}` to the worker
- **AND** the worker stops screencast capture

### Requirement: Stream termination on run end

The cloud SHALL send `stream_ended` to viewers when a worker-mode run reaches a terminal status, consistent with in-process livestream behavior.

#### Scenario: Run completes while viewing

- **WHEN** a worker-mode run emits a terminal event
- **THEN** viewers receive `stream_ended`
- **AND** no further frames are delivered
