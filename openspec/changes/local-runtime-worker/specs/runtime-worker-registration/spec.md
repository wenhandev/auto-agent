## ADDED Requirements

### Requirement: Worker user login

The worker application SHALL authenticate the operator with the same cloud platform credentials used by the web UI (email + password via `multi-user-orgs`), then obtain a worker-scoped session credential for outbound connections.

#### Scenario: Successful login on worker

- **WHEN** a user enters a valid cloud URL, email, and password in the worker app
- **THEN** the cloud validates credentials and returns a worker session token bound to that user and org
- **AND** the worker persists the token locally for subsequent reconnects

#### Scenario: Invalid login rejected

- **WHEN** a user enters invalid credentials in the worker app
- **THEN** the cloud returns HTTP 401
- **AND** the worker does not open a control WebSocket

#### Scenario: Logout on worker

- **WHEN** a user logs out from the worker app
- **THEN** the worker closes its control WebSocket
- **AND** deletes locally persisted session credentials
- **AND** the cloud marks that worker connection offline

### Requirement: Worker visible on cloud after connect

After a successful login, the worker SHALL actively open an outbound control connection; the cloud SHALL list that worker in the platform Workers UI for members of the same org.

#### Scenario: Worker appears online after login

- **WHEN** a logged-in worker opens `WSS /api/v1/workers/connect` with a valid worker session token
- **THEN** the cloud upserts a `Worker` row linked to the user and org
- **AND** sets status to `online` with `last_seen_at` updated
- **AND** org members viewing Settings → Workers see the worker with display name, hostname, logged-in user email, and status `在线`

#### Scenario: Worker disappears on disconnect

- **WHEN** the worker control WebSocket closes and no heartbeat arrives within `WORKER_HEARTBEAT_TIMEOUT`
- **THEN** the cloud sets the worker status to `offline`
- **AND** the Workers UI reflects the offline state

#### Scenario: Reconnect with saved session

- **WHEN** the worker restarts and finds a persisted valid session token
- **THEN** it reconnects without prompting for password
- **AND** the same worker row returns to `online`

#### Scenario: Expired session prompts re-login

- **WHEN** a persisted worker session token is expired or revoked
- **THEN** the worker prompts the user to log in again
- **AND** does not assign or execute runs until re-authenticated

### Requirement: Outbound worker WebSocket

The worker SHALL maintain an outbound WebSocket to `WSS /api/v1/workers/connect` authenticated with the worker session token obtained from user login (or enrollment, see below).

#### Scenario: Connect after login

- **WHEN** login succeeds
- **THEN** the worker immediately initiates the outbound WebSocket without manual copy-paste of tokens in the cloud UI

#### Scenario: TLS required

- **WHEN** the configured cloud URL uses plain HTTP in production mode
- **THEN** the worker refuses to connect and displays a security warning

### Requirement: Worker identity metadata

Each connected worker SHALL report machine metadata on connect and in heartbeats: hostname, OS, agent version, optional friendly display name, and pool tags.

#### Scenario: Cloud shows hostname and user

- **WHEN** a worker connects from machine `DESKTOP-FINANCE` as user `alice@corp.com`
- **THEN** the Workers UI row shows `DESKTOP-FINANCE` (or user-edited name), `alice@corp.com`, and agent version

### Requirement: Worker heartbeat and capabilities

The worker SHALL send periodic heartbeat frames advertising `max_concurrent_runs`, active run count, agent version, and capability tags.

#### Scenario: Heartbeat updates capacity

- **WHEN** the worker sends a heartbeat with `active_runs=1` and `max_concurrent_runs=2`
- **THEN** the cloud considers one additional run assignable to that worker

#### Scenario: Stale heartbeat

- **WHEN** the cloud receives no heartbeat from an online worker for longer than `WORKER_HEARTBEAT_TIMEOUT`
- **THEN** the worker is marked `offline`
- **AND** any in-flight runs assigned to it transition to `failed` with a worker-disconnected error

### Requirement: Worker tags for pool routing

Each worker SHALL declare one or more pool tags (default `["default"]`) used by the dispatcher to match `Run.worker_pool`. Tags MAY be edited in the worker app before connecting.

#### Scenario: Tag advertisement

- **WHEN** a worker connects with tags `["finance", "default"]`
- **THEN** runs with `worker_pool="finance"` MAY be assigned to that worker
- **AND** runs with `worker_pool="default"` MAY also be assigned to that worker

### Requirement: Optional headless enrollment (admin path)

The system MAY support one-time enrollment tokens (`wk_enroll_`) for unattended/service workers without an interactive login UI. This path is secondary to user login and SHALL require org `admin` or `owner` role to create tokens in Settings.

#### Scenario: Admin creates enrollment token

- **WHEN** an org admin creates an enrollment token in Settings
- **THEN** the API returns the full token once for use with `auto-agent-worker connect --enrollment-token`

#### Scenario: Enrollment token revoked

- **WHEN** an admin revokes an enrollment token
- **THEN** workers registered only via that token cannot reconnect
