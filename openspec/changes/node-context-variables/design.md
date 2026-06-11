## Context

The executor (`backend/app/executor.py`) walks the workflow graph one node at a time. For each node it calls the matching action in `app/tools/actions.py`, awaits the coroutine, and emits a `node_completed` event whose payload contains the action's return value as `output`. The output is then discarded. There is no "context dict" today — outputs are observable to the UI only via the event stream, not to subsequent nodes.

Credentials get a per-node interpolation pass (`credential_interpolation.resolve_params(params, session, workflow_id=...)`) that walks the `params` tree, finds `{{cred.<name>.<field>}}` substrings, and substitutes the decrypted value. That pass is the model for what we add here.

This change introduces a second token family — `{{nodes.<id>[.path]}}` — and a chained interpolation entry point that runs both passes against the same `params` tree before the action receives it. The schema is unchanged; this is purely a runtime/interpretation layer.

## Goals / Non-Goals

**Goals**

- A node can reference any predecessor node's output through a single, simple token form.
- Resolution happens server-side in the executor, against the exact JSON the prior node returned.
- Errors are loud and precise: a missing token names the failing path and lists the available top-level keys.
- The editor / planner LLMs can generate these tokens without learning a templating language; the syntax is one literal form.
- The UI surfaces the available variables so an operator can author by clicking, not by guessing node ids.

**Non-Goals**

- A full templating language (Jinja, Mustache, etc.). No conditionals, no loops, no arithmetic inside tokens.
- Default-value fallbacks (`{{nodes.n1.output.x or "default"}}`). If the path is missing the node fails. The future error-handling change adds `on_error="continue"` semantics that cover this case structurally.
- String concatenation between tokens beyond plain text adjacency (`"a-{{nodes.n1.output.x}}-b"` is supported; `"{{nodes.n1.output.x + nodes.n2.output.y}}"` is not).
- Parallel-branch fan-in / array building from N parallel runs of the same node. Resolved by `expanded-node-library`'s `foreach` semantics.
- Backwards-compatibility shim for already-shipped workflows that contain `{{nodes.…}}` as literal text. No such workflows exist today; any literal `{{` users may have typed is rare enough to warrant the breaking interpretation.
- Persisting the per-run `context` as a separate column. The `RunEvent` stream already carries every node output; reconstructing the context from events on demand is cheap and avoids a second source of truth.

## Decisions

### Decision 1: One chained entry point in `variable_interpolation.py`, not two separate passes called in order

Two separate passes in the executor (`credential_interpolation.resolve_params(...)` then `variable_interpolation.resolve_nodes(...)`) would each walk the same tree twice and would have to agree on subtle edge cases like "what if a credential value contains `{{nodes...}}` text?". We pick a single chained entry point:

```python
# backend/app/services/variable_interpolation.py
def resolve_params(
    params: dict[str, Any],
    *,
    context: dict[str, Any],
    session: Session,
    workflow_id: Optional[str] = None,
) -> dict[str, Any]:
    """Walk params (strings, lists, nested dicts) and substitute:
       - {{nodes.<id>[.path]}}  against context
       - {{cred.<name>.<field>}} against the credential vault
       Both passes happen in a single walk; tokens are resolved
       atomically (no recursion: substituted values are NOT re-scanned)."""
```

`credential_interpolation.py` is kept as the implementation detail for the credential pass; `variable_interpolation.py` is the only caller from the executor going forward. The non-recursive substitution rule is explicit: a credential value of `{{nodes.n1.output.x}}` is preserved verbatim. This eliminates a class of cyclic-template surprises and matches how `os.path.expandvars` behaves.

### Decision 2: Path syntax — dot notation, array index as `.<int>`, no brackets

```text
{{nodes.n2.output.product.id}}
{{nodes.fetch_products.output.items.0.sku}}
{{nodes.search.output.results.3.title}}
```

We considered bracket notation (`items[0]`, `results['title']`) and rejected it. Reasons:

- Brackets force a small parser; dots fit `str.split('.')`.
- The editor LLM produces simpler tokens with dots (single tokeniser pass).
- No real workflow we've seen needs string keys with characters that aren't `[A-Za-z0-9_]`.

