## ADDED Requirements

### Requirement: Org desktop client policy

Each organization SHALL have a `desktop_client_policy` controlling whether desktop clients may register and execute:

- `disabled` — no desktop/CLI worker login or connect permitted.
- `approval_required` — devices may register but MUST be approved by an org admin before execution (**default for new orgs**).
- `open` — devices are auto-approved on first successful login (legacy/dev behavior).

#### Scenario: Policy disabled blocks login

- **WHEN** `desktop_client_policy=disabled` and a user attempts desktop app login
- **THEN** the cloud returns HTTP 403 with a message that desktop clients are disabled for this org
- **AND** no worker session token is issued

#### Scenario: Default policy requires approval

- **WHEN** a new organization is created
- **THEN** `desktop_client_policy` defaults to `approval_required`

### Requirement: Per-device approval state

Each `Worker` row representing a desktop or CLI client SHALL carry an `approval_status` of `pending`, `approved`, or `rejected`, plus optional `approved_at` and `approved_by_user_id`.

#### Scenario: First login creates pending device

- **WHEN** a user logs in from a new `machine_id` and org policy is `approval_required`
- **THEN** the worker row is upserted with `approval_status=pending`
- **AND** a session token is issued so the device can show pending UI and appear in the admin list

#### Scenario: Auto-approve when policy is open

- **WHEN** org policy is `open` and login succeeds
- **THEN** `approval_status` is set to `approved` immediately

#### Scenario: Re-login on approved device

- **WHEN** a user logs in from a previously approved `machine_id`
- **THEN** `approval_status` remains `approved` unless an admin revoked the device

### Requirement: Execution blocked until approved

The cloud and local sidecar SHALL NOT execute workflows, accept cloud-dispatched runs, or allow Publish until the worker is `approved` and not revoked.

#### Scenario: Pending device cannot run

- **WHEN** `approval_status=pending`
- **THEN** the dispatcher SHALL NOT assign runs to that worker
- **AND** the desktop app localhost API rejects `POST /runs` with HTTP 403
- **AND** Publish to cloud is rejected with HTTP 403

#### Scenario: Rejected device

- **WHEN** an admin sets `approval_status=rejected`
- **THEN** the worker WebSocket is closed or kept in a no-dispatch state
- **AND** the desktop app shows that access was denied

#### Scenario: Approved device operates normally

- **WHEN** `approval_status=approved` and the worker is not revoked
- **THEN** cloud dispatch and app-initiated runs behave per `desktop-local-runtime` and `worker-local-runtime`

### Requirement: Admin approve and reject in cloud UI

Org admins and owners SHALL approve or reject pending desktop clients from Settings → Workers in the web UI.

#### Scenario: Admin approves pending device

- **WHEN** an admin clicks Approve on a worker with `approval_status=pending`
- **THEN** the worker becomes `approved` with `approved_at` and `approved_by_user_id` set
- **AND** the desktop app unlocks within one poll interval (≤10s) or on reconnect

#### Scenario: Admin rejects pending device

- **WHEN** an admin clicks Reject on a pending worker
- **THEN** `approval_status` becomes `rejected`
- **AND** active worker sessions for that device are revoked

#### Scenario: Non-admin cannot approve

- **WHEN** a member or viewer calls the approve endpoint
- **THEN** the cloud returns HTTP 403

### Requirement: Pending state UX in desktop app

The desktop app SHALL show a dedicated **waiting for authorization** screen when the device is pending, instead of the main authoring shell.

#### Scenario: User sees pending screen

- **WHEN** login succeeds but `approval_status=pending`
- **THEN** the app displays machine name, logged-in email, and instructions to contact an administrator
- **AND** polls worker status until approved or rejected

#### Scenario: Unlock after approval

- **WHEN** the device transitions to `approved` while the app is open
- **THEN** the app navigates to the main shell without requiring re-login
