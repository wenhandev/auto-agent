## ADDED Requirements

### Requirement: Observe elements with bounding boxes (Phase 3)

The system SHALL expose `GET /api/browser-sessions/{session_id}/observe-elements` returning interactive elements with viewport-relative bounding boxes:

```json
{
  "elements": [
    { "index": 0, "role": "button", "name": "Continue", "ref": "...", "box": { "x": 120, "y": 340, "width": 80, "height": 32 } }
  ],
  "viewport": { "width": 1280, "height": 720 }
}
```

Elements SHALL be sourced from the same interactive-role walk as `perception.py`, capped at 80 entries.

#### Scenario: Observe returns boxes for visible buttons

- **WHEN** the session page displays three visible buttons
- **THEN** observe-elements includes those buttons with non-null `box` values

#### Scenario: Offscreen element omitted or null box

- **WHEN** an interactive element has no bounding box (display:none or offscreen)
- **THEN** it is omitted from the response or returned with `"box": null`

### Requirement: Observe overlay in picker dialog (Phase 3)

The ElementPickerDialog SHALL support a third mode **Element list** that:

- Fetches `observe-elements` and draws SVG (or HTML) overlays on the screenshot aligned to `box` coordinates
- Allows selecting an element by clicking its overlay or list row
- Runs `selector_builder` on the selected element without coordinate mapping

#### Scenario: Select from overlay

- **WHEN** the author clicks an overlay box labeled "Download Summary INV-2024-3325"
- **THEN** selector candidates are shown for that element

### Requirement: Standalone Selector Debug page (Phase 3)

The frontend SHALL provide route `/selector-debug` (linked from Settings or Browser Sessions) with:

- Session management (same as picker dialog)
- URL bar with navigate
- Full-height screenshot + observe overlay
- Selector test console (input selector, run test-selector, show match preview)
- Pick history panel (last 10 picks in session)

This page is independent of workflow editing.

#### Scenario: Debug page test selector

- **WHEN** the user enters `[data-testid="ticket-category"]` and clicks Test
- **THEN** match count and element preview are displayed without modifying any workflow

### Requirement: Recording emits selector candidates (Phase 3)

When a recording captures a `click` or `fill` event, the system SHALL attach `selector_candidates` from `selector_builder` when the target element can be resolved, in addition to the existing `selector` field (`#id` or null).

Each recorded event MAY include:

```json
{
  "selector": "#legacy",
  "selector_candidates": [
    { "selector": "[data-testid=\"login-submit\"]", "strategy": "data-testid", "confidence": 0.95, "match_count": 1 }
  ]
}
```

#### Scenario: Recorded click with testid

- **WHEN** the user clicks a button with `data-testid` during recording
- **THEN** the stored event includes `selector_candidates` with a data-testid strategy entry

### Requirement: Apply recorded selector to workflow (Phase 3)

The Recording Detail page SHALL show selector candidates on click/fill events with **Copy selector** and **Use in workflow** actions.

**Use in workflow** SHALL open a node picker (or chat prefill) to paste the selector into a chosen `click`/`fill` node — mirroring the self-heal adopt pattern (operator confirms before mutation).

#### Scenario: Copy selector from recording

- **WHEN** the user clicks Copy selector on a recorded event candidate
- **THEN** the selector string is copied to the clipboard

### Requirement: Integration with selector cache (optional Phase 3)

When a selector is applied to a workflow node from the picker or recording, the client MAY offer **Save to selector cache** if the workflow is saved and the node has a stable id.

This action SHALL call the existing selector cache write path keyed by `(workflow_id, node_id, url_pattern)`.

#### Scenario: Save to cache offered after apply

- **WHEN** the author applies a picker selector to a saved workflow node
- **THEN** an optional Save to cache checkbox is available
- **AND** when checked, the cache entry is written after Apply
