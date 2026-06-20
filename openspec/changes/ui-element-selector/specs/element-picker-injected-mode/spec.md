## ADDED Requirements

### Requirement: In-page hover highlight picker (Phase 2)

The system SHALL support an **Injected Picker Mode** activated after `picker/enable` with `{ "mode": "injected" }` (default mode in Phase 1 is `"coordinate"`).

In injected mode, the backend SHALL inject a namespaced script (`window.__autoAgentPicker`) into the session page that:

- Highlights the element under the cursor with a visible outline and tooltip showing tag, id, and accessible name
- On click: prevents default navigation, captures the target element, runs `selector_builder`, stores result for polling
- Does not modify page content except outline/tooltip overlay elements owned by the script

#### Scenario: Hover shows outline

- **WHEN** injected mode is active and the user moves the mouse over a link
- **THEN** the link receives a visible highlight overlay
- **AND** a tooltip displays the element's tag and primary identifier

#### Scenario: Click captures element

- **WHEN** the user clicks a highlighted element
- **THEN** default click behaviour is suppressed for that event
- **AND** `GET picker/result` returns selector candidates on the next poll

### Requirement: Picker script cleanup

The system SHALL remove all picker-injected DOM nodes and event listeners when `picker/disable` is called or the session is closed.

#### Scenario: Disable removes script side effects

- **WHEN** picker/disable succeeds
- **THEN** no picker outline elements remain in the DOM
- **AND** `window.__autoAgentPicker` is undefined or inert

### Requirement: Mode toggle in picker dialog (Phase 2)

The ElementPickerDialog SHALL offer a toggle: **Click on screenshot** (Phase 1 coordinate mode) vs **Pick in browser** (Phase 2 injected mode).

In **Pick in browser** mode:

- The dialog shows a live-refreshed screenshot (polling every 1–2s) for visual feedback
- Instructions tell the author to interact with the headed browser window directly
- Candidate list updates when `picker/result` returns a new pick

#### Scenario: Switch to injected mode

- **WHEN** the author toggles to Pick in browser
- **THEN** the client re-calls picker/enable with `mode: "injected"`
- **AND** screenshot polling continues for preview

### Requirement: Headed browser required for injected mode

When injected mode is requested and `BROWSER_HEADLESS=true`, the API SHALL return HTTP 422 with guidance to use headed mode or fall back to coordinate picking.

#### Scenario: Headless rejection

- **WHEN** injected mode is enabled with headless browser configuration
- **THEN** the API returns HTTP 422
- **AND** the error message suggests coordinate mode or headed browser
