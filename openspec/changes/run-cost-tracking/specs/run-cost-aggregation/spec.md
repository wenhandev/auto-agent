## ADDED Requirements

### Requirement: Per-run cost aggregation

The system SHALL accumulate token counts, LLM/vision call counts, and an estimated USD cost onto each run from the cost signals it produces.

#### Scenario: Totals accumulate

- **WHEN** a run makes several LLM/vision calls
- **THEN** the run's `total_input_tokens`, `total_output_tokens`, `total_llm_calls`, and `total_vision_calls` reflect their sum

#### Scenario: Traces authoritative over hints

- **WHEN** both an `llm_trace` and a `cost_hint` exist for the same call
- **THEN** the trace's exact token counts are used and the hint is not double-counted

### Requirement: Cost estimation with editable prices

The system SHALL estimate USD cost from an editable per-model price table, leaving the estimate null for unknown models while still counting tokens.

#### Scenario: Known model priced

- **WHEN** a run uses a model present in the price table
- **THEN** `estimated_cost_usd` is computed from the token totals

#### Scenario: Unknown model

- **WHEN** a run uses a model absent from the price table
- **THEN** `estimated_cost_usd` is null with a "未知价格" indicator and token counts are still tracked

### Requirement: Nested run rollup

The system SHALL roll a subworkflow child run's cost into its parent's totals.

#### Scenario: Child cost in parent total

- **WHEN** a run invokes a subworkflow that incurs cost
- **THEN** the parent run's totals include the child's cost, and the child also shows its own

### Requirement: Per-node breakdown and cost API

The system SHALL attribute cost to the producing node and expose run totals plus a windowed spend summary via the API.

#### Scenario: Per-node breakdown

- **WHEN** the operator opens a run's cost panel
- **THEN** cost is shown per node so the most expensive node is identifiable

#### Scenario: Window summary

- **WHEN** a client requests the cost summary for a date range
- **THEN** the system returns aggregate spend over that window