Numeric segments are interpreted as list indices when the surrounding value is a list; otherwise as a string key. So `{{nodes.n.output.items.0}}` works on `output = {"items":["a","b"]}` (returns `"a"`) and ALSO works on `output = {"items":{"0":"a","1":"b"}}` (returns `"a"`). Ambiguity is resolved by the runtime type — never the path syntax.

### Decision 3: Whole-token vs interpolated semantics

```text
params = {
  "url": "https://shop.com/p/{{nodes.n2.output.product_id}}",   # interpolated → string
  "data": "{{nodes.n2.output.product}}",                         # whole token → raw value (dict)
  "count": "{{nodes.n2.output.count}}",                          # whole token → raw value (int)
}
```

Rules:

- If the `params` value is exactly one token and nothing else, the resolved Python object (dict, list, int, bool, etc.) is substituted as-is and the field's type changes accordingly.
- If the value contains a token mixed with literal text, every token is resolved to its `str(value)` representation (for primitives) or `json.dumps(value)` (for dicts/lists) and concatenated into the surrounding string.
- This rule is symmetric with how the credential pass works on string fields today, but extends it to arbitrary value types.

### Decision 4: Missing path is a hard `node_failed` with closest-valid-path suggestion

```text
{{nodes.n2.output.does_not_exist}}
→ VariableResolutionError(
    "path 'output.does_not_exist' missing on node 'n2'; "
    "did you mean 'output.product_id'? available paths: "
    "['output.product_id', 'output.product_name', 'output.price']"
  )
```

The error message lists up to 8 dot-paths into the referenced node's output AND surfaces a best-effort "did you mean" suggestion (computed via `difflib.get_close_matches(failed_segment, available_segments, n=1, cutoff=0.6)`) to make the fix obvious. We considered `null`-on-missing semantics with a warning event but rejected: silent `null` produces downstream errors that are harder to diagnose ("why did the navigate node hit `https://shop.com/p/null`?"). The future `node-error-handling` change provides `on_error="continue"` as the structured way to tolerate missing data.

### Decision 5: Context is built incrementally from action returns, NOT reconstructed from events

The executor already receives each action's return value before emitting `node_completed`. We add a single line: `context[node_id] = output`. The `RunEvent` stream remains a side-effect for the UI; the executor's source of truth is the local dict.

For replay (driving the UI from stored events) the frontend already has the full event sequence. If a future change wants to replay with full interpolation tracing (e.g. "show what THIS token resolved to at this step"), the replay engine can reconstruct `context` from the persisted `node_completed.output` payloads. Out of scope for this change.

### Decision 6: NodeInspector's "可用变量" tab uses the latest successful `Run` of THIS workflow

We considered four candidate sources for the "what shape does node X return?" answer:

1. Statically-inferred shape from the node `type` + `params`. Rejected — too many node types return free-form dicts (`extract`, `fuzzy_action`, `http_request`).
2. The most recent `Run` for this workflow, regardless of status. Rejected — failed runs leave most nodes' outputs as `null`.
3. The most recent **successful** `Run` for this workflow. **Chosen.** The "last green build" idiom.
4. A union of all observed shapes across all historical runs. Rejected — needlessly expensive and confusing when shapes change across edits.

If no successful `Run` exists for the current workflow version (or any version), the tab shows `"尚无运行历史，先成功跑一次以获取输出样例"`. Tokens can still be typed by hand; they just don't get auto-completion.

```mermaid
sequenceDiagram
    participant FE as NodeInspector
    participant API as GET /api/workflows/{id}/last-output-shapes
    participant DB as SQLite
    FE->>API: fetch on inspector open
    API->>DB: SELECT * FROM run WHERE workflow_id=? AND status='completed' ORDER BY started_at DESC LIMIT 1
    alt no successful run
        API-->>FE: { runs: null, shapes: {} }
    else has successful run
        API->>DB: SELECT node_id, payload_json FROM runevent WHERE run_id=? AND event_type='node_completed'
        DB-->>API: rows
        API-->>FE: { run_id, started_at, shapes: { node_id: <output json> } }
    end
    FE->>FE: render variable tree per predecessor; copy-on-click
```

