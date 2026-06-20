## ADDED Requirements

### Requirement: TOTP credential kind

The system SHALL support a `totp` credential kind storing a base32 secret (and optional `digits`/`period`/`algorithm`) encrypted at rest, whose secret is never returned in plaintext.

#### Scenario: Create a TOTP credential

- **WHEN** a client creates a credential of kind `totp` with a base32 secret
- **THEN** the secret is stored Fernet-encrypted
- **AND** any read endpoint returns the secret masked, never in plaintext

### Requirement: RFC 6238 code generation

The system SHALL compute the current TOTP code for a stored secret per RFC 6238, honouring configured `digits`, `period`, and `algorithm`.

#### Scenario: Code matches RFC test vectors

- **WHEN** the generator runs against the RFC 6238 reference secret and timestamps
- **THEN** it returns the documented expected codes

#### Scenario: Default parameters

- **WHEN** a TOTP credential omits `digits`/`period`/`algorithm`
- **THEN** the generator uses 6 digits, 30s period, SHA1

### Requirement: TOTP interpolation token

The system SHALL resolve `{{totp.<credential_name>}}` to the current code at action time, subject to per-workflow credential-link enforcement.

#### Scenario: Token resolves to live code

- **WHEN** a node param contains `{{totp.my-2fa}}` during a run whose workflow links `my-2fa`
- **THEN** the token resolves to the current 6-digit code at execution time

#### Scenario: Unlinked TOTP rejected

- **WHEN** a node references `{{totp.x}}` for a credential not linked to the run's workflow
- **THEN** the node fails with a "not linked to this workflow" error and no code is generated

### Requirement: Run-level totp_identifier

The system SHALL accept an optional `totp_identifier` on a run so a vision/login flow can request the code at runtime.

#### Scenario: Vision flow fetches code on demand

- **WHEN** a run is started with `totp_identifier` and the agent encounters a 2FA field
- **THEN** the agent can obtain the current code for that identifier and fill it
