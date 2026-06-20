## ADDED Requirements

### Requirement: Vision navigation node

The system SHALL provide a `vision_navigate` node type that drives the page toward a natural-language `goal` using a bounded observe-decide-act loop over the perception layer, requiring no author-supplied selector.

#### Scenario: Goal reached within budget

- **WHEN** a `vision_navigate` node with `goal` runs and the agent calls `done(success=true)` within `max_steps`
- **THEN** the node completes successfully
- **AND** its output includes `{completed: true, summary, steps: <count>}`

#### Scenario: Step budget exhausted

- **WHEN** a `vision_navigate` node does not reach `done` within `max_steps`
- **THEN** the node completes (does not crash the run) with output `{completed: false, reason: "max_steps_reached", last_observation}`

#### Scenario: Default step budget

- **WHEN** a `vision_navigate` node omits `max_steps`
- **THEN** the executor uses `settings.VISION_MAX_STEPS` (default 8)

### Requirement: Vision single-action node

The system SHALL provide a `vision_act` node type that performs exactly one AI-decided action on the current page from a natural-language `instruction`.

#### Scenario: Single action executed

- **WHEN** a `vision_act` node with `instruction: "click the Add to cart button"` runs
- **THEN** the perception layer captures the page, the agent selects one element, performs one action, and the node completes
- **AND** the node performs no further actions even if the goal is not fully satisfied

### Requirement: Vision extraction node

The system SHALL provide a `vision_extract` node type that returns structured data from the current page, validated against an optional JSON Schema.

#### Scenario: Extraction with schema

- **WHEN** a `vision_extract` node supplies a `schema` and the page contains the requested data
- **THEN** the node output is JSON that validates against `schema`
- **AND** IF the first extraction fails validation THEN the agent is asked to repair once before the node fails

#### Scenario: Extraction without schema

- **WHEN** a `vision_extract` node omits `schema`
- **THEN** the node output is free-form JSON matching the instruction with no validation step

### Requirement: Vision tool surface

The vision agent SHALL expose a fixed tool surface (`click_element`, `type_text`, `select_option`, `scroll`, `go_back`, `wait`, `extract`, `done`) where element-targeting tools take an element index from the current observation.

#### Scenario: Action by index

- **WHEN** the agent calls `click_element(2)`
- **THEN** the executor resolves index `2` from the current observation and clicks that element

#### Scenario: Invalid index

- **WHEN** the agent calls a tool with an index not present in the current observation
- **THEN** the tool returns an error observation to the agent (it does not crash the node) and the loop continues

### Requirement: Per-step observability event

Each step of a vision node SHALL emit a `vision_step` event capturing the step index, the agent's thought, the chosen action, the target element index, and a screenshot reference.

#### Scenario: Step event emitted

- **WHEN** the vision agent completes one observe-decide-act step
- **THEN** a `vision_step` event is emitted with `{step_index, thought, action, target_index, screenshot_ref}`
- **AND** the event is persisted as a `RunEvent` when the run is persisted

### Requirement: Backward-compatible fuzzy_action

The system SHALL treat a `fuzzy_action` node as an alias of `vision_navigate`, preserving existing workflows and the keyless demo stub.

#### Scenario: Legacy fuzzy_action still runs

- **WHEN** a workflow containing a `fuzzy_action` node is executed
- **THEN** it runs through the `vision_navigate` engine and emits the same event types
- **AND** WHEN no LLM key is configured THEN the 3-step demo stub runs as before
