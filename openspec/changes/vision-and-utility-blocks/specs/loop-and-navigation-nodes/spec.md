## ADDED Requirements

### Requirement: While-loop node

The system SHALL provide a `while_loop` node that repeats a one-node-deep body while a typed predicate holds, bounded by `max_iterations` with a hard ceiling.

#### Scenario: Loops while condition holds

- **WHEN** a `while_loop` predicate is true at the start of an iteration
- **THEN** the body executes and the predicate is re-evaluated for the next iteration

#### Scenario: Hard ceiling enforced

- **WHEN** a `while_loop` would exceed the hard iteration ceiling (1000)
- **THEN** the loop stops and the node completes with a `max_iterations_reached` reason

#### Scenario: Iteration events

- **WHEN** each `while_loop` iteration runs
- **THEN** `while_iteration_started` / `while_iteration_completed` events are emitted

### Requirement: Goto-URL node

The system SHALL provide a deterministic `goto_url` node that navigates directly to a URL without an LLM loop.

#### Scenario: Direct navigation

- **WHEN** a `goto_url` node runs with a URL
- **THEN** the page navigates to it via `page.goto` and the node completes with the final URL
