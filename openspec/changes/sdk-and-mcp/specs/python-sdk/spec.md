## ADDED Requirements

### Requirement: Python client surface

The system SHALL provide a Python SDK exposing `AutoAgent(base_url, api_key)` with `run_task`, `run_workflow`, `get_run`, `list_runs`, `cancel_run`, and a `wait` helper.

#### Scenario: Run a task and wait

- **WHEN** a developer calls `client.run_task(prompt, url=...)` then `client.wait(run)`
- **THEN** the SDK enqueues the task via `/api/v1/run-task` and polls to a terminal status, returning the final run

#### Scenario: Authentication via api key

- **WHEN** the client is constructed with an api key
- **THEN** every request sends `Authorization: Bearer <key>`

### Requirement: CLI

The system SHALL provide an `auto-agent` CLI for run-task, workflow run, run listing/inspection (with `--watch`), and cancellation.

#### Scenario: run-task from the terminal

- **WHEN** a user runs `auto-agent run-task "extract invoices" --url https://example.com --watch`
- **THEN** the CLI starts the run and streams status to terminal until terminal status

### Requirement: Model contract alignment

The SDK request/response models SHALL stay aligned with the served `/api/v1` OpenAPI contract, verified by a test.

#### Scenario: Contract drift detected

- **WHEN** the API schema diverges from the SDK models
- **THEN** the contract test fails
