## ADDED Requirements

### Requirement: Computer Use settings IPC parity

The embedded desktop runtime IPC layer SHALL expose get/put operations for Computer Use settings that are semantically equivalent to the daemon HTTP `/settings/computer-use` endpoints, including Always-allow list read/write used by the desktop client Settings UI.

#### Scenario: IPC get computer-use settings

- **WHEN** the desktop client requests Computer Use settings through the embedded runtime path (`runtimeFetch` / mapped IPC)
- **THEN** the call succeeds with the same settings shape as the HTTP API
- **AND** it does not fail with a missing IPC mapping error

#### Scenario: IPC put updates allowlist

- **WHEN** the desktop client puts an updated Always-allow list through the embedded runtime path
- **THEN** subsequent get reflects the update
- **AND** unauthorized apps remain blocked by the backend auth gate

### Requirement: Insertable desktop workflow nodes

The desktop workflow authoring UI SHALL allow inserting `desktop_open`, `desktop_act`, `desktop_navigate`, and `desktop_extract` nodes from the standard insert/action palette (not only via raw JSON or planner output).

#### Scenario: Palette includes desktop group

- **WHEN** a user opens the workflow insert actions list in the desktop client
- **THEN** the four `desktop_*` node types are offered as insertable actions
- **AND** selecting one creates a node with the corresponding type and editable params

### Requirement: Dual Computer Use naming clarity

Product copy and technical docs that surface both stacks SHALL distinguish Playwright coordinate Computer Use (`computer_use_enabled` / browser fallback) from native desktop Computer Use (platform backend + app allowlist). Settings MUST NOT imply that toggling the Playwright flag enables native desktop automation.

#### Scenario: Docs and settings do not conflate stacks

- **WHEN** a user reads desktop Computer Use settings help or architecture docs covering both features
- **THEN** the two mechanisms are named and described as separate controls
- **AND** enabling browser coordinate fallback alone does not claim native app automation is on
