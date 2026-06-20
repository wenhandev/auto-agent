## depends_on

- `node-context-variables` — the `{{...}}` token machinery and `variable_interpolation.resolve_params(...)` entry point this change extends with an expression form.
- `items-data-model` — expressions read `item.json`, `items`, and prior nodes' outputs through the items envelope.
- `auto-agent-mvp` — the executor's per-node interpolation step.

Soft sibling of `data-transform-nodes` (Set / Edit Fields field values are the primary place expressions are typed) and `workflow-input-parameters` (`{{= $params.x }}`). No dependency on browser-intelligence changes.

## Why

n8n's power comes from expressions: a field can be `={{ $json.price * 1.2 }}` or `={{ $items.map(i => i.json.id).join(',') }}`. auto-agent today only supports dotted-path interpolation (`{{nodes.n1.output.x}}`) — no arithmetic, no string ops, no list transforms, no conditionals. Authors cannot compute a derived value without a full `fuzzy_action` or (refused) Code node. We add a **safe, bounded expression form** that covers the 90% of n8n expressions people actually write, evaluated through an AST whitelist (no `eval`, no `exec`, no attribute access into Python internals, no imports).

## What Changes

- **New token form** `{{= <expr> }}` (leading `=` marks an expression; plain `{{nodes...}}` stays a pure path lookup). The expression is parsed with `ast.parse(expr, mode="eval")` and evaluated by a whitelisted evaluator — never Python `eval`.
- **Evaluation namespace** exposes: `nodes` (mapping of `node_id -> NodeResult` with `.output` / `.items` / `.item`), `item` (current item's `json` in loop scope, else first item), `items` (current input items' `json` list), `params` (workflow input params when `workflow-input-parameters` is present, else empty), and `now` (a timezone-aware datetime).
- **Allowed syntax**: literals (str/num/bool/None/list/dict/tuple), arithmetic (`+ - * / // % **`), comparison (`== != < <= > >= in not in`), boolean (`and or not`), conditional expression (`a if c else b`), subscript and index, attribute access ONLY on the whitelisted root objects and on a small set of safe methods, list/dict/set comprehensions (bounded), and calls ONLY to whitelisted functions.
- **Whitelisted functions / helpers**: `len, str, int, float, bool, round, abs, min, max, sum, sorted, any, all, map, filter, range, enumerate, zip`; string helpers (`upper, lower, strip, replace, split, join, startswith, endswith, format` via a `str`-method allowlist); `json_parse`, `json_stringify`; date helpers (`now()`, `parse_date`, `format_date`, `date_add`). No attribute or call outside the allowlist; dunder access is rejected at parse time.
- **Hard limits**: max expression length (default 2 KB), max AST node count (default 500), comprehension iteration cap (default 10000), and a per-expression wall-clock timeout (default 250 ms). Exceeding any limit raises `ExpressionError`, surfaced as a `node_failed`.
- **Whole-expression vs interpolated** semantics mirror `node-context-variables`: a field that is exactly one `{{= ... }}` keeps the evaluated value's type; mixed text stringifies.
- **Errors** are actionable: a failed expression reports the expression text, the Python-level error class/message (sanitised), and the names available in the namespace.
- **Editor / planner prompts**: a catalogue of the expression form, the namespace, and the allowed functions, with 2-3 examples.

## Capabilities

### New Capabilities

- `safe-expression-evaluation`: the `{{= ... }}` token form, the AST-whitelist evaluator, the evaluation namespace, the syntax/function allowlist, the hard limits, and the error contract.

### Modified Capabilities

- `node-output-interpolation` (from `node-context-variables`): the resolver recognises the `=` prefix and routes to the expression evaluator; pure-path tokens are unchanged.
- `chat-authoring` / `nl-workflow-planner`: prompts document the expression form and allowlist.

## Impact

- **Backend**: new module `app/services/expressions.py` (parser + whitelisted visitor + namespace builder + limits); `variable_interpolation.py` routes `=`-prefixed tokens to it. ~400 LOC + ~300 LOC tests (heavy on adversarial inputs: `__import__`, `().__class__`, attribute escapes, billion-laughs comprehensions, timeouts).
- **Frontend**: NodeInspector renders `{{= ... }}` fields with a monospace expression chip and a "fx" affordance; a popover evaluates the expression against the latest run's data (best-effort preview via a new `POST /api/expressions/preview`). ~200 LOC.
- **Runtime**: parsing + bounded evaluation per expression; the AST-node cap and timeout bound worst case.
- **Security**: the entire value of this change hinges on the allowlist being deny-by-default. Tests MUST cover known Python sandbox escapes (`__class__`, `__subclasses__`, `__globals__`, `__builtins__`, generator/`lambda` abuse). `lambda`, `:=`, `import`, `with`, attribute access to any dunder, and calls to non-allowlisted names are rejected at parse time.
- **Migration**: none; additive token form. Existing `{{nodes...}}` tokens unchanged.
- **Out of scope**: a full JS expression engine (we offer a Python-subset, not JS — the editor prompt documents the exact surface); user-defined functions; the Code node (still refused on security grounds); cross-expression variable assignment (each expression is pure).
