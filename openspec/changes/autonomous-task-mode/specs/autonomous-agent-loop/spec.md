## Description

A graph-free `autonomous` run mode: given an objective (and optional start URL, budgets, success criteria, data schema), the agent runs a bounded plan-act-observe-reflect loop over the vision tools and a curated set of deterministic nodes-as-tools, maintaining compacted working memory, until it finishes, exhausts a budget, or trips a guardrail. The result is schema-validated data or a free-form summary plus collected items.

## User stories

- **As a user**, I want to give a URL and a goal ("find the cheapest flight NYC→SFO next Friday and extract the price") and have the agent accomplish it without me authoring a graph.
- **As a user**, I want a structured result matching my schema when I provide one.
- **As an operator**, I want to watch the agent's plan, steps, and reflections live and abort if it goes wrong.

## ADDED Requirements

### Requirement: Autonomous Run Mode Entry Point

The backend SHALL expose `POST /api/tasks` accepting `{objective, start_url?, max_steps?, max_seconds?, success_criteria?, allowed_domains?, data_schema?, require_confirmation?, allowed_tools?}` and start an `autonomous`-mode run. `max_steps` and `max_seconds` SHALL have enforced defaults when omitted (budgets are mandatory).

#### Scenario: Task starts with mandatory budgets

- **WHEN** a task is created without `max_steps`/`max_seconds`
- **THEN** the run SHALL start with the default budgets applied AND the run record SHALL have `mode == "autonomous"`.

### Requirement: Plan-Act-Observe-Reflect Loop

Each loop cycle SHALL build an observation (perception + compacted memory + current plan), obtain exactly one next action from the LLM (a tool call or `finish`), execute it, record the result in memory, and periodically reflect/re-plan. The loop SHALL terminate on `finish`, budget exhaustion, a guardrail trip, or an unrecoverable error.

#### Scenario: Finish terminates the loop

- **WHEN** the agent calls `finish(success=true, result=...)`
- **THEN** the loop SHALL stop and return the result without consuming further steps.

#### Scenario: Step budget terminates the loop

- **WHEN** the agent reaches `max_steps` without finishing
- **THEN** the loop SHALL stop and return a budget-exhausted result that includes the work done so far.

### Requirement: Working Memory With Compaction

The agent SHALL maintain structured memory (objective, evolving plan, recent observations, extracted data items, visited URLs). When serialized memory would exceed the context budget, older narrative steps SHALL be compacted into a summary; extracted data items SHALL be preserved verbatim and SHALL NOT be summarized away.

#### Scenario: Data items survive compaction

- **WHEN** memory is compacted after many steps
- **THEN** every previously `extract`ed data item SHALL still be present verbatim in the result/memory.

### Requirement: Superset Tool Surface

The agent's callable tools SHALL include the `vision-action-mode` tools and a curated set of deterministic nodes-as-tools (`http_request`, `extract`, data-transform ops, `integration`), restricted to `allowed_tools` when provided (default: read-only browser + extract + http). A node-as-tool SHALL execute via the same node executor used in graphs.

#### Scenario: Restricted tool set enforced

- **WHEN** `allowed_tools` excludes `integration`
- **THEN** the agent SHALL NOT be offered or able to invoke an `integration` tool call.

### Requirement: Result Contract

When `data_schema` is provided, `finish` SHALL return data validated against it; a validation failure SHALL trigger one corrective retry then fail the task with the validation error. Without a schema, the result SHALL be `{success, summary, items}` where `items` are everything extracted during the run.

#### Scenario: Schema-validated finish

- **WHEN** `data_schema` requires `{price: number}` and the agent finishes with `{price: 199}`
- **THEN** the task result SHALL be the validated object.

#### Scenario: Invalid finish retries then fails

- **WHEN** the agent finishes with data failing `data_schema` twice
- **THEN** the task SHALL fail with the schema validation error.

### Requirement: Task Events

The run SHALL emit `task_plan_updated`, `task_reflection`, and `task_finished` (with `success`, `result`, optional `synthesized_workflow_id`) in addition to the reused `vision_step` events.

#### Scenario: Plan updates are observable

- **WHEN** the agent re-plans after a reflection
- **THEN** a `task_plan_updated` event SHALL be emitted carrying the new plan.

## Out of Scope

- Multi-agent / sub-agent orchestration.
- Cross-task learning / persistent skills.
- Unbounded (budget-free) runs.
