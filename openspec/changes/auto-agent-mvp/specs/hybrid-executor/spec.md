## ADDED Requirements

### Requirement: Async Graph Walker

The backend SHALL provide an async executor that, given a `Workflow`, walks from `start_id` following `edges` and `await`s exactly one action per node.

#### Scenario: Linear walk

- **WHEN** the workflow has a strictly linear chain of nodes
- **THEN** the executor SHALL visit them in order, awaiting each action to completion before the next begins.

### Requirement: Deterministic Action Routing

For node types `navigate`, `click`, `fill`, `wait`, `extract`, the executor SHALL dispatch to the matching async function in `app/tools/actions.py` and pass `params` directly.

#### Scenario: Navigate dispatch

- **WHEN** a node with `type="navigate"` and `params={"url":"https://example.com"}` is reached
- **THEN** the executor SHALL call `await actions.navigate("https://example.com")`.

### Requirement: Fuzzy Action Routing

For nodes of type `fuzzy_action`, the executor SHALL invoke `FuzzyAgent.run_fuzzy_action(instruction, page, on_progress)` and forward the `on_progress` callback so the agent's per-step messages reach the WebSocket as `node_progress` events.

#### Scenario: Progress events flow

- **WHEN** the FuzzyAgent emits a sub-step message
- **THEN** the executor SHALL emit `{event:"node_progress", node_id, message, ts}` over the active WebSocket BEFORE the next sub-step starts.

### Requirement: Single Headed Chromium Singleton

The executor SHALL use a process-wide singleton Playwright Chromium launched with `headless=False` (configurable via `BROWSER_HEADLESS`), shared across all action calls within a session.

#### Scenario: One window per session

- **WHEN** multiple `navigate` nodes run within a single workflow
- **THEN** all SHALL navigate the same Chromium tab.

### Requirement: Failure Isolation

If an action raises, the executor SHALL emit `node_failed` with an error string for the offending node and stop traversal without crashing the WebSocket handler.

#### Scenario: Bad selector

- **WHEN** a `click` action throws because the selector is missing
- **THEN** the executor SHALL emit `node_failed` for that node and SHALL NOT raise out of the WebSocket handler.

### Requirement: Condition Node Default Branch

For `condition` nodes in the POC, the executor SHALL evaluate `params["expr"]` in a small restricted context (defaulting to truthy) and follow the outgoing edge whose `when` matches; if no expression is provided it SHALL follow the `when=="true"` edge.

#### Scenario: Missing expression

- **WHEN** a condition node has no `params["expr"]` and two outgoing edges
- **THEN** the executor SHALL follow the `when=="true"` edge.
