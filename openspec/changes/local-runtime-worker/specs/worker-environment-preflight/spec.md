## ADDED Requirements

### Requirement: Environment preflight before connect

The worker SHALL run a local environment preflight before opening the control WebSocket or accepting jobs. Preflight SHALL verify that browser automation can run on this machine.

#### Scenario: All checks pass

- **WHEN** preflight completes successfully
- **THEN** the worker proceeds to login/connect
- **AND** reports `environment_status="ready"` to the cloud on connect and in heartbeats

#### Scenario: Critical check fails before connect

- **WHEN** Chromium/Playwright is missing or cannot launch
- **THEN** the worker does not open the control WebSocket
- **AND** displays actionable remediation (e.g. run `playwright install chromium`)
- **AND** does not appear as assignable in the cloud Workers UI

#### Scenario: Standalone preflight command

- **WHEN** an operator runs `auto-agent-worker doctor`
- **THEN** the worker runs all preflight checks and prints pass/fail for each with remediation hints
- **AND** exits non-zero if any critical check fails

### Requirement: Preflight check catalogue

The worker preflight SHALL include at minimum the following checks, each recorded as `pass`, `warn`, or `fail`:

| Check | Critical | Description |
|-------|----------|-------------|
| `playwright_installed` | yes | Playwright Python package importable |
| `chromium_binary` | yes | Chromium browser binary present for Playwright |
| `chromium_smoke` | yes | Launch headless Chromium, open blank page, close cleanly |
| `cloud_reachable` | yes | HTTPS GET to configured cloud `/health` or `/api/health` succeeds |
| `headed_display` | warn-only when headless=false | Display server / GUI session available for headed mode |
| `disk_space` | warn below threshold | Sufficient free disk for profiles and artifacts (default warn &lt; 1 GiB) |
| `memory` | warn below threshold | Sufficient free RAM (default warn &lt; 2 GiB) |

#### Scenario: Headed mode without display

- **WHEN** `BROWSER_HEADLESS=false` and no display is available (e.g. headless Linux server)
- **THEN** `headed_display` is `warn`
- **AND** `environment_status` is `degraded`
- **AND** the worker MAY still connect but advertises `capabilities.headed=false`

#### Scenario: Headless mode skips display check

- **WHEN** `BROWSER_HEADLESS=true`
- **THEN** `headed_display` is skipped or reported as not applicable
- **AND** a missing display does not affect `environment_status`

### Requirement: Environment status on cloud

The worker SHALL include an `environment` summary in the connect handshake and periodic heartbeats. The cloud SHALL persist the latest summary on the `Worker` row and expose it in the Workers UI.

#### Scenario: Heartbeat carries environment

- **WHEN** a connected worker sends a heartbeat
- **THEN** the payload includes `{environment_status, checks: [{id, status, message?}], capabilities}`
- **AND** the cloud updates the worker record

#### Scenario: Workers UI shows not ready

- **WHEN** a worker has `environment_status="not_ready"`
- **THEN** the Workers UI shows a warning badge and the failing check messages
- **AND** the dispatcher does not assign new runs to that worker

#### Scenario: Degraded worker assignment policy

- **WHEN** a worker has `environment_status="degraded"` (warnings only)
- **THEN** the dispatcher MAY assign runs that do not require failing capabilities
- **AND** headed runs are not assigned when `capabilities.headed=false`

### Requirement: Re-check on environment change

The worker SHALL re-run preflight when configuration changes (e.g. toggling `BROWSER_HEADLESS`) and at least once on each reconnect after restart.

#### Scenario: Chromium installed after initial failure

- **WHEN** preflight previously failed on `chromium_binary` and the user installs Chromium
- **THEN** the next `doctor` or restart preflight passes
- **AND** the worker can connect and transition to `ready`
