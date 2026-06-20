## ADDED Requirements

### Requirement: Navigate session page for picker

The system SHALL expose `POST /api/browser-sessions/{session_id}/navigate` accepting `{ "url": string }` that navigates the session's active page to the given URL and waits for `domcontentloaded`.

#### Scenario: Successful navigation

- **WHEN** a client sends a valid absolute URL for a live session
- **THEN** the session page navigates to that URL
- **AND** the response includes `{ "url": "<final_url>", "title": "<page_title>" }`
- **AND** `last_activity_at` is updated

#### Scenario: Session not live

- **WHEN** the session is not `live` in memory
- **THEN** the API SHALL return HTTP 409 with an actionable error

### Requirement: Capture session screenshot for picker

The system SHALL expose `GET /api/browser-sessions/{session_id}/screenshot` returning a JPEG image and viewport metadata `{ width, height, deviceScaleFactor }`.

#### Scenario: Screenshot of current page

- **WHEN** a client requests a screenshot for a live session
- **THEN** the response Content-Type is `image/jpeg`
- **AND** response headers or a companion JSON endpoint include viewport dimensions for coordinate mapping

### Requirement: Pick element at coordinates (Phase 1)

The system SHALL expose `POST /api/browser-sessions/{session_id}/pick-element` accepting `{ "x": number, "y": number }` viewport coordinates and returning `{ "candidates": SelectorCandidate[], "element_summary": { tag, role, name, text } }`.

#### Scenario: Pick on interactive element

- **WHEN** coordinates resolve to a button element
- **THEN** the response includes at least one candidate with `match_count >= 1`
- **AND** `element_summary.role` reflects the element's accessible role when available

#### Scenario: Pick while session locked by picker

- **WHEN** the session has an active picker lock owned by the same client token
- **THEN** pick-element SHALL succeed

### Requirement: Test selector against session page

The system SHALL expose `POST /api/browser-sessions/{session_id}/test-selector` accepting `{ "selector": string }` and returning `{ "match_count": number, "preview": { tag, text, role, visible } }` using the first matched element.

#### Scenario: Unique selector

- **WHEN** the selector matches exactly one visible element
- **THEN** `match_count` is `1` and `preview.visible` is `true`

#### Scenario: Ambiguous selector

- **WHEN** the selector matches more than one element
- **THEN** `match_count` is `> 1`
- **AND** the response SHALL NOT fail; the UI uses this to warn the author

### Requirement: Picker lock lifecycle

The system SHALL expose:

- `POST /api/browser-sessions/{session_id}/picker/enable` — acquire picker lock, return `{ "picker_token": string }`
- `POST /api/browser-sessions/{session_id}/picker/disable` — release lock and remove any injected picker script (Phase 2)

While picker lock is held:

- Workflow runs attempting to attach the session SHALL receive HTTP 409.
- Only the holder of `picker_token` MAY call pick-element, navigate, screenshot, and test-selector.

#### Scenario: Enable picker lock

- **WHEN** picker/enable is called on a live unattached session
- **THEN** the session enters picker-locked state and returns a picker_token

#### Scenario: Run blocked during picker

- **WHEN** a workflow run tries to attach to a picker-locked session
- **THEN** attach fails with HTTP 409 and message indicating picker is active

#### Scenario: Disable releases lock

- **WHEN** picker/disable is called with valid picker_token
- **THEN** the lock is released regardless of dialog close reason

### Requirement: Injected pick result polling (Phase 2)

The system SHALL expose `GET /api/browser-sessions/{session_id}/picker/result` returning the last element picked via injected script mode, or `{ "pending": true }` when none.

#### Scenario: Click in injected mode

- **WHEN** injected picker mode is active and the user clicks an element in the page
- **THEN** the next poll to picker/result returns `{ "candidates": [...], "picked_at": "<iso>" }`
