## ADDED Requirements

### Requirement: On-device LLM configuration

The desktop app SHALL provide a Settings screen for LLM provider configuration (provider, model, credentials) used by agent, vision, recording synthesis, and autonomous steps during local execution.

#### Scenario: User configures API key

- **WHEN** the user saves LLM settings in the desktop app
- **THEN** credentials are stored locally using OS keychain when available, otherwise an encrypted local store
- **AND** subsequent runs on this device use direct model calls without the cloud LLM proxy

#### Scenario: Missing LLM configuration

- **WHEN** the user starts a run containing LLM-dependent nodes without configured credentials
- **THEN** the app blocks or fails the run with a clear message pointing to Settings
- **AND** does not silently fall back to cloud LLM keys without user consent

### Requirement: Local LLM for desktop execution

Runs initiated from the desktop app or dispatched to the desktop sidecar SHALL invoke LLM providers from the local configuration.

#### Scenario: Vision step uses local model

- **WHEN** a vision action node runs on the desktop sidecar
- **THEN** prompts and screenshots are sent to the configured local LLM provider
- **AND** screenshot bytes are not required to pass through the cloud LLM proxy
