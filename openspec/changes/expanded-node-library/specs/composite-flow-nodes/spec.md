## Description

Three composite-flow node primitives are added: `foreach` (iterates a list and runs an inline body sub-workflow per item), `subworkflow` (invokes another persisted `Workflow` as a nested run), and an extension to the existing `condition` node so it accepts a typed predicate instead of relying on the default-true behaviour. Together they let workflows express loops, sub-routines, and richer branches without resorting to a `fuzzy_action` that does everything in one LLM call.

`foreach` exposes the current item / index through the standard `{{nodes...}}` token form. `subworkflow` reuses the run table: a child run is a normal `Run` row with `parent_run_id` set to its caller. The runs-list endpoint hides child runs by default; the run-detail endpoint exposes them as `child_runs`. The condition extension uses a small typed evaluator — no `eval`, no expression DSL — that supports a fixed set of operators on a resolved left operand.

## User stories

- **As a workflow author**, I want to loop over a parsed CSV and run my existing "check order status" workflow per row, without re-implementing the workflow inline.
- **As a workflow author**, I want a `condition` node to branch on `{{nodes.http.output.status}} >= 400` instead of always taking the default true edge.
- **As an operator**, I want child runs of a `foreach`-driven workflow to be observable but not clutter the default runs list.
- **As an operator**, I want a hard cap on `foreach` iterations so a runaway loop doesn't lock the queue for hours.
- **As an operator**, I want a workflow that calls itself recursively to fail with a clear error rather than crash the backend.

## ADDED Requirements

### Requirement: `foreach` Node

The `NodeType` literal SHALL include `"foreach"`. Params:

```python
class ForeachParams(BaseModel):
    items: Any                      # typically a token resolved to a list
    body_workflow: Workflow         # inline; one start_id, one end_id
    max_iterations: int = Field(default=1000, ge=1, le=10_000)
    parallel: bool = False          # MUST be False in v1
```

The action SHALL iterate `items` (validated to be a list at runtime; non-list raises `ValueError`). Per iteration the action SHALL:

1. Emit `foreach_iteration_started(index, item)`.
2. Build a child context dict containing the inherited parent context PLUS a synthetic entry `nodes.<foreach_id>.output = {"item": item, "index": index, "is_last": bool}` (so downstream tokens inside `body_workflow` can reference these).
3. Run `body_workflow` via a recursive call into the executor's `run_workflow`.
4. Append the body's last completed node's output to the running `results` list.
5. Emit `foreach_iteration_completed(index, output, succeeded: bool)`.
6. Check the abort flag; on abort, exit the loop cleanly and re-raise.

When the loop completes the action SHALL return:

```python
{"item_count": int, "succeeded": int, "failed": int, "results": list[Any]}
```

When `len(items) > max_iterations` the action SHALL raise `ValueError(f"foreach exceeds max_iterations: {len(items)} > {max_iterations}")` BEFORE the first iteration runs. The executor SHALL emit `node_failed` and consult the foreach node's `on_error` per `node-error-handling` rules (when installed). There SHALL be NO escape-hatch flag (`unsafe_max_iterations` or equivalent) that lets a workflow exceed the hard cap of `10_000`; workflows that genuinely need higher cardinality are out of scope for this change.

`parallel=True` SHALL raise a `ValidationError` at workflow save time in v1. Workflow validation SHALL also reject `body_workflow` containing a nested `foreach` node.

#### Scenario: Iterate over three items

- **WHEN** `items=[1,2,3]` and `body_workflow` is a single `log` node that returns `{"value": "{{nodes.<foreach_id>.output.item}}"}`
- **THEN** three `foreach_iteration_completed` events SHALL fire AND the foreach's `output.results` SHALL equal `[{"value": 1},{"value": 2},{"value": 3}]` AND `output.item_count == 3` AND `output.succeeded == 3`.

#### Scenario: Iteration cap pre-flight

- **WHEN** `items` has 1500 entries and `max_iterations = 1000`
- **THEN** the action SHALL raise BEFORE the first iteration AND no `foreach_iteration_started` event SHALL fire.

#### Scenario: Nested foreach rejected

- **WHEN** a workflow saves with a `foreach` node whose `body_workflow` contains another `foreach`
- **THEN** workflow validation SHALL fail with a message naming the nested foreach.

#### Scenario: Abort mid-iteration

- **WHEN** the abort flag is set during iteration 5 of 10
- **THEN** the loop SHALL exit cleanly AND the executor SHALL emit `run_aborted` AND `output.item_count == 10` SHALL NOT be reported (the foreach action does not complete).

