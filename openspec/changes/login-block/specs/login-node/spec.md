## ADDED Requirements

### Requirement: Login node

The system SHALL provide a `login` node type that authenticates against the current site using a linked credential, locating and filling the login form via the vision agent.

#### Scenario: Successful login

- **WHEN** a `login` node runs with a linked username/password credential and the form is present
- **THEN** the agent fills the credentials, submits, and the node completes with `{logged_in: true, method, final_url}`

#### Scenario: Credential must be linked

- **WHEN** a `login` node references a credential not linked to the run's workflow
- **THEN** the node fails with a "not linked to this workflow" error

### Requirement: Secrets excluded from model context

The login flow SHALL never place the raw username/password/TOTP into the LLM context; real values are typed by server-side tools.

#### Scenario: Password not in prompt

- **WHEN** the login agent decides to fill the password field
- **THEN** the model context contains a masked placeholder and the server-side tool types the real secret

### Requirement: Automated 2FA

When a 2FA step is encountered and a TOTP credential/identifier is available, the login node SHALL generate and fill the current code.

#### Scenario: TOTP filled automatically

- **WHEN** the site prompts for a 2FA code and a TOTP credential is configured
- **THEN** the node generates the current code and submits it without human intervention

#### Scenario: Code rollover retry

- **WHEN** a submitted code is rejected
- **THEN** the node requests a fresh code once and retries the 2FA submit before failing

### Requirement: Profile short-circuit

When the run is seeded from a profile that already holds a valid authenticated state, the login node SHALL skip re-authentication.

#### Scenario: Already authenticated

- **WHEN** a profile-seeded run reaches a `login` node and no login form is present at the target
- **THEN** the node completes with `{logged_in: true, method: "profile"}` without re-logging-in

### Requirement: Login outcome events

The login node SHALL emit `login_started` and a terminal `login_completed` / `login_failed` event carrying the masked outcome.

#### Scenario: Failure reported without secrets

- **WHEN** login cannot be verified as successful
- **THEN** a `login_failed` event is emitted with a reason and no secret material
