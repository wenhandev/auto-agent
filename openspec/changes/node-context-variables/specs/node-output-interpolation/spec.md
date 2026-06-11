## Description

A node's `params` may reference any predecessor node's output via the token `{{nodes.<node_id>[.path.to.field]}}`. The executor maintains a per-run `context` dict keyed by node id and resolves these tokens immediately before invoking each action. Resolution is chained with the existing credential interpolation (`{{cred.<name>.<field>}}`) so a single tree walk handles both. Missing paths fail the node loudly with a `node_failed` event that names the failing token and the available sibling paths.

The token namespace is reserved: `nodes` for prior-node outputs (this change), `cred` for the credential vault (existing). The prefixes `run` and `trigger` are reserved for the upcoming `triggers-and-scheduling` change (`{{run.input.*}}` and `{{trigger.headers.*}}` for webhook bodies / metadata); using them in this change raises a `VariableResolutionError` with the message `"prefix '<p>' is reserved for a future change"`. Any other unrecognised prefix raises a `VariableResolutionError` whose message lists `nodes, cred` as the supported prefixes.

## User stories

- **As a workflow author**, I want a later `navigate` node to consume the `product_id` an earlier `extract` node found, without writing JavaScript or a `fuzzy_action`.
- **As a workflow author**, I want to know what shape a predecessor node returns so I can pick the right path, without running the workflow once and inspecting the log by hand.
- **As an operator**, I want a missing path to fail the run immediately with an error message that names the broken token and shows me what the predecessor actually returned, so I can fix the token in one edit.
- **As the editor LLM**, I want a single, documented token form so I can suggest it confidently in newly-generated workflows.

## Functional requirements

### Requirement: Token Form And Path Resolution

A `{{nodes.<id>[.path]}}` token SHALL resolve against the current run's `context` dict, where the dict key is the referenced node's `id` and the value is the dict that the referenced node's action returned. The path SHALL be a dot-separated sequence of segments; each segment SHALL be either a dictionary key or a list index (parsed as `int` when the surrounding value is a list, otherwise as a string key). Whitespace inside the braces SHALL be tolerated and stripped.

#### Scenario: Simple dict path

- **WHEN** node `n2` returned `{"product": {"id": "P-42", "name": "Widget"}}` and node `n5`'s params contain `{"data": "{{nodes.n2.output.product.id}}"}`
- **THEN** `n5` receives `params = {"data": "P-42"}` (the raw string value).

#### Scenario: List index

- **WHEN** node `fetch` returned `{"items": [{"sku": "A"}, {"sku": "B"}]}` and a later node has `{"first_sku": "{{nodes.fetch.output.items.0.sku}}"}`
- **THEN** the later node receives `{"first_sku": "A"}`.

#### Scenario: Whitespace tolerance

- **WHEN** the token is `"{{ nodes.n2.output.product.id }}"`
- **THEN** the resolver SHALL strip the whitespace and resolve identically to the no-whitespace form.

### Requirement: Whole-Token Returns Raw Value, Interpolated Returns String

When the entire `params` field value is exactly one token (no surrounding text), the resolved value SHALL be substituted as-is, preserving the underlying type (dict, list, int, bool, float). When the value contains a token mixed with literal text or other tokens, every token SHALL be resolved to its string form (`str(value)` for primitives, `json.dumps(value, ensure_ascii=False)` for dicts and lists) and concatenated into the surrounding string.

#### Scenario: Whole token preserves int

- **WHEN** node `count` returned `{"n": 42}` and a later node has `{"max": "{{nodes.count.output.n}}"}`
- **THEN** the resolved params SHALL be `{"max": 42}` (Python `int`, NOT string `"42"`).

#### Scenario: Whole token preserves dict

- **WHEN** node `fetch` returned `{"body": {"a": 1, "b": [2,3]}}` and a later node has `{"payload": "{{nodes.fetch.output.body}}"}`
- **THEN** the resolved params SHALL be `{"payload": {"a": 1, "b": [2,3]}}`.

#### Scenario: Interpolated produces string

- **WHEN** node `count` returned `{"n": 42}` and a later node has `{"label": "count={{nodes.count.output.n}}"}`
- **THEN** the resolved params SHALL be `{"label": "count=42"}`.

### Requirement: Chained Credential And Node Interpolation In One Pass

The executor SHALL call `variable_interpolation.resolve_params(params, *, context, session, workflow_id)` once per node, immediately before dispatching to the action. The pass SHALL handle both `{{nodes.…}}` and `{{cred.…}}` tokens in a single tree walk. The substitution SHALL be non-recursive: a resolved value that itself contains template syntax SHALL be preserved verbatim.

#### Scenario: Both token types in one string

