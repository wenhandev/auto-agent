## ADDED Requirements

### Requirement: Desktop observation from accessibility tree

The system SHALL build a desktop observation from a target app window by combining (1) a window (or display) screenshot and (2) an indexed list of interactive accessibility elements derived from the platform accessibility tree (macOS AX or Windows UIA). The observation SHALL be mappable into the shared `Observation` shape used by browser vision so agents can reuse compact payloads.

#### Scenario: Indexed interactive elements

- **WHEN** `get_app_state` succeeds for an authorized app with interactive controls
- **THEN** the returned state includes an `elements` list where each element has `index`, `role`, and `name`
- **AND** indices are contiguous starting at 0 for that capture

#### Scenario: Compact payload for LLM

- **WHEN** `compact_desktop_observation` / `Observation.compact_payload` is produced from a desktop state
- **THEN** the payload includes app identity, title, `screenshot_ref`, and a bounded element list
- **AND** it does not include raw full-tree dumps beyond the indexed interactive subset

### Requirement: Screenshot artifact reference

Each successful state capture SHALL produce screenshot bytes and a `screenshot_ref` suitable for run artifacts and `desktop_step` events.

#### Scenario: Screenshot ref present

- **WHEN** FakeBackend or a real backend captures app state
- **THEN** `screenshot_ref` is a non-empty string
- **AND** `screenshot_bytes` are PNG bytes (possibly empty only when capture is explicitly skipped in test stubs)

### Requirement: Parallel to browser perception

Desktop perception SHALL NOT replace browser `perception.py`. Browser pages continue to use Playwright accessibility snapshots; desktop apps use AX/UIA through `desktop_perception` / the Computer Use backend.

#### Scenario: Browser perception unchanged

- **WHEN** a `vision_act` node runs against a Playwright page
- **THEN** it continues to use browser perception
- **AND** it does not require a DesktopComputerUseBackend

### Requirement: Accessibility-first with screenshot fallback role

The primary targeting signal SHALL be accessibility element indices. Screenshots SHALL be available to the model for visual grounding and for UIs with weak accessibility trees; coordinate clicks remain a secondary fallback, not the default path.

#### Scenario: Weak AX still returns screenshot

- **WHEN** an app window exposes few or no interactive AX/UIA nodes
- **THEN** `get_app_state` still returns a screenshot_ref when capture succeeds
- **AND** the elements list MAY be empty without crashing the capture
