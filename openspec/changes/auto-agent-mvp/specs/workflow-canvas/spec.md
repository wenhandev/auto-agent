## ADDED Requirements

### Requirement: React Flow Canvas with Custom Glow Node

The frontend SHALL render the `Workflow` using `@xyflow/react` with a single registered custom node type named `glow`.

#### Scenario: Sample workflow renders

- **WHEN** the app starts and successfully fetches `/api/sample-workflow`
- **THEN** the canvas SHALL render all six sample nodes as instances of the `glow` node type with their `label` text visible.

### Requirement: Four Visual Status States

The `GlowNode` component SHALL visually distinguish four states driven by `data.status`: `idle`, `running`, `success`, `error`.

#### Scenario: Running state pulses

- **WHEN** the node's status is `running`
- **THEN** the node SHALL display an animated halo implemented via a CSS `@keyframes` rule that animates `box-shadow`.

#### Scenario: Success and error states

- **WHEN** the node's status is `success` or `error`
- **THEN** the node SHALL show a green checkmark and green border, or a red label and red border, respectively.

### Requirement: Fuzzy Sub-Progress Subtitle

When a node is in `running` state and has a non-empty `message`, the `GlowNode` SHALL render a one-line subtitle beneath the label with an animated shimmer background.

#### Scenario: Subtitle updates per progress event

- **WHEN** the frontend receives a `node_progress` event for the running node
- **THEN** the subtitle text SHALL update to the event's `message` without remounting the node.

### Requirement: Dagre Auto-Layout

On first load and on each replacement of the workflow, the canvas SHALL compute positions with `dagre` in top-down direction and pass them to React Flow.

#### Scenario: Layout on workflow replacement

- **WHEN** the workflow object is replaced (e.g. after `/api/workflow/generate`)
- **THEN** the canvas SHALL recompute node positions via dagre before next render.
