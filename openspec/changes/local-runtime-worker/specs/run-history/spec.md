## ADDED Requirements

### Requirement: Run execution metadata

Run list and detail responses SHALL include `execution_mode`, optional `worker_id`, optional `worker_pool`, and optional `worker_name` (resolved from the assigned worker).

#### Scenario: Worker run detail

- **WHEN** a client loads `GET /api/runs/{id}` for a worker-mode run assigned to worker `w-abc`
- **THEN** the response includes `execution_mode="worker"`, `worker_id="w-abc"`, and the worker display name

#### Scenario: Queued waiting for worker

- **WHEN** a worker-mode run is queued with no matching online worker
- **THEN** the run list shows status `queued` and queue metadata indicating `waiting_for_worker`

### Requirement: Enqueue worker mode

`POST /api/runs` and public `POST /api/v1/workflows/{id}/run` SHALL accept optional `execution_mode`, `worker_id`, and `worker_pool` fields.

#### Scenario: Enqueue with worker pool

- **WHEN** a client posts `{execution_mode:"worker", worker_pool:"finance"}`
- **THEN** the created run row stores those fields
- **AND** the dispatcher routes to workers tagged `finance`

#### Scenario: Invalid execution mode

- **WHEN** a client posts an unknown `execution_mode` value
- **THEN** the API returns HTTP 422
