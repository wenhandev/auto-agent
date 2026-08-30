## ADDED Requirements

### Requirement: Two-layer permission model

Desktop Computer Use SHALL enforce two layers of permission: (1) OS system permissions required to see and control the UI, and (2) product-level per-app authorization (Allow once / Always allow / Deny). Missing system permissions SHALL surface actionable guidance rather than failing silently.

#### Scenario: macOS system permission guidance

- **WHEN** the desktop client loads Computer Use settings on macOS
- **THEN** the settings payload includes a hint to grant Screen Recording and Accessibility in System Settings → Privacy & Security

#### Scenario: Windows visibility guidance

- **WHEN** the desktop client loads Computer Use settings on Windows
- **THEN** the settings payload includes a hint to keep the target app visible on the active desktop and to install `desktop-windows` extras when needed

### Requirement: Per-app authorization gate

Before interacting with an application (open, get state, click, type, key, scroll), the backend SHALL require product-level approval unless the app identifier is on the local Always-allow list or has been Allow-once for the current session. Unauthorized attempts SHALL fail with `DesktopAppAuthorizationError` (or equivalent pause for approval).

#### Scenario: Unapproved app blocked

- **WHEN** an agent attempts `open_app` or `get_app_state` for an app that is not Always-allowed and not Allow-once
- **THEN** the action fails with an authorization error
- **AND** no click/type input is injected into that app

#### Scenario: Allow once grants session access

- **WHEN** the user chooses Allow once for app A
- **THEN** subsequent Computer Use actions against app A succeed for the current process session
- **AND** a newly loaded auth store from disk does not treat app A as Always-allowed

#### Scenario: Always allow persists locally

- **WHEN** the user chooses Always allow for app A
- **THEN** app A's identifier is written to a local auth file under the user's Auto Agent data directory
- **AND** a new auth store instance loaded from that file authorizes app A without prompting

### Requirement: Revocable Always-allow list

The desktop Settings → Computer Use surface SHALL list Always-allowed apps and allow the user to revoke any entry. Revocation SHALL take effect for subsequent actions immediately.

#### Scenario: Revoke via settings API

- **WHEN** the client calls the Computer Use settings API with `revoke` set to an Always-allowed app id
- **THEN** that app is removed from the persisted Always-allow list
- **AND** a later unauthorized attempt against that app fails until re-approved

#### Scenario: Allow via settings API

- **WHEN** the client calls the Computer Use settings API with `allow_always` set to a non-forbidden app id
- **THEN** that app appears in `always_allowed` in the settings response

### Requirement: Hard-deny list

The system SHALL refuse to automate Terminal / cmd / PowerShell / Windows Terminal, Auto Agent itself, and OS security / permission / UAC dialogs, even if the user attempts Always allow.

#### Scenario: macOS Terminal denied

- **WHEN** the target app is Terminal or bundle id `com.apple.Terminal`
- **THEN** the backend rejects the action with `DesktopAppForbiddenError`

#### Scenario: Windows shells denied

- **WHEN** the target app is `cmd.exe`, `powershell.exe`, `pwsh.exe`, or Windows Terminal
- **THEN** the backend rejects the action with `DesktopAppForbiddenError`

#### Scenario: Cannot Always-allow forbidden app

- **WHEN** the user attempts Always allow on a hard-denied app
- **THEN** the auth store rejects the request
- **AND** the app is not persisted to the Always-allow list

### Requirement: Local-only auth storage

Always-allow entries SHALL be stored only on the local device. The system MUST NOT upload the Always-allow list to the cloud control plane as part of Computer Use settings sync in v1.

#### Scenario: Settings response is local

- **WHEN** Computer Use settings are read from the local sidecar
- **THEN** `always_allowed` reflects the local auth file only
- **AND** no cloud API call is required to list or revoke entries

### Requirement: Sensitive action confirmation

Destructive or sensitive desktop actions (payment, delete, send message, account settings changes) SHALL reuse the existing autonomous confirmation / HITL gate when `require_confirmation` is enabled.

#### Scenario: Confirmation gate consulted

- **WHEN** `require_confirmation` is true and the agent attempts a classified sensitive desktop action
- **THEN** the confirmation gate is invoked before the action executes
- **AND** a denied confirmation prevents the input from being injected
