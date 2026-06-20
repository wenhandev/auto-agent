## ADDED Requirements

### Requirement: Live viewport streaming

The system SHALL stream the active browser page's viewport as image frames to connected clients in real time while a run is executing, using CDP screencast.

#### Scenario: Viewer sees live frames

- **WHEN** a client connects to `/ws/stream/{run_id}` for a running run
- **THEN** the server starts CDP screencast and pushes JPEG frames with `{ts, seq, width, height}` headers
- **AND** frames reflect page changes in near real time

#### Scenario: Headless run still streams

- **WHEN** the browser runs headless and a client opens the stream socket
- **THEN** frames are still produced and delivered

### Requirement: On-demand capture lifecycle

The system SHALL start screencast only when at least one viewer is connected and stop it when the last viewer disconnects.

#### Scenario: No cost when unwatched

- **WHEN** a run executes with no stream viewers connected
- **THEN** no screencast is started and no frames are captured

#### Scenario: Stop on last disconnect

- **WHEN** the last stream viewer disconnects
- **THEN** the server stops CDP screencast for that run

### Requirement: Latest-wins backpressure

The system SHALL bound per-viewer memory by keeping only the most recent undelivered frame for a slow viewer, dropping older frames.

#### Scenario: Slow viewer drops stale frames

- **WHEN** a viewer cannot keep up with the frame rate
- **THEN** the server overwrites the pending frame with the newest one and never grows an unbounded queue

### Requirement: Stream termination signal

The system SHALL notify viewers when the run finishes so the UI can render a terminal state.

#### Scenario: Run ends while watching

- **WHEN** the run reaches a terminal status while a viewer is connected
- **THEN** the server sends a `stream_ended` control message and stops sending frames
