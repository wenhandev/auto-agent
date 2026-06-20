## ADDED Requirements

### Requirement: Hybrid observe primitive

The system SHALL provide an `observe` primitive that inspects the current browser page and returns candidate interactive targets without causing page side effects.

#### Scenario: Observe returns candidates without action

- **WHEN** a client calls `observe` with a natural-language instruction on a live page
- **THEN** the system returns candidate elements with refs, labels, roles, confidence, and source metadata
- **AND** the system does not click, type, navigate, submit, or mutate page state

#### Scenario: Observe records trace metadata

- **WHEN** `observe` completes
- **THEN** the run timeline records the instruction, current URL, candidate count, and whether perception or cache contributed to the result

### Requirement: Hybrid act primitive

The system SHALL provide an `act` primitive that resolves a natural-language browser action and executes exactly one page action using cache-first deterministic resolution before invoking LLM/vision fallback.

#### Scenario: Cached act skips LLM

- **WHEN** a valid cached selector or action plan exists for an `act` request on the current URL pattern
- **THEN** the system replays the cached action before calling an LLM
- **AND** the run timeline emits a cache-hit event with avoided cost metadata

#### Scenario: Act falls back to perception

- **WHEN** no cache entry exists or cached replay fails
- **THEN** the system uses fresh perception and the configured LLM/vision resolver to choose one action
- **AND** a successful action is eligible for cache write-through

#### Scenario: Act executes one browser action

- **WHEN** the resolver returns an action
- **THEN** the system executes at most one click, type, select, scroll, navigation, drag, wait, or keypress operation
- **AND** the caller must issue another primitive call for the next step

### Requirement: Hybrid extract primitive

The system SHALL provide an `extract` primitive that extracts structured data from the current page and validates it against a caller-supplied schema when provided.

#### Scenario: Extract validates schema

- **WHEN** a client calls `extract` with a JSON schema
- **THEN** the system returns data that validates against the schema
- **OR** returns a schema validation error that includes the failing field or validation reason

#### Scenario: Extract records artifacts

- **WHEN** `extract` uses perception or an LLM call
- **THEN** the system records the prompt, model usage, current URL, and any screenshot/perception artifact needed for audit

### Requirement: Hybrid agent task primitive

The system SHALL provide an `agent_task` primitive that runs an autonomous browser task through the same event, artifact, cost, memory, and guardrail surfaces used by autonomous task mode.

#### Scenario: Agent task reuses autonomous loop

- **WHEN** a client calls `agent_task` with an objective and optional start URL
- **THEN** the system runs the bounded plan-act-observe-reflect loop
- **AND** emits task plan, step, reflection, and finish events

#### Scenario: Agent task respects guardrails

- **WHEN** `agent_task` is called with allowed domains, allowed tools, confirmation settings, budgets, or browser session/profile identifiers
- **THEN** the system enforces those settings consistently with autonomous task mode
