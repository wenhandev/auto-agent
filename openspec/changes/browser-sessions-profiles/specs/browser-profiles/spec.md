## ADDED Requirements

### Requirement: Browser profile entity

The system SHALL persist browser profiles as durable snapshots of browser state (`storage_state`) encrypted at rest, each with a unique name.

#### Scenario: Create a profile

- **WHEN** a client creates a browser profile with a name
- **THEN** a `BrowserProfile` row is created with an empty/initial `storage_state`
- **AND** the name is unique across profiles

#### Scenario: Storage state encrypted at rest

- **WHEN** a profile's `storage_state` is written to disk
- **THEN** it is Fernet-encrypted using the platform secret key
- **AND** the plaintext is never persisted

### Requirement: Capture profile from a run

The system SHALL allow capturing the `storage_state` of a finished or live run's browser context into a profile.

#### Scenario: Capture after successful login

- **WHEN** a client captures a profile from a run whose context holds authenticated cookies
- **THEN** the profile's encrypted `storage_state` is updated with that context's cookies and storage
- **AND** `last_used_at` is updated

### Requirement: Seed a run from a profile

The system SHALL seed a new run's browser context from a referenced profile so authenticated state is reused without re-login.

#### Scenario: Run reuses profile auth

- **WHEN** a run is started with `browser_profile_id` referencing a profile with valid auth cookies
- **THEN** the run's context is created with that profile's `storage_state`
- **AND** the run starts already authenticated where the cookies are still valid

#### Scenario: Stale profile falls through to login

- **WHEN** a profile-seeded run lands on a login wall because the cookies expired
- **THEN** the run does not crash on profile load and proceeds with its normal nodes (e.g. a `login` node)
