## ADDED Requirements

### Requirement: Agent loop metrics summary

The system SHALL aggregate autonomous and hybrid primitive loop metrics into a run-level summary after completion or terminal failure.

#### Scenario: Successful run records metrics

- **WHEN** an autonomous or hybrid agent run finishes successfully
- **THEN** the system records round count, tool success count, tool failure count, cache hit count, cache miss count, Computer Use fallback count, no-effect count, stop reason, and usage/cost summary

#### Scenario: Failed run records metrics

- **WHEN** an autonomous or hybrid agent run fails, times out, is aborted, or stops due to no progress
- **THEN** the system records the same metrics available up to the terminal step
- **AND** records the final stop reason

### Requirement: Metrics visibility in events and APIs

The system SHALL expose loop metrics through run detail APIs and record a metrics summary event in the run timeline.

#### Scenario: Run detail includes metrics

- **WHEN** a client fetches run details for an autonomous or hybrid run
- **THEN** the response includes the loop metrics summary if one exists

#### Scenario: Timeline includes metrics summary

- **WHEN** loop metrics are finalized
- **THEN** the run timeline includes an `agent_loop_metrics` event with the summary payload

### Requirement: Metrics do not replace detailed trace

The system SHALL preserve existing detailed run events, artifacts, and LLM traces while adding aggregate metrics.

#### Scenario: Metrics coexist with step events

- **WHEN** loop metrics are written
- **THEN** existing per-step events, screenshots, LLM traces, cache events, approval events, and artifacts remain available for audit and replay