### Requirement: `subworkflow` Node

The `NodeType` literal SHALL include `"subworkflow"`. Params:

```python
class SubworkflowParams(BaseModel):
    workflow_id: str
    version_id: Optional[str] = None    # default: current_version_id
    input: dict[str, Any] = Field(default_factory=dict)
```

The action SHALL:

1. Emit `subworkflow_started(child_workflow_id)`.
2. Call `services.sub_runs.run_subworkflow(parent_run_id, workflow_id, version_id, input)` which creates a `Run` row with `parent_run_id = <current run id>` and recurses into the executor.
3. The child's context SHALL include a synthetic `nodes._input.output = input` entry, accessible as `{{nodes._input.output.<key>}}` from within the child's body.
4. On child termination, emit `subworkflow_completed(child_run_id, status, final_output)`.
5. Return `{"child_run_id": str, "status": RunStatus, "final_output": Any|null}` where `RunStatus` is the full union from `auto-agent-platform` (`queued|running|completed|failed|aborted`) extended by `human-in-the-loop` (`rejected`) and `node-error-handling` (`completed_with_errors`) if those changes are also in place. In practice the child's terminal status is one of `completed | completed_with_errors | failed | aborted | rejected`.

The action SHALL enforce a recursion depth cap of 5 via a `contextvars.ContextVar` counter; the 6th nested invocation SHALL raise with a clear message ("subworkflow recursion depth exceeded (5)"). Self-recursion (`workflow_id == current workflow_id AND version_id == current_version_id`) SHALL be rejected at workflow save time as a special case of the depth cap.

#### Scenario: Parent + child run linkage

- **WHEN** workflow A has one `subworkflow(workflow_id=B)` node and runs successfully
- **THEN** the `run` table SHALL contain one row with `parent_run_id IS NULL` (A) AND one row with `parent_run_id = <A's run id>` (B).

#### Scenario: Child output accessible via context

- **WHEN** workflow B's last node returns `{"result": 42}` and workflow A has a downstream node referencing `{{nodes.<sub_id>.output.final_output.result}}`
- **THEN** the downstream resolution SHALL produce `42`.

#### Scenario: Recursion cap

- **WHEN** workflow C subworkflows itself at depth 5 and that level subworkflows again
- **THEN** the action SHALL raise "subworkflow recursion depth exceeded (5)" AND the executor SHALL emit `node_failed`.

#### Scenario: Self-recursion at same version rejected at save

- **WHEN** a workflow tries to save with a `subworkflow` node whose `workflow_id` equals itself AND `version_id` equals its current version
- **THEN** save SHALL fail with HTTP 422 naming the self-recursion.

### Requirement: Run History Distinguishes Child Runs

`Run.parent_run_id: Optional[str]` SHALL exist as a column on the `run` table, indexed, foreign-key to `run.id`. `GET /api/runs` SHALL filter `parent_run_id IS NULL` by default; the `?include_children=true` query parameter SHALL return the unfiltered list (ordered by `started_at desc`). `GET /api/runs/{id}` SHALL include `child_runs: list[RunSummary]` populated by `SELECT … FROM run WHERE parent_run_id = id`.

#### Scenario: Default list hides children

- **WHEN** the run table contains 1 parent + 5 children for the same parent
- **THEN** `GET /api/runs` SHALL return 1 row AND `GET /api/runs?include_children=true` SHALL return 6 rows.

#### Scenario: Detail surfaces children

- **WHEN** `GET /api/runs/{parent_id}` is called
- **THEN** the response SHALL include `child_runs` listing the 5 child rows with their statuses AND durations.

### Requirement: `condition` Node Typed Predicate

`ConditionParams` SHALL accept an optional `predicate: ConditionPredicate | None`:

```python
class ConditionPredicate(BaseModel):
    left: Any
    op: Literal["==","!=",">",">=","<","<=","in","not_in","is_truthy","is_falsy"]
    right: Optional[Any] = None
```

When `predicate` is set, the executor SHALL evaluate it via a typed evaluator (no `eval`, no DSL) and follow the outgoing edge whose `when` matches the evaluated bool (`"true"` / `"false"`). When `predicate` is `None`, today's behaviour applies: follow the `when="true"` edge by default. `left` is typically a `{{nodes...}}` token and is resolved by the existing interpolation pass before evaluation. `right` is required for binary ops; absent for `is_truthy` / `is_falsy`.

The condition node's output SHALL be `{"predicate": <serialised predicate>, "result": bool}`.

#### Scenario: Numeric comparison