### Decision 7: Chip rendering for tokens in inputs

Any `<input>` / `<textarea>` inside the NodeInspector that holds a `params` value SHALL parse its value for `{{nodes.…}}` and `{{cred.…}}` tokens and render each as a non-editable chip with a small icon. Clicking a chip opens a popover showing the resolved value from the latest run (if available). Deleting the chip removes the entire token from the string. We use `contenteditable` for this rather than a custom editor because it preserves accessibility and copy-paste behaviour.

### Decision 8: Editor agent prompt update is doc-only

The editor agent's system prompt is a string in `backend/app/agents/editor.py`. This change adds one paragraph and one example. There is no API change. The editor's `EditorResponse` schema and the patch op set from `chat-authoring` are unchanged.

## Risks / Trade-offs

- **`{{` as literal text**: writing `{{` verbatim is now context-dependent. We document the escape `{{ {{` and the editor's system prompt tells the model to avoid `{{` in literal strings. Acceptable trade-off given how rarely `{{` appears in real workflow params.
- **Output shape drift**: if the operator edits an `extract` node's `query`, the next run's output shape may change. The "可用变量" tab is best-effort and may surface a stale shape. We document this and the chip-popover's resolved value is always computed against the latest run, never cached longer than that.
- **Large outputs**: a `fuzzy_action` node may return a multi-KB dict. The chip popover renders the path's resolved value; the full dict is shown via "show full output" in the inspector. Network cost is one fetch per inspector open.
- **Token namespace collision**: `nodes.cred` would NOT collide because `nodes` and `cred` are distinct top-level prefixes. We reserve `run` AND `trigger` as future-only prefixes (see Decision 11 below); any token starting with `{{run.…}}` or `{{trigger.…}}` raises `VariableResolutionError` with the message `"prefix 'run' is reserved for a future change"` (or `'trigger'`), so workflows authored today cannot accidentally claim shapes that the upcoming `triggers-and-scheduling` change will define.
- **Recursive expansion**: explicitly rejected. A credential value of `{{nodes.n1.output.x}}` is preserved verbatim. Same rule for a node output that happens to contain `{{cred.…}}`. This prevents cyclic templates and matches how environment variable expansion works in shells.

## Migration Plan

- No schema change, no DB migration.
- Existing workflows continue to run unchanged: their `params` contain no `{{nodes...}}` tokens, so the new pass is a no-op for them.
- The editor agent's system prompt update is a deploy-time change (Python source edit) that takes effect on the next backend restart.
- Frontend chip rendering is opt-in based on token detection; inputs that don't contain tokens render as plain text.

### Decision 11: Reserve `run` AND `trigger` prefixes now

To prevent workflows authored today from accidentally colliding with the shape the upcoming `triggers-and-scheduling` change will introduce (`{{run.input.*}}`, `{{trigger.headers.*}}`, etc.), the interpolator SHALL reject any token whose prefix is `run` or `trigger` with `VariableResolutionError(f"prefix '<p>' is reserved for a future change")`. The unknown-prefix error message lists `nodes, cred` as the currently-supported prefixes; the `run` and `trigger` prefixes get the more specific "reserved for a future change" message so the operator understands the difference between "typo" and "not yet implemented".

This is a no-behaviour change beyond the error message; resolved values for `run` / `trigger` are introduced by `triggers-and-scheduling` without re-touching the interpolator.

## Resolved Decisions

The two original open questions were closed by the user before implementation:

1. **Missing-path behaviour** → **hard `node_failed`** with a closest-valid-path suggestion in the error message (see Decision 4). Silent `null` was rejected because it tends to mask real bugs in downstream nodes; `node-error-handling`'s `on_error="continue"` is the structured way to tolerate missing data.
2. **Reserve `run` / `trigger` prefixes now** → **yes** (see Decision 11). Parser-level reservation only; no behaviour beyond a "reserved for a future change" error.

## Open Questions

All design decisions resolved as of 2026-05-15.
