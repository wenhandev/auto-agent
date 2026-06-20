## ADDED Requirements

### Requirement: Credential backend interface

The system SHALL define a `CredentialBackend` interface with `get`/`list`/optional `put`/`delete` and an explicit `capabilities` declaration, and route all credential resolution through a registry of mounted backends.

#### Scenario: Resolution routes through the registry

- **WHEN** a credential is resolved by name
- **THEN** the registry selects the backend by mount and calls its `get`
- **AND** the returned fields are decrypted/normalised into the standard credential shape

#### Scenario: Read-only backend rejects writes

- **WHEN** a write is attempted against a backend whose capabilities exclude `write`
- **THEN** the operation is rejected with a clear "backend is read-only" error and the create form is hidden in the UI

### Requirement: Namespaced credential tokens

The system SHALL resolve `{{cred.<mount>:<name>.<field>}}` against the named mount, and `{{cred.<name>.<field>}}` against the default mount.

#### Scenario: Explicit mount selection

- **WHEN** a node param contains `{{cred.bw:github.password}}`
- **THEN** resolution targets the `bw` mount's `github` entry

#### Scenario: Backward-compatible default

- **WHEN** a node param contains `{{cred.github.password}}` (no mount prefix)
- **THEN** resolution targets the default (local) mount, identical to prior behaviour

### Requirement: Backend configuration and testing

The system SHALL store external-backend connection settings encrypted with the local key and provide a connection test.

#### Scenario: Test a mounted backend

- **WHEN** the operator clicks "测试连接" for a configured backend
- **THEN** the system attempts a capability probe and reports success or an actionable failure

### Requirement: Per-workflow link across backends

The system SHALL key per-workflow credential links on the namespaced identity so scoping is unambiguous across backends.

#### Scenario: Scoped to one mount

- **WHEN** a workflow links `bw:github` and a node references `{{cred.local:github.password}}`
- **THEN** resolution fails with a "not linked to this workflow" error
