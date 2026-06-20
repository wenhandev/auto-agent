## ADDED Requirements

### Requirement: Browser provider abstraction

The system SHALL provide a browser provider abstraction so runs can use local Playwright by default and compatible remote or cloud browser providers through the same runtime interface.

#### Scenario: Default provider remains local Playwright

- **WHEN** a run or browser session is created without a provider override
- **THEN** the system uses the existing local Playwright-backed browser runtime
- **AND** existing workflow and autonomous task behavior remains unchanged

#### Scenario: Provider metadata recorded

- **WHEN** a browser session or run uses a browser provider
- **THEN** the system records the provider identifier and relevant non-secret connection metadata for audit and debugging

### Requirement: Provider capability checks

The system SHALL expose provider capabilities and fail clearly when a requested runtime feature is unsupported.

#### Scenario: Unsupported capability rejected

- **WHEN** a run requests a feature that the selected provider does not support
- **THEN** the system rejects the run or step with a clear unsupported-capability error
- **AND** it does not silently degrade to a weaker behavior

#### Scenario: Supported capability proceeds

- **WHEN** a provider advertises support for a requested capability
- **THEN** the system allows the run or session to use that capability through the provider interface

### Requirement: Remote CDP provider

The system SHALL support a remote CDP provider that attaches to an existing browser endpoint when configured.

#### Scenario: Create session from remote CDP

- **WHEN** a client creates a browser session with a remote CDP provider and valid endpoint configuration
- **THEN** the system attaches to the remote browser and stores a live session record

#### Scenario: Remote CDP endpoint secret handling

- **WHEN** remote CDP configuration includes credentials or tokens
- **THEN** the system does not expose those secrets in public API responses, run events, or logs
