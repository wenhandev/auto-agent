## ADDED Requirements

### Requirement: Single Workflow Contract

The system SHALL define a single `Workflow` JSON shape consisting of `nodes`, `edges`, and a `start_id` that is the canonical contract between the planner, the canvas, and the executor.

#### Scenario: Schema parity across components

- **WHEN** the planner emits a `Workflow`
- **THEN** the same JSON SHALL deserialize into the backend `pydantic` `Workflow` model and SHALL render in the React Flow canvas without translation, and the backend executor SHALL be able to walk that exact graph.

### Requirement: Node Type Enum

The system SHALL support exactly the following node types: `start`, `end`, `navigate`, `click`, `fill`, `extract`, `wait`, `fuzzy_action`, `condition`.

#### Scenario: Validation rejects unknown types

- **WHEN** a workflow contains a node with a type outside the enum
- **THEN** pydantic validation SHALL fail with a clear error before execution.

### Requirement: Edge Branching Hints

Each `Edge` SHALL carry an optional `when` field with allowed values `"true"`, `"false"`, or `null` for use by `condition` nodes.

#### Scenario: Condition node selects branch

- **WHEN** the executor reaches a `condition` node with two outgoing edges (`when="true"` and `when="false"`)
- **THEN** the executor SHALL follow the edge whose `when` matches the condition's evaluated result; in the POC default the executor SHALL follow `when=="true"`.

### Requirement: Human-Readable Labels

Each `Node` SHALL expose a `label` string written in the user's vocabulary (Chinese or English) for display on the canvas, distinct from any internal selector or URL parameter.

#### Scenario: Label visible on canvas

- **WHEN** the canvas renders a node
- **THEN** the node's `label` SHALL be shown as the main text and `params` SHALL remain hidden by default.
