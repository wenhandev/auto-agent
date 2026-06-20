## ADDED Requirements

### Requirement: Run execution mode

Each run SHALL carry an `execution_mode` of `cloud` or `worker`. When omitted at enqueue time, the system SHALL default to `cloud`.

#### Scenario: Default cloud mode

- **WHEN** a run is enqueued without `execution_mode`
- **THEN** the run executes in-process on the cloud backend as today

#### Scenario: Explicit worker mode

- **WHEN** a run is enqueued with `execution_mode="worker"`
- **THEN** the cloud dispatcher SHALL NOT call in-process `_drive_run`
- **AND** SHALL assign the run to a connected worker instead

### Requirement: Worker assignment

The cloud dispatcher SHALL assign worker-mode runs to an online worker matching `worker_pool` or pinned `worker_id` with available capacity.

#### Scenario: Pool assignment

- **WHEN** a worker-mode run has `worker_pool="default"` and two workers with tag `default` are online with free capacity
- **THEN** the dispatcher assigns the run to one of them using round-robin fairness

#### Scenario: Pinned worker assignment

- **WHEN** a run specifies `worker_id="w-123"` and that worker is online with capacity
- **THEN** the run is assigned only to worker `w-123`

#### Scenario: No worker available

- **WHEN** no online worker matches the pool or pinned id
- **THEN** the run remains `queued`
- **AND** queue metadata indicates `waiting_for_worker`

#### Scenario: Not-ready worker skipped

- **WHEN** the only matching workers have `environment_status="not_ready"`
- **THEN** the run remains `queued`
- **AND** queue metadata indicates `waiting_for_ready_worker`

### Requirement: Environment-aware assignment

The dispatcher SHALL assign worker-mode runs only to workers whose reported `environment_status` satisfies the run requirements.

#### Scenario: Ready worker receives job

- **WHEN** a worker has `environment_status="ready"` and free capacity
- **THEN** the dispatcher MAY assign worker-mode runs to it

#### Scenario: Not-ready worker excluded

- **WHEN** a worker has `environment_status="not_ready"`
- **THEN** the dispatcher SHALL NOT assign runs to that worker even if it is connected

#### Scenario: Degraded headed capability

- **WHEN** a worker has `environment_status="degraded"` with `capabilities.headed=false`
- **THEN** the dispatcher MAY assign runs that do not require a visible headed browser
- **AND** SHALL NOT assign runs explicitly requiring headed execution to that worker

### Requirement: Execute job frame

The cloud SHALL push an `execute_run` frame to the assigned worker containing `run_id`, hydrated workflow JSON, resolved parameters, trigger namespace, and browser profile id reference.

#### Scenario: Worker receives job

- **WHEN** a worker-mode run is assigned
- **THEN** the worker receives `{type:"execute_run", run_id, workflow, parameters, trigger_namespace, browser_profile_id, totp_identifier, record_video}`
- **AND** the run transitions to `running` with `started_at` set

#### Scenario: Worker rejects unknown run

- **WHEN** a worker receives an `execute_run` for a run_id it is not assigned
- **THEN** the worker ignores the frame and logs a warning

### Requirement: Abort relay

The cloud SHALL relay abort requests to the worker executing the run.

#### Scenario: Abort running worker run

- **WHEN** an operator aborts a worker-mode run with status `running`
- **THEN** the cloud sends `{type:"abort", run_id}` to the assigned worker
- **AND** the worker sets its local abort event
- **AND** the run eventually reaches status `aborted` with a `run_aborted` event

#### Scenario: Abort queued worker run

- **WHEN** an operator aborts a worker-mode run still waiting for a worker
- **THEN** the run transitions directly to `aborted` without contacting a worker

### Requirement: Approval resume relay

The cloud SHALL notify the worker to resume a run paused on an approval node after the operator approves.

#### Scenario: Resume after approval

- **WHEN** an approval is granted for a worker-mode run paused on the worker
- **THEN** the cloud sends `{type:"resume_run", run_id}` to the worker
- **AND** the worker continues execution from the approval node

### Requirement: Per-worker concurrency

The worker SHALL enforce its advertised `max_concurrent_runs` locally and reject additional `execute_run` frames when at capacity.

#### Scenario: Worker at capacity

- **WHEN** a worker already runs `max_concurrent_runs` jobs
- **THEN** the cloud SHALL NOT assign another run to that worker until a slot frees