- **WHEN** the value is `"user={{cred.bosch-login.username}}&product={{nodes.n2.output.id}}"` and both tokens resolve
- **THEN** the value SHALL become `"user=<decrypted>&product=<id>"` in a single resolution.

#### Scenario: Non-recursive substitution

- **WHEN** a credential field value literally is the string `"{{nodes.n1.output.x}}"`
- **THEN** the resolved value SHALL be the literal string `"{{nodes.n1.output.x}}"` (the inner token SHALL NOT be re-resolved).

### Requirement: Missing Path Fails The Node With An Actionable Error

If a `{{nodes.<id>[.path]}}` token cannot be resolved — because `<id>` is not in the `context` dict, or because any segment of `.path` is missing — the resolver SHALL raise `VariableResolutionError`. The executor SHALL emit a `node_failed` event whose `error` field contains the raised message verbatim. The message SHALL name the failing token, SHALL include up to 8 dot-paths into the referenced node's output that DO exist, AND SHALL include a best-effort `"did you mean '<closest>'?"` suggestion when the failing path segment is within edit-distance cutoff of a real one (computed via `difflib.get_close_matches(failed_segment, available_segments, n=1, cutoff=0.6)`).

#### Scenario: Unknown node id

- **WHEN** the token is `{{nodes.n_missing.output.x}}` and the context has only `n1`, `n2`
- **THEN** the error SHALL contain the substring `"node 'n_missing' has not run yet (available: n1, n2)"`.

#### Scenario: Missing path segment with suggestion

- **WHEN** node `n2` returned `{"product_id": 1, "product_name": "x"}` and the token is `{{nodes.n2.output.product_idd}}`
- **THEN** the error SHALL contain `"path 'output.product_idd' missing on node 'n2'"`, SHALL include `"did you mean 'output.product_id'?"`, AND SHALL list `'output.product_id'` and `'output.product_name'` among available paths.

#### Scenario: Missing path with no close match

- **WHEN** node `n2` returned `{"a": 1, "b": 2}` and the token is `{{nodes.n2.output.completely_unrelated}}`
- **THEN** the error SHALL contain `"path 'output.completely_unrelated' missing on node 'n2'"` AND SHALL list `'output.a'` and `'output.b'` among available paths AND SHALL NOT include a `"did you mean"` suggestion (no candidate above cutoff).

### Requirement: Unknown Prefix Names The Supported Prefixes; Reserved Prefixes Are Rejected

Any `{{<prefix>.…}}` token whose prefix is not `nodes` or `cred` SHALL raise `VariableResolutionError`. Two prefixes — `run` and `trigger` — SHALL be specifically reserved for a future change (the upcoming `triggers-and-scheduling` work) and SHALL raise with the message `"prefix '<p>' is reserved for a future change"`. Any other unrecognised prefix SHALL raise with `"unknown variable prefix '<p>' in '{{<token>}}'; supported prefixes: nodes, cred"`. Reservation is a parser-level no-op beyond the error message — no resolution behaviour is introduced by this change for `run` / `trigger`.

#### Scenario: Typo'd prefix

- **WHEN** the token is `{{node.n1.output.x}}` (singular `node`, not `nodes`)
- **THEN** the error SHALL contain `"unknown variable prefix 'node' in '{{node.n1.output.x}}'; supported prefixes: nodes, cred"`.

#### Scenario: Reserved `run` prefix

- **WHEN** the token is `{{run.input.x}}`
- **THEN** the error SHALL contain `"prefix 'run' is reserved for a future change"` AND SHALL NOT include the generic `"supported prefixes"` text.

#### Scenario: Reserved `trigger` prefix

- **WHEN** the token is `{{trigger.headers.x}}`
- **THEN** the error SHALL contain `"prefix 'trigger' is reserved for a future change"`.

### Requirement: Per-Run Context Built From Action Returns

The executor SHALL maintain a per-run `context: dict[str, Any]` that maps each completed node's `id` to that node's action return value. Entries SHALL be added immediately after the action coroutine returns and BEFORE the `node_completed` event is emitted, so a synchronously-following node's interpolation pass observes the new entry. Failed nodes SHALL NOT add a context entry; downstream nodes that depend on them SHALL fail per Requirement "Missing Path".

#### Scenario: Sequential nodes see each other's output

- **WHEN** node `n1` returns `{"x": 1}` and node `n2`'s params reference `{{nodes.n1.output.x}}`
- **THEN** at the time `n2`'s resolution runs, `context["n1"] == {"x": 1}` AND the resolution succeeds with value `1`.

#### Scenario: Failed node leaves no context entry

- **WHEN** node `n1` fails (action raises) and node `n2` references `{{nodes.n1.output.x}}`
- **THEN** `n2`'s resolution SHALL fail with `"node 'n1' has not run yet"` (consistent error wording; the operator is told to fix the upstream failure first).

### Requirement: Latest-Output-Shapes Endpoint For UI Auto-Completion

