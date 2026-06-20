## ADDED Requirements

### Requirement: MCP tool server

The system SHALL provide an MCP server exposing tools `run_task`, `run_workflow`, `get_run`, `cancel_run`, and `list_workflows` over the `/api/v1` surface.

#### Scenario: AI assistant runs a task

- **WHEN** an MCP client invokes the `run_task` tool with a prompt and url
- **THEN** the server calls `/api/v1/run-task` and returns the run handle to the assistant

#### Scenario: Configuration from environment

- **WHEN** the MCP server starts without `AUTO_AGENT_BASE_URL` or `AUTO_AGENT_API_KEY`
- **THEN** it fails fast with an actionable configuration error

### Requirement: IDE configuration snippet

The system SHALL ship a ready-to-paste MCP configuration snippet for common AI IDEs.

#### Scenario: Snippet provided

- **WHEN** a user reads the MCP server docs
- **THEN** a copy-paste config block for Cursor/Claude is available