- **WHEN** `predicate = {left:"{{nodes.http.output.status}}", op:">=", right:400}` and the HTTP node returned `status=500`
- **THEN** the condition SHALL evaluate `true` AND the executor SHALL follow the `when="true"` edge.

#### Scenario: Membership

- **WHEN** `predicate = {left:"{{nodes.http.output.status}}", op:"in", right:[200,201,204]}` and the status is `201`
- **THEN** the condition SHALL evaluate `true`.

#### Scenario: is_truthy on missing field

- **WHEN** `predicate = {left:"{{nodes.http.output.json.items}}", op:"is_truthy"}` and the JSON path is missing
- **THEN** the variable-interpolation pass SHALL raise `VariableResolutionError` BEFORE the predicate is evaluated AND the executor SHALL emit `node_failed` (consistent with the existing missing-path rule).

#### Scenario: Backwards compat with default-true

- **WHEN** a legacy condition node has no `predicate` and no `expr`
- **THEN** the executor SHALL follow the `when="true"` edge AND no schema validation error SHALL fire.

### Requirement: Four New Event Types Persisted

The event-type literal SHALL grow by four entries:

| Event type | Payload keys |
| --- | --- |
| `foreach_iteration_started` | `index: int`, `item: Any` |
| `foreach_iteration_completed` | `index: int`, `output: Any`, `succeeded: bool` |
| `subworkflow_started` | `child_workflow_id: str`, `child_version_id: str` |
| `subworkflow_completed` | `child_run_id: str`, `status: RunStatus`, `final_output: Any|null` |

All four SHALL be persisted via `services.runs.record_event(...)` exactly like existing events. Replay SHALL render them.

#### Scenario: Foreach replay timeline

- **WHEN** a past run had a foreach of 3 items
- **THEN** the replay SHALL render 3 `foreach_iteration_started` and 3 `foreach_iteration_completed` rows in order.

## API contract

`GET /api/runs?include_children: bool = false` — new query parameter.

`GET /api/runs/{id}` response SHALL include `child_runs: list[RunSummary]`.

`RunSummary` / `RunOut` SHALL include `parent_run_id: Optional[str]`.

No new endpoints; the four new event types are observed through the existing `/ws/run` socket and the existing `GET /api/runs/{id}` event-stream replay.

## Data model

```python
class Run(SQLModel, table=True):
    # ...existing...
    parent_run_id: Optional[str] = Field(default=None, foreign_key="run.id", index=True)
```

Workflow-JSON additions (inside `WorkflowVersion.workflow_json`):

```python
class ForeachParams(BaseModel):
    items: Any
    body_workflow: Workflow
    # Default 1000 iterations; hard cap 10_000 enforced by pydantic.
    # No escape-hatch flag; workflows needing higher cardinality are out of scope.
    max_iterations: int = Field(default=1000, ge=1, le=10_000)
    parallel: bool = False

class SubworkflowParams(BaseModel):
    workflow_id: str
    version_id: Optional[str] = None
    input: dict[str, Any] = Field(default_factory=dict)

class ConditionPredicate(BaseModel):
    left: Any
    op: Literal["==","!=",">",">=","<","<=","in","not_in","is_truthy","is_falsy"]
    right: Optional[Any] = None

class ConditionParams(BaseModel):
    predicate: Optional[ConditionPredicate] = None
    expr: Optional[str] = None  # legacy; ignored when predicate is set
```

Service surface:

```python
# backend/app/services/sub_runs.py
async def run_subworkflow(
    parent_run_id: str,
    workflow_id: str,
    version_id: Optional[str],
    input: dict,
) -> SubworkflowResult: ...
```

The reserved synthetic id `_input` (and any id beginning with `_`) is reserved for the platform; user workflows SHALL NOT use it. The chat editor's system prompt explicitly says so.

## Out of Scope

- Parallel iteration in `foreach` (`parallel=True`). Hard-coded false in v1.
- Nested `foreach` inside another `foreach`'s `body_workflow`. Rejected at validation; allowed inside a `subworkflow`.
- Compound predicates (`AND`, `OR`, `NOT`) in `condition`. Chain two `condition` nodes for combinators.
- Custom user-defined functions inside the predicate evaluator.
- Cross-`subworkflow` shared state. Children produce one output; talk to the parent only via the final-output return.
- `subworkflow` mid-run mutation of the parent context.
- A new `Run.status` value for subworkflow runs. Children use the same status set as top-level runs.
- Pagination on `child_runs`. If a parent has hundreds of children, the run-detail page renders them all in one nested table.
