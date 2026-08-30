## ADDED Requirements

### Requirement: Desktop Computer Use backend protocol

The system SHALL provide a `DesktopComputerUseBackend` that can list apps, open or activate an app, capture app state (window screenshot + indexed accessibility elements), and perform click, type, key, and scroll actions. Element indices returned by `get_app_state` SHALL be valid only until the next state capture for that app on the same backend instance.

#### Scenario: Fake backend round-trip

- **WHEN** a test uses the FakeBackend with a seeded TextEdit-like app that is Always-allowed
- **THEN** `get_app_state` returns indexed interactive elements
- **AND** `click` / `type_text` update backend state without error

#### Scenario: Element index preferred over coordinates

- **WHEN** both an element index and raw coordinates are available for a click
- **THEN** the agent and tools SHALL prefer the element index
- **AND** coordinates MAY be used only as an explicit fallback when no index is supplied

### Requirement: Platform gate

Computer Use execution SHALL be available on macOS and Windows desktop runtimes. On unsupported platforms the system SHALL return a clear unavailable error rather than silently no-oping.

#### Scenario: Linux unavailable

- **WHEN** the factory resolves a real backend on Linux without an injected FakeBackend
- **THEN** resolution fails with a `DesktopComputerUseUnavailableError` mentioning macOS or Windows

#### Scenario: Injected backend available everywhere

- **WHEN** a FakeBackend is injected for tests
- **THEN** `desktop_computer_use_available` is true and `resolve_desktop_backend` returns the injected backend on any host platform

### Requirement: macOS AX foreground driver

On macOS, the system SHALL provide an Accessibility-based foreground backend that activates the target app, reads the AX tree, captures a window screenshot, and synthesizes mouse/keyboard input. Constructing the backend without the `desktop-macos` extras SHALL fail with a clear unavailable error.

#### Scenario: macOS extras missing

- **WHEN** `MacOSDesktopComputerUseBackend` is constructed without pyobjc frameworks installed
- **THEN** it raises `DesktopComputerUseUnavailableError` describing `desktop-macos` extras

#### Scenario: Foreground activation

- **WHEN** a macOS backend performs `open_app` or `get_app_state` for an authorized app
- **THEN** it attempts to bring that app to the foreground before capturing state or injecting input

### Requirement: Windows UIA foreground driver

On Windows, the system SHALL provide a UI Automation-based foreground backend that lists visible app windows, captures window state (screenshot + indexed elements), and performs click/type/key/scroll after app authorization. Constructing the backend without the `desktop-windows` extras SHALL fail with a clear unavailable error.

#### Scenario: Windows extras missing

- **WHEN** `WindowsDesktopComputerUseBackend` is constructed without pywinauto/Pillow installed
- **THEN** it raises `DesktopComputerUseUnavailableError` describing `desktop-windows` extras

#### Scenario: Target window must be resolvable

- **WHEN** `get_app_state` is called for an authorized app whose window cannot be found
- **THEN** the backend fails with a clear unavailable or not-found error (it does not hang indefinitely)

### Requirement: Browser versus desktop routing

When a browser Playwright session already exists for the run, the system SHALL prefer existing browser / vision tools for web tasks. Desktop Computer Use tools SHALL be used for native applications, when no browser session exists, or when the user explicitly requests desktop operation.

#### Scenario: Prefer browser tools for web session

- **WHEN** an autonomous task has an active Playwright page and the objective is a website interaction
- **THEN** the agent is instructed / routed to use browser vision tools rather than `desktop_*` tools for that interaction

#### Scenario: Desktop tools for native app

- **WHEN** the objective targets a native application (for example TextEdit or Notepad)
- **THEN** the agent MAY call `list_apps`, `open_app`, and other `desktop_*` tools against the DesktopComputerUseBackend

### Requirement: Same-app concurrency limit

The system SHALL allow at most one active Computer Use task against the same application at a time.

#### Scenario: Second task on same app rejected or queued

- **WHEN** a Computer Use task is already running against app A
- **AND** another task attempts to start Computer Use against app A
- **THEN** the second attempt fails with a clear conflict error or waits until the first task releases app A
- **AND** it MUST NOT interleave input against the same app without coordination

### Requirement: Screen lock and sleep failure

When the host screen is locked or the session is unavailable for GUI input, Computer Use actions SHALL fail with a diagnostic error. Locked-use automatic unlock is out of scope for v1.

#### Scenario: Locked session fails clearly

- **WHEN** a desktop action is attempted while the OS session cannot accept GUI input (locked / no interactive desktop)
- **THEN** the action fails with an error that indicates the session is unavailable
- **AND** the system does not silently report success

### Requirement: Driver swappability for background cursor

The backend protocol SHALL keep input synthesis behind a replaceable driver boundary so a future BackgroundCursorDriver can replace foreground input without changing tool or node contracts.

#### Scenario: Provider id distinguishes drivers

- **WHEN** a foreground backend is resolved
- **THEN** it exposes a stable `provider_id` (for example `macos_foreground` or `windows_foreground`)
- **AND** tools/nodes depend only on the backend protocol, not on driver internals
