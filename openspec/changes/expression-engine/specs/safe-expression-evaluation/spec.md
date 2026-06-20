## Description

A `{{= <expr> }}` token evaluates a bounded, whitelisted expression against a fixed namespace (`nodes`, `item`, `items`, `params`, `now`) and a curated function/method allowlist. Expressions are parsed via `ast.parse(mode="eval")` and interpreted over a node-type allowlist — never via Python `eval`/`exec`. Attribute access is deny-by-default with a hard dunder ban; calls reach only allowlisted callables. Length, AST-size, iteration, and wall-clock limits bound every evaluation. Whole-expression fields preserve the evaluated type; mixed text stringifies.

## User stories

- **As a workflow author**, I want `{{= nodes.n1.output.price * 1.2 }}` to compute a derived value without a Code node.
- **As a workflow author**, I want `{{= [i.json.sku for i in items if i.json.in_stock] }}` to reshape a list.
- **As a security owner**, I want any attempt to reach Python internals (`__class__`, `__import__`, `open`) to be rejected at parse time, not merely fail at runtime.
- **As an operator**, I want a broken expression to fail the node with a message that shows the expression and the available names.

## ADDED Requirements

### Requirement: Expression Token Form And Routing

A `{{= <expr> }}` token (optional whitespace around `=`) SHALL be evaluated as an expression. A `{{ ... }}` token WITHOUT a leading `=` SHALL continue to be resolved as a path lookup per `node-context-variables` / `items-data-model`, with no behaviour change.

#### Scenario: Expression token is evaluated

- **WHEN** a field value is `"{{= 2 + 3 }}"`
- **THEN** the resolved value SHALL be the integer `5`.

#### Scenario: Non-expression token still a path lookup

- **WHEN** a field value is `"{{nodes.n1.output.x}}"` and `n1.output.x == 7`
- **THEN** the resolved value SHALL be `7` via the existing path resolver, NOT the expression evaluator.

### Requirement: Whitelisted Namespace

The evaluation namespace SHALL expose exactly: `nodes` (mapping `node_id -> NodeResult` with `.output`/`.items`/`.item`), `item` (the current item's `json`; first item outside loop scope), `items` (list of current input items' `json`), `params` (workflow input params or `{}`), and `now` (a timezone-aware datetime). No other names SHALL be resolvable.

#### Scenario: Item field arithmetic

- **WHEN** the current `item.json` is `{"qty": 3, "price": 10}` and the field is `"{{= item.json.qty * item.json.price }}"`
- **THEN** the value SHALL be `30`.

#### Scenario: Unknown name rejected

- **WHEN** the expression is `"{{= secrets.key }}"`
- **THEN** evaluation SHALL raise `ExpressionError` AND the message SHALL list `nodes, item, items, params, now` as the available names.

### Requirement: Syntax Allowlist Enforced At Parse Time

The evaluator SHALL accept only: literals, arithmetic (`+ - * / // % **`), comparison (`== != < <= > >= in not in`), boolean (`and or not`), conditional expression (`a if c else b`), subscript/slice, attribute access (subject to the attribute allowlist), comprehensions, and calls (subject to the call allowlist). `lambda`, assignment, walrus (`:=`), `import`, and any statement form SHALL be rejected during the whitelist pass.

#### Scenario: Lambda rejected

- **WHEN** the expression is `"{{= (lambda: 1)() }}"`
- **THEN** the whitelist pass SHALL raise `ExpressionError` before any evaluation.

#### Scenario: Conditional expression allowed

- **WHEN** the expression is `"{{= 'yes' if item.json.ok else 'no' }}"` and `item.json.ok` is truthy
- **THEN** the value SHALL be `"yes"`.

### Requirement: Attribute Access Is Deny-By-Default With Dunder Ban

Attribute access SHALL be permitted only on whitelisted types/roots and only for allowlisted attribute names. Any attribute whose name begins or ends with an underscore SHALL be rejected.

#### Scenario: Dunder access rejected