The backend SHALL expose `GET /api/workflows/{id}/last-output-shapes`. The endpoint SHALL find the most recent `Run` for the workflow with `status="completed"` and SHALL return a JSON map keyed by `node_id`, with values equal to the `output` payload of each node's `node_completed` event. If no successful run exists, the map SHALL be empty.

#### Scenario: No successful run

- **WHEN** the workflow has only failed and aborted runs
- **THEN** the response SHALL be `{"run_id": null, "started_at": null, "shapes": {}}`.

#### Scenario: One successful run

- **WHEN** the most recent successful run completed nodes `n1`, `n2`, `n3` with outputs `o1`, `o2`, `o3`
- **THEN** the response SHALL be `{"run_id": "...", "started_at": "...", "shapes": {"n1": o1, "n2": o2, "n3": o3}}`.

### Requirement: NodeInspector "可用变量" Tab Surfaces Predecessor Shapes

The NodeInspector SHALL render a "可用变量" tab. For the currently selected node, the tab SHALL compute the set of predecessor nodes (reverse-BFS over edges), fetch `GET /api/workflows/{id}/last-output-shapes`, and render a collapsible tree for each predecessor that has a shape entry. Each leaf SHALL be clickable; clicking SHALL copy `{{nodes.<id>.output.<dot.path>}}` to the clipboard. The tab SHALL render an empty state when no successful run is available.

#### Scenario: Tree renders predecessors

- **WHEN** the current node is `n4`, its predecessors (transitive) are `n1` and `n2`, and both have shape entries
- **THEN** the tab SHALL render two collapsible sections (`n1`, `n2`) and SHALL NOT render shape entries for non-predecessor nodes even if they exist in the shapes map.

#### Scenario: Empty state

- **WHEN** the workflow has no successful run
- **THEN** the tab SHALL render the message `"尚无运行历史，先成功跑一次以获取输出样例"` and SHALL NOT make a network request beyond the initial one.

### Requirement: Token Chip Rendering In Params Inputs

String-typed `params` inputs in the NodeInspector SHALL parse their value for `{{nodes.…}}` and `{{cred.…}}` tokens and render each as a chip. The chip SHALL show an icon identifying the token family and the dot-path tail (e.g. `nodes.n2.output.product_id`). Hovering / clicking the chip SHALL open a popover showing the resolved-from-latest-run value (or `"未知（运行后可见）"` when no shape entry exists). Deleting the chip SHALL remove the entire token from the underlying string value.

#### Scenario: Token in a navigate URL

- **WHEN** the navigate node's `url` field is `"https://shop.com/p/{{nodes.n2.output.product_id}}"`
- **THEN** the input SHALL render `"https://shop.com/p/"` followed by a chip showing `nodes.n2.output.product_id`.

#### Scenario: Chip popover shows resolved value

- **WHEN** the latest successful run's `n2.output.product_id` was `"P-42"`
- **THEN** the chip popover SHALL display `"P-42"`; otherwise `"未知（运行后可见）"`.

## API contract

| Method | Path | Request | Response | Notes |
| --- | --- | --- | --- | --- |
| `GET` | `/api/workflows/{id}/last-output-shapes` | — | `LastOutputShapesResponse` | most recent successful run; empty if none |

`LastOutputShapesResponse`:

```json
{
  "run_id": "run_…" | null,
  "started_at": "2026-…" | null,
  "shapes": {
    "n1": { ... output of n1 from last successful run ... },
    "n2": { ... }
  }
}
```

## Data model

No schema change. The per-run `context: dict[str, Any]` is in-memory only inside the executor.

The implementation surface:

```python
# backend/app/services/variable_interpolation.py
class VariableResolutionError(Exception): ...

def resolve_params(
    params: dict[str, Any],
    *,
    context: dict[str, Any],
    session: Session,
    workflow_id: Optional[str] = None,
) -> dict[str, Any]:
    """Walk params and substitute every {{nodes.…}} and {{cred.…}} token.
    Whole-token substitutions preserve type; interpolated substitutions
    produce strings. Missing paths and unknown prefixes raise
    VariableResolutionError."""
```

## Out of Scope

- Complex templating: conditionals (`{% if %}`), loops, filters, arithmetic, ternaries.
- Default-value fallbacks (`{{nodes.n1.output.x or "default"}}`). The future `node-error-handling` change provides `on_error="continue"` for structural tolerance.
- Recursive expansion of substituted values.
- Parallel-branch fan-in (`foreach`-produced lists). Resolved by `expanded-node-library`.
- Server-side cron preview of token resolution (the chip popover uses the latest run's value, never executes a preview).
- Bracket index syntax (`items[0]`). Dots only; numeric segment IS the index.
- Persisting `context` as a column. The `RunEvent` stream already carries every output payload.
