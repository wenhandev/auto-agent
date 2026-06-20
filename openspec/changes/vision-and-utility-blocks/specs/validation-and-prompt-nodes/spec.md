## ADDED Requirements

### Requirement: Validation node

The system SHALL provide a `validation` node that evaluates a typed predicate over context variables and controls flow on failure (`fail_run`, `continue`, or an `on_error` edge).

#### Scenario: Assertion passes

- **WHEN** a `validation` node's predicate evaluates true
- **THEN** the node completes with `{passed: true}` and traversal continues normally

#### Scenario: Assertion fails with fail_run

- **WHEN** a `validation` node's predicate evaluates false and `on_error` is `fail_run`
- **THEN** a `validation_failed` event is emitted and the run fails with the reason

#### Scenario: Assertion fails with branch

- **WHEN** a `validation` node fails and an `on_error` edge exists
- **THEN** traversal follows the `on_error` edge

### Requirement: Text prompt node

The system SHALL provide a `text_prompt` node that performs a browserless LLM call and returns text or schema-validated JSON.

#### Scenario: Text generation

- **WHEN** a `text_prompt` node runs with a prompt and no schema
- **THEN** the node output is the model's text response

#### Scenario: Schema-validated output

- **WHEN** a `text_prompt` node supplies a `schema`
- **THEN** the output validates against it, with one repair retry on first failure
