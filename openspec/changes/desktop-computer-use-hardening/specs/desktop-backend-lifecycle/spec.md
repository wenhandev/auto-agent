## ADDED Requirements

### Requirement: Process-scoped backend reuse

Without a test injection, `resolve_desktop_backend()` SHALL return the same backend instance for repeated calls on the same process and platform. Element indices returned by `get_app_state` SHALL remain valid for subsequent click/type/key/scroll calls that use those indices until the next `get_app_state` (or equivalent capture) for that app on that instance.

#### Scenario: Cross-tool index click without injection

- **WHEN** no FakeBackend is injected
- **AND** autonomous tools call `get_app_state` then `desktop_click` with an index from that state (same process)
- **THEN** both calls use the same backend instance
- **AND** the click resolves the indexed element without treating the cache as empty

#### Scenario: Test injection still wins

- **WHEN** `set_desktop_backend_for_tests` injects a FakeBackend
- **THEN** `resolve_desktop_backend` returns that instance
- **AND** clearing the injection restores normal resolution behavior

### Requirement: Real dependency availability probe

`desktop_computer_use_available()` SHALL be true only when a usable backend can be constructed on the current platform (including optional extras such as pyobjc or pywinauto/Pillow), or when a test backend is injected. Reporting available solely because `sys.platform` is darwin/win32 WITHOUT being able to construct the backend is NOT sufficient.

#### Scenario: Platform match but extras missing

- **WHEN** the host is macOS or Windows but required desktop extras cannot be imported
- **THEN** `desktop_computer_use_available` is false
- **AND** settings/status payloads MAY include a clear reason string

#### Scenario: Injected backend reports available

- **WHEN** a FakeBackend is injected for tests
- **THEN** `desktop_computer_use_available` is true on any host platform

### Requirement: Hold-scoped activation caching

While a desktop app lock is held for an app, the backend SHOULD avoid redundant full `list_apps` scans and redundant foreground activation between consecutive actions against that same app, unless the target is no longer frontmost or cannot be resolved from cache.

#### Scenario: Consecutive actions under one hold

- **WHEN** multiple desktop actions run under one `hold_desktop_app` for the same app
- **THEN** the implementation does not perform a full fresh app-list resolution on every action solely to re-identify the same target
- **AND** actions still succeed against the locked app

### Requirement: Windows window identity parity

On Windows, app listing and targeting SHALL preserve enough identity to distinguish multiple windows/processes of the same executable when they are separately controllable. `frontmost` SHALL reflect the actual foreground window when the platform API provides it. Failed `open_app` MUST NOT fall back to unrestricted `shell=True` process spawning.

#### Scenario: open_app failure is explicit

- **WHEN** Windows `open_app` cannot start or activate the target through the controlled launch path
- **THEN** the backend returns a clear error
- **AND** it does not invoke an unrestricted shell execute fallback
