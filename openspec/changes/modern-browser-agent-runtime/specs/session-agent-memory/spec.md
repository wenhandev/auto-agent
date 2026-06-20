## ADDED Requirements

### Requirement: Session compact memory

The system SHALL maintain optional compact agent memory for a browser session, storing task continuity context without storing stale DOM, screenshots, accessibility trees, or full tool traces.

#### Scenario: New session starts with empty memory

- **WHEN** a browser session is created
- **THEN** its compact agent memory is empty
- **AND** no memory content is injected into runs until memory entries are appended

#### Scenario: Run appends compact memory

- **WHEN** an autonomous or hybrid agent run finishes while attached to a browser session
- **THEN** the system appends a compact memory entry containing objective, success status, final summary, final URL, and a bounded extracted-facts summary
- **AND** the system excludes full DOM snapshots, screenshots, raw accessibility trees, and raw tool traces

### Requirement: Session memory injection

The system SHALL inject relevant browser-session compact memory into later autonomous or hybrid runs that explicitly attach to the same browser session.

#### Scenario: Later run receives compact context

- **WHEN** a new autonomous or hybrid run starts with a `browser_session_id` that has compact memory
- **THEN** the prompt/context includes the bounded compact memory as historical context
- **AND** the prompt/context states that the current observation is the only source of current page facts

#### Scenario: Runs without session do not receive session memory

- **WHEN** a run starts without a `browser_session_id`
- **THEN** the system does not inject compact memory from any browser session

### Requirement: Session memory lifecycle

The system SHALL allow operators or clients to inspect and clear compact memory for a browser session.

#### Scenario: Clear session memory

- **WHEN** a client clears memory for a browser session
- **THEN** all compact memory entries for that session are removed
- **AND** subsequent runs on that session receive no prior compact memory

#### Scenario: Deleted session removes memory

- **WHEN** a browser session row is deleted
- **THEN** its associated compact memory is removed or becomes inaccessible through public APIs
