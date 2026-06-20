## ADDED Requirements

### Requirement: Proxy configuration

The system SHALL allow configuring a proxy (`server`, optional `username`/`password`) per run, session, or profile, with credentials encrypted at rest, applied to the browser context.

#### Scenario: Run uses a configured proxy

- **WHEN** a run is started with a proxy configuration
- **THEN** its browser context is created with that proxy and traffic egresses through it

#### Scenario: Proxy credentials masked

- **WHEN** a proxy with credentials is read in the UI or appears in a trace
- **THEN** the credentials are masked, never shown in plaintext

### Requirement: Default proxy

The system SHALL support a default proxy applied to runs that do not specify one.

#### Scenario: Default applied

- **WHEN** a default proxy is configured and a run specifies none
- **THEN** the run uses the default proxy
