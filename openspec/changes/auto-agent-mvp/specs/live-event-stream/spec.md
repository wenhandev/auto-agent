## ADDED Requirements

### Requirement: WebSocket Run Endpoint

The backend SHALL expose `WebSocket /ws/run` that accepts an initial client message `{"type":"start", "workflow": Workflow}` and streams executor events back as JSON text frames.

#### Scenario: Run a workflow

- **WHEN** a client sends a valid `start` frame
- **THEN** the server SHALL start the executor immediately and stream events progressively as nodes execute.

### Requirement: Event Shape

Each emitted event SHALL be a JSON object with at least `event`, `node_id`, and `ts` (ISO-8601). `node_completed` MAY include `output`, `node_failed` MUST include `error`, and `node_progress` MUST include `message`.

#### Scenario: Started/completed pair

- **WHEN** a deterministic node finishes successfully
- **THEN** the client SHALL receive exactly one `node_started` followed by exactly one `node_completed` for that `node_id`.

### Requirement: Progressive Streaming

The server SHALL emit each event AS SOON AS the executor reaches the corresponding point, rather than buffering all events until the run completes.

#### Scenario: Glow visible live

- **WHEN** a workflow contains a `wait` node of 1000 ms
- **THEN** the `node_started` event SHALL arrive at the client at least 500 ms before the `node_completed` event.

### Requirement: Graceful WebSocket Closure

The server SHALL close the WebSocket cleanly after the final node event (success or failure path) without raising.

#### Scenario: Successful close

- **WHEN** the executor finishes the last node
- **THEN** the server SHALL emit a final `run_completed` event and close the socket.

### Requirement: Sample Workflow Endpoint

The backend SHALL expose `GET /api/sample-workflow` returning a hardcoded six-node `Workflow` that exercises `navigate`, `wait`, `fuzzy_action`, `extract`, `navigate`, `wait` in a linear chain.

#### Scenario: Demo without API key

- **WHEN** no `OPENAI_API_KEY` is set in the environment and the client requests `/api/sample-workflow`
- **THEN** the endpoint SHALL still return the hardcoded workflow with HTTP 200.
