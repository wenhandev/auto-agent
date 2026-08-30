## ADDED Requirements

### Requirement: Desktop observation after desktop tools

When an autonomous run is operating in a desktop context (desktop tools in use against a native app, or an explicit desktop runtime selection), the observe step after a desktop tool SHALL refresh observation from desktop app state (`get_app_state` / equivalent mapped Observation), not from a browser Playwright page that was not the action target.

#### Scenario: Post-click desktop observe

- **WHEN** the agent successfully executes `desktop_click` (or other mutating desktop tool) against app A
- **AND** the run is in desktop context
- **THEN** the next observation used for decide is derived from app A's desktop state
- **AND** it is not solely a stale browser page perception

#### Scenario: Browser web session still prefers browser observe

- **WHEN** the objective is website interaction with an active Playwright page and no desktop context
- **THEN** the agent continues to use browser perception for observe steps

### Requirement: Default tool surface split

Default allowed tools for browser-centric autonomous tasks SHALL NOT automatically include the full desktop tool set. Desktop tools SHALL be available when the task explicitly allows them, selects a desktop runtime, or otherwise opts into native app automation.

#### Scenario: Browser default excludes desktop tools

- **WHEN** a new autonomous task uses the default browser-oriented tool set
- **THEN** `list_apps` / `desktop_click` and sibling desktop tools are absent from the default allowed set
- **AND** they can still be enabled by explicit configuration

### Requirement: Desktop-aware destructive guardrails

Destructive-action detection for `desktop_click` / related desktop tools SHALL evaluate the desktop target (element name/role from the desktop observation or backend index map for that app). It MUST NOT treat browser page `observation.elements[index]` as the desktop click target.

#### Scenario: Desktop index not confused with browser index

- **WHEN** guardrails evaluate `desktop_click` with index N
- **AND** a browser observation also has an element at index N with a different name
- **THEN** the guardrail decision uses the desktop target identity
- **AND** it does not approve/deny solely based on the browser element at N

### Requirement: Production DesktopAgent LLM decide

When a workflow run has a configured runtime LLM, `desktop_act` and `desktop_navigate` SHALL use an LLM-backed decide function for observe→act decisions. The heuristic decide path remains for tests and environments without an LLM.

#### Scenario: Navigate with LLM does not one-step succeed

- **WHEN** `desktop_navigate` runs with an LLM decide function and a multi-step goal
- **THEN** the node does not treat the first successful heuristic action as automatic goal completion
- **AND** it continues the bounded loop until the goal succeeds, fails, or `max_steps` is exhausted

#### Scenario: Heuristic navigate without false success in production

- **WHEN** `desktop_navigate` runs without an LLM decide function in a production executor path
- **THEN** the node MUST NOT report `completed: true` solely because the first heuristic action succeeded
- **AND** tests MAY still use an explicit heuristic/test mode that allows short-circuit completion

### Requirement: Run-scoped desktop app lock holder

Autonomous desktop tool execution within a single run SHALL reuse a stable lock holder identity for the run (or for the continuous desktop context), rather than minting a new holder UUID per individual tool call that immediately releases mid-run coordination.

#### Scenario: Sequential tools same app same run

- **WHEN** two sequential desktop tools in one autonomous run target the same app
- **THEN** they do not fail with busy/lock errors solely because each tool used a distinct ephemeral holder id