- **WHEN** the expression is `"{{= ''.__class__ }}"`
- **THEN** evaluation SHALL raise `ExpressionError` (dunder access banned) and SHALL NOT return any class object.

#### Scenario: Sandbox-escape chain rejected

- **WHEN** the expression is `"{{= ().__class__.__bases__[0].__subclasses__() }}"`
- **THEN** evaluation SHALL raise `ExpressionError` at the first dunder access.

#### Scenario: Allowlisted string method works

- **WHEN** the expression is `"{{= item.json.name.upper() }}"` and `item.json.name == 'abc'`
- **THEN** the value SHALL be `"ABC"`.

### Requirement: Calls Reach Only Allowlisted Callables

A call SHALL be permitted only when the callee resolves to a member of the function allowlist or a per-type allowlisted method. Calling any non-allowlisted name SHALL raise `ExpressionError`.

#### Scenario: Allowed builtin

- **WHEN** the expression is `"{{= len(items) }}"` and there are 4 items
- **THEN** the value SHALL be `4`.

#### Scenario: Dangerous builtin unavailable

- **WHEN** the expression is `"{{= open('/etc/passwd') }}"`
- **THEN** evaluation SHALL raise `ExpressionError("function 'open' is not available")`.

### Requirement: Resource Limits

Evaluation SHALL enforce: source length `<= EXPR_MAX_LEN` (default 2048 bytes), AST node count `<= EXPR_MAX_NODES` (default 500), total comprehension/range/map/filter elements `<= EXPR_MAX_ITER` (default 10000), and wall-clock `<= EXPR_TIMEOUT_MS` (default 250 ms). Breaching any limit SHALL raise `ExpressionError` naming the limit.

#### Scenario: Iteration cap

- **WHEN** the expression is `"{{= [x for x in range(100000)] }}"` with the default cap of 10000
- **THEN** evaluation SHALL raise `ExpressionError` whose message names the iteration cap.

#### Scenario: Oversized source

- **WHEN** the expression source exceeds `EXPR_MAX_LEN`
- **THEN** evaluation SHALL raise `ExpressionError` before parsing.

### Requirement: Whole-Expression Type Preservation And Error Contract

A field equal to exactly one `{{= ... }}` SHALL return the evaluated value with its native type. A field mixing an expression with literal text SHALL stringify the result (`str` for primitives, JSON for dict/list). A failed expression SHALL raise `ExpressionError` whose message includes the (truncated) expression text and the available names, surfaced by the executor as `node_failed`.

#### Scenario: Whole expression preserves list type

- **WHEN** the field is `"{{= [1, 2, 3] }}"`
- **THEN** the resolved value SHALL be the list `[1, 2, 3]` (not the string `"[1, 2, 3]"`).

#### Scenario: Interpolated expression stringifies

- **WHEN** the field is `"total: {{= 2 + 3 }}"`
- **THEN** the resolved value SHALL be the string `"total: 5"`.

### Requirement: Expression Preview Endpoint

The backend SHALL expose `POST /api/expressions/preview` accepting `{workflow_id, node_id, expression}` and returning `{ok: bool, type: str|null, value_preview: str|null, error: str|null}`. The preview SHALL use the SAME evaluator and limits as runtime, evaluated against the latest successful run's predecessor outputs. When no run data exists it SHALL return `{ok: false, error: "no run data", value_preview: null}`.

#### Scenario: Preview with run data

- **WHEN** the latest successful run has `n1.output.price == 10` and the previewed expression is `nodes.n1.output.price * 2`
- **THEN** the response SHALL be `{ok: true, type: "int", value_preview: "20", error: null}`.

#### Scenario: Preview without run data

- **WHEN** the workflow has no successful run and an expression is previewed
- **THEN** the response SHALL be `{ok: false, error: "no run data", value_preview: null}`.

## Out of Scope

- A JavaScript engine (we expose a documented Python-subset).
- User-defined functions, lambdas, statements, assignment, imports.
- The Code node (refused on security grounds).
- Cross-expression shared state.
