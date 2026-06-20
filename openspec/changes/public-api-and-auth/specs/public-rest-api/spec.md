## ADDED Requirements

### Requirement: Autonomous run-task endpoint

The system SHALL expose `POST /api/v1/run-task` that starts a run from a natural-language prompt and optional URL, returning a run handle.

#### Scenario: Run a task from a prompt

- **WHEN** a client POSTs `{prompt, url}` to `/api/v1/run-task`
- **THEN** the system creates a vision-navigation run toward the prompt and returns `{run_id, status}`

#### Scenario: Run-task with session and TOTP

- **WHEN** the request includes `browser_session_id` and `totp_identifier`
- **THEN** the run attaches to the session and can fetch 2FA codes for that identifier

### Requirement: Workflow run endpoint

The system SHALL expose `POST /api/v1/workflows/{id}/run` to enqueue a run of a saved workflow with optional parameters.

#### Scenario: Run a saved workflow

- **WHEN** a client POSTs to `/api/v1/workflows/{id}/run`
- **THEN** a run is enqueued for that workflow and a run handle is returned

### Requirement: Run status, listing, and cancellation

The system SHALL expose endpoints to get a run, list runs (paginated), and cancel a run.

#### Scenario: Poll run status

- **WHEN** a client GETs `/api/v1/runs/{id}`
- **THEN** it receives the run status and outputs

#### Scenario: Cancel a run

- **WHEN** a client POSTs `/api/v1/runs/{id}/cancel` for a running run
- **THEN** the run is aborted and its status reflects cancellation

#### Scenario: Paginated listing

- **WHEN** a client GETs `/api/v1/runs?limit=50&cursor=...`
- **THEN** it receives at most `limit` runs and a next cursor

### Requirement: Programmatic resource CRUD

The system SHALL expose `/api/v1/workflows` and `/api/v1/credentials` (masked) CRUD with parity to the internal UI operations.

#### Scenario: Create a workflow via API

- **WHEN** a client POSTs a workflow definition to `/api/v1/workflows`
- **THEN** the workflow is persisted and returned with its id

#### Scenario: Credentials returned masked

- **WHEN** a client GETs `/api/v1/credentials`
- **THEN** secret fields are masked in the response

### Requirement: Curated OpenAPI contract

The system SHALL publish a curated OpenAPI document for `/api/v1` suitable for SDK generation.

#### Scenario: OpenAPI describes the v1 surface

- **WHEN** a client fetches the OpenAPI document
- **THEN** all `/api/v1` routes appear with tags, the bearer auth scheme, and request/response schemas
