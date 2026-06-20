## ADDED Requirements

### Requirement: Pick Element button on click and fill nodes

The workflow NodeInspector SHALL display a **Pick Element** control adjacent to the `selector` parameter field when the selected node type is `click` or `fill`.

#### Scenario: Button visible for click node

- **WHEN** the author selects a `click` node in the workflow editor
- **THEN** the selector field shows a Pick Element button

#### Scenario: Button hidden for navigate node

- **WHEN** the author selects a `navigate` node
- **THEN** no Pick Element button is shown

### Requirement: Element picker dialog (Phase 1)

Opening Pick Element SHALL launch `ElementPickerDialog` with:

1. Browser session selector (list live sessions + create new)
2. URL input and **Go** button
3. Screenshot viewport with click-to-pick interaction
4. Candidate selector list with strategy label and match count
5. **Apply** (writes selected candidate to node `selector` param) and **Cancel**
6. **Test** button for the highlighted candidate

#### Scenario: Apply writes selector to node

- **WHEN** the author picks an element, selects a candidate, and clicks Apply
- **THEN** the node's `params.selector` is updated
- **AND** the dialog closes
- **AND** the workflow canvas reflects the unsaved change

#### Scenario: Cancel discards selection

- **WHEN** the author clicks Cancel
- **THEN** node params are unchanged
- **AND** picker lock is released via picker/disable

### Requirement: Coordinate mapping on screenshot

The picker dialog SHALL map click coordinates on the displayed screenshot to viewport coordinates using the ratio between displayed image size and server-reported viewport `{ width, height }`.

#### Scenario: Scaled screenshot click

- **WHEN** the screenshot is displayed at 50% scale and the author clicks the center of a button
- **THEN** the pick-element request sends viewport coordinates corresponding to the button center, not raw pixel coordinates on the img element

### Requirement: Session and URL defaults

The picker dialog SHALL attempt to pre-fill the URL field from:

1. The nearest upstream `navigate` node's `url` param in the workflow graph, if any
2. Otherwise empty, requiring manual entry

#### Scenario: Prefill from navigate node

- **WHEN** the `click` node has a predecessor `navigate` node with `url` set
- **THEN** the URL field in the picker dialog is pre-filled with that URL

### Requirement: Picker lock acquired for dialog lifetime

The frontend SHALL call `picker/enable` when the dialog opens and `picker/disable` when it closes (Apply, Cancel, or unmount).

#### Scenario: Dialog unmount releases lock

- **WHEN** the author closes the dialog via the X button
- **THEN** picker/disable is invoked

### Requirement: Error states surfaced in dialog

The dialog SHALL display actionable errors for: no live sessions, session expired, navigation failure, pick failure, and selector test with `match_count === 0`.

#### Scenario: Expired session

- **WHEN** the selected session is not live
- **THEN** the dialog shows an error with option to create a new session
