## ADDED Requirements

### Requirement: Autonomous desktop tool surface

Autonomous task mode SHALL expose desktop tools `list_apps`, `open_app`, `get_app_state`, `desktop_click`, `desktop_type`, `desktop_key`, and `desktop_scroll`. These tools SHALL appear in `tool_schemas` / LLM tool builders when included in the task's allowed tools, and `_execute_tool` SHALL dispatch them to `resolve_desktop_backend()`.

#### Scenario: Tools listed in schemas

- **WHEN** desktop tools are included in the allowed tool set
- **THEN** `tool_schemas` includes `list_apps`, `open_app`, `get_app_state`, `desktop_click`, `desktop_type`, `desktop_key`, and `desktop_scroll`

#### Scenario: Tool dispatch through FakeBackend

- **WHEN** a FakeBackend is injected and Always-allow includes TextEdit
- **AND** `_execute_tool` is called with `get_app_state` / `desktop_type` for TextEdit
- **THEN** the calls succeed and return structured results (not `unknown tool`)

#### Scenario: Unavailable backend returns tool error

- **WHEN** no backend can be resolved (unsupported platform and no injection)
- **THEN** desktop tool execution returns an error payload to the agent
- **AND** it does not crash the autonomous run loop

### Requirement: Workflow desktop_open node

The workflow schema SHALL include `desktop_open` with params `{ app: string }`. The executor SHALL open or activate the app via the DesktopComputerUseBackend.

#### Scenario: desktop_open activates app

- **WHEN** a `desktop_open` node runs with `app` set to an Always-allowed FakeBackend app
- **THEN** the node returns the resolved app identity (`app_id` / `name` / `bundle_id`)
- **AND** the backend records an open/activate action

### Requirement: Workflow desktop_act node

The system SHALL provide a `desktop_act` node type that performs exactly one observe→decide→act cycle against a native app from params `{ app, instruction }`, analogous to `vision_act`.

#### Scenario: Single desktop action

- **WHEN** a `desktop_act` node runs with instruction to type into a text field
- **THEN** the agent captures state, performs one action, and completes
- **AND** at least one `desktop_step` event is emitted

### Requirement: Workflow desktop_navigate node

The system SHALL provide a `desktop_navigate` node type that runs a bounded observe→decide→act loop toward params `{ app, goal, max_steps? }`, analogous to `vision_navigate`.

#### Scenario: Goal progress within budget

- **WHEN** a `desktop_navigate` node runs with a reachable goal and sufficient `max_steps`
- **THEN** the node completes with `completed: true` (or equivalent success fields)
- **AND** `desktop_step` events are emitted for perceive/action steps

#### Scenario: Max steps exhausted

- **WHEN** a `desktop_navigate` node cannot finish within `max_steps`
- **THEN** the node completes without crashing the run
- **AND** the output indicates the step budget was exhausted

### Requirement: Workflow desktop_extract node

The system SHALL provide a `desktop_extract` node type with params `{ app, instruction, schema? }` that returns structured data derived from the current app state observation.

#### Scenario: Extract without schema

- **WHEN** a `desktop_extract` node omits `schema`
- **THEN** the node returns completed output including title/elements (or equivalent structured data) matching the instruction

#### Scenario: Extract failure is explicit

- **WHEN** `desktop_extract` cannot complete successfully
- **THEN** the executor surfaces a clear failure (raised error or `completed: false`) rather than a silent empty success

### Requirement: Per-step desktop_step event

Each perceive/action step of desktop nodes (and desktop agent loops) SHALL emit a `desktop_step` event capturing at least `app`, `step_index`, `thought`, `action`, `target_index` (nullable), and `screenshot_ref`.

#### Scenario: desktop_step shape

- **WHEN** `desktop_act` runs successfully against FakeBackend
- **THEN** at least one emitted `desktop_step` includes `app`, `action`, and `screenshot_ref`
- **AND** the event type name is `desktop_step` (parallel to `vision_step`)

### Requirement: DesktopAgent loop

The system SHALL provide a `DesktopAgent` that can `run_act`, `run_navigate`, and `run_extract` against a `DesktopComputerUseBackend`, emitting `desktop_step` callbacks. Keyless / test environments MAY use a deterministic heuristic decide path; production MAY use an LLM decide function without changing node contracts.

#### Scenario: Heuristic type action

- **WHEN** `DesktopAgent.run_act` is invoked with instruction containing a type/write intent against a FakeBackend text field
- **THEN** the backend receives a `type_text` action on a textfield index
- **AND** the node/agent result reports completion success when the action succeeds

### Requirement: Schema and editor surfacing

`NodeType` SHALL include `desktop_open`, `desktop_act`, `desktop_navigate`, and `desktop_extract`. The desktop client workflow inspector SHALL expose params editors for `app`, `instruction` / `goal`, and optional `max_steps` where applicable.

#### Scenario: Node types accepted by schema

- **WHEN** a workflow JSON includes a node with `type: "desktop_navigate"` and valid params
- **THEN** schema validation accepts the node type
- **AND** the executor has a dispatch branch for that type
