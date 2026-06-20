## ADDED Requirements

### Requirement: Worker login UI

The worker application SHALL provide a first-run and re-auth flow where the user enters cloud platform URL, email, and password before any jobs are accepted.

#### Scenario: First launch shows login

- **WHEN** the worker starts with no saved session
- **THEN** the user sees a login form (URL, email, password)
- **AND** optional display name and pool tags fields

#### Scenario: Login then connect

- **WHEN** the user submits valid credentials
- **THEN** the worker obtains a session token, saves it locally, and opens the outbound control WebSocket
- **AND** displays connected status with worker id and cloud URL

### Requirement: Local Playwright on worker

The worker process SHALL launch and manage Playwright Chromium locally using the existing browser pool and profile machinery.

#### Scenario: Worker executes navigate node

- **WHEN** a worker receives an `execute_run` job containing a navigate node
- **THEN** the worker opens or reuses a local Chromium context
- **AND** executes the node without contacting cloud Playwright

#### Scenario: Headed default on worker

- **WHEN** the worker is configured with `BROWSER_HEADLESS=false`
- **THEN** a visible Chromium window MAY appear on the operator's desktop

### Requirement: Local browser profile resolution

Worker-mode runs SHALL resolve `browser_profile_id` against the worker's local profile store, not the cloud database bytes.

#### Scenario: Profile exists locally

- **WHEN** a run references `browser_profile_id` and the worker has matching profile storage
- **THEN** the worker seeds the browser context from local `storage_state`

#### Scenario: Profile missing locally

- **WHEN** a run references a profile id absent on the worker
- **THEN** the worker fails the run before execution with a clear profile-not-found error event

### Requirement: Local credential resolution

Worker-mode runs SHALL resolve `{{cred.*}}` references against the worker's local credential backend only.

#### Scenario: Credential on worker

- **WHEN** a workflow node references `{{cred.local:github.password}}` and the worker vault contains that entry
- **THEN** interpolation succeeds on the worker without sending secret values to the cloud

#### Scenario: Credential missing on worker

- **WHEN** a referenced credential is absent on the worker
- **THEN** the node fails with a credential-not-found error
- **AND** no secret values are logged or uploaded

### Requirement: Cloud LLM proxy for agent steps

When a worker-mode run invokes LLM-backed agent steps, the worker SHALL call the cloud LLM proxy instead of loading API keys locally.

#### Scenario: Fuzzy action on worker

- **WHEN** a fuzzy_action node runs on a worker
- **THEN** the worker sends a proxy request to the cloud with prompts and optional screenshot artifact references
- **AND** the cloud returns model output using centralized LLM configuration

#### Scenario: Proxy unauthorized

- **WHEN** the worker presents an invalid session token to the LLM proxy
- **THEN** the cloud returns HTTP 401 and the node fails

### Requirement: Worker application entry point

The repository SHALL provide `auto-agent-worker` that defaults to the login-then-connect flow.

#### Scenario: Interactive start

- **WHEN** an operator runs `auto-agent-worker start` (or launches the desktop app)
- **THEN** the worker prompts for login if no valid saved session exists
- **AND** after login connects outbound and logs online status

#### Scenario: Headless start with enrollment token

- **WHEN** an operator runs `auto-agent-worker connect --enrollment-token wk_enroll_...`
- **THEN** the worker registers without interactive login (admin path only)
- **AND** connects outbound
