## ADDED Requirements

### Requirement: Cross-platform desktop application

The product SHALL ship a native desktop application installable on macOS, Windows, and Linux as the **primary** user-facing deliverable (not the CLI worker alone).

#### Scenario: User installs from platform artifact

- **WHEN** a user downloads the desktop installer for their OS
- **THEN** they can launch **Auto Agent** without installing Python separately
- **AND** the app presents a graphical login screen

#### Scenario: System tray presence

- **WHEN** the app is running and the user minimizes or closes the main window
- **THEN** the app MAY remain available via a system tray icon showing connection status
- **AND** the user can reopen the main window or quit from the tray

### Requirement: Login and logout in app

The desktop app SHALL authenticate with cloud URL, email, and password using the same identity system as the web UI, and SHALL persist session credentials locally for reconnect.

#### Scenario: Successful login

- **WHEN** the user submits valid credentials on the login screen
- **THEN** the app stores a worker-scoped session token locally
- **AND** navigates to the main application shell

#### Scenario: Logout

- **WHEN** the user chooses Log out
- **THEN** the app clears local session credentials
- **AND** closes the outbound worker WebSocket
- **AND** returns to the login screen

### Requirement: Connection status indicator

The app shell SHALL display whether the device is connected to the cloud control plane and the outcome of the latest environment preflight.

#### Scenario: Connected and ready

- **WHEN** the sidecar reports `environment_status=ready` and the worker WebSocket is open
- **THEN** the shell shows a connected/ready indicator (e.g. green status)

#### Scenario: Degraded or not ready

- **WHEN** preflight reports `degraded` or `not_ready`
- **THEN** the shell shows a warning with a link to Settings or doctor details
- **AND** the user can still access local drafts but cloud dispatch MAY be blocked
