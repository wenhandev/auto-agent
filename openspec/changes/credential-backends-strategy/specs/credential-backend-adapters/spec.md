## ADDED Requirements

### Requirement: Local backend (default)

The system SHALL provide a `local` backend wrapping the existing Fernet vault, supporting read/write/list/delete, mounted as the default.

#### Scenario: Local backend preserves vault behaviour

- **WHEN** the `local` backend resolves a credential
- **THEN** it returns the same fields the Fernet vault returned before this change

### Requirement: Environment-variable backend

The system SHALL provide a read-only `env` backend resolving fields from environment variables by a configured name prefix.

#### Scenario: Resolve from env

- **WHEN** `AUTOAGENT_CRED_GITHUB_PASSWORD` is set and the `env` backend resolves `github.password`
- **THEN** it returns the environment value
- **AND** a write attempt is rejected (read-only)

### Requirement: External vault adapters

The system SHALL provide read-mostly adapters for Bitwarden, 1Password, Azure Key Vault, and a generic custom HTTP vault, each declaring its capabilities and failing fast when its tooling is unavailable.

#### Scenario: Bitwarden adapter resolves a secret

- **WHEN** the `bitwarden` adapter is configured and resolves a linked credential
- **THEN** it returns the secret fields via the Bitwarden CLI/API

#### Scenario: Missing CLI probed at config time

- **WHEN** a CLI-based adapter is configured but its CLI is not installed
- **THEN** the connection test reports the missing tool and the adapter is not marked active

#### Scenario: Custom HTTP vault

- **WHEN** the `http_vault` adapter is configured with a URL + auth header and resolves `name`
- **THEN** it issues `GET {url}/{name}` and maps the JSON response to credential fields
