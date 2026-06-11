## depends_on

- `auto-agent-mvp` — workflow schema (`Node.params: dict`), executor walker, action set.
- `auto-agent-platform` — `services.credential_interpolation.resolve_params(params, session, *, workflow_id=None)` is the existing string-walking pass we chain into; `Run` + `RunEvent` for the latest-output introspection used by the UI.
- `per-workflow-credentials` — current `resolve_params` signature.

No dependency on other changes in this batch. This change is a sibling-ready prerequisite for `human-in-the-loop` (`{{nodes.<approval>.output.inputs.X}}`), `node-error-handling` (`{{nodes.<id>.error.message}}` in on-error branches), and `expanded-node-library` (`{{nodes.<http>.output.json.products[0].id}}` in downstream nodes).

## Why

Today every node executes in isolation. The executor records each node's output into a transient dict and emits it as a `node_completed` event, but the next node has no way to read that output. A workflow that "extract a product id, then navigate to that product page" cannot be expressed declaratively — either the URL is hardcoded, or the workflow degenerates into a single giant `fuzzy_action` node that does everything in one LLM-driven chunk.

We already have a string-walking interpolation pass for credentials (`{{cred.<name>.<field>}}`). The natural extension is a second token family that references prior nodes' outputs:

```text
{{nodes.<node_id>.output[.path.to.field]}}
```

Resolved at the same point in the executor as credentials, against a per-run `context: dict[node_id, output]` that the executor already builds.

This is the single highest-leverage change in the roadmap: it unlocks composability, it removes the need for "swiss-army `fuzzy_action`" workarounds, and it is a hard prerequisite for the approval node (which collects user inputs and must hand them to downstream nodes) and for the HTTP/parse nodes (whose entire purpose is to feed structured data into later steps).

## What Changes

- **Schema**: none. `Node.params: dict[str, Any]` already accepts strings; the new tokens ARE strings. No version bump. No DB migration.
- **Executor**: maintains a per-run `context: dict[node_id, NodeOutput]` keyed by node id, where `NodeOutput` is the canonical output dict the node returned (the same payload already emitted as `node_completed.output`). Before each node runs, its `params` are walked by a new `app/services/variable_interpolation.py::resolve_params(params, *, context, session, workflow_id)` which chains the credential pass and the nodes pass into a single tree walk.
- **Token form**: `{{nodes.<id>[.path.to.field]}}`. Whitespace tolerated inside the braces. Path uses dot notation; array indexing via `.0`, `.1`, … (no bracket syntax in v1). Resolution returns either the raw value (when the token IS the entire string) or the JSON-stringified value (when interpolated into a larger string). Missing path → `CredentialResolutionError`-style raise, surfaced as `node_failed` whose error names the failing token and lists the available top-level keys of the referenced node's output.
- **Escape**: a literal `{{` can be emitted by writing `{{ {{` (the inner `{{` is preserved verbatim). This is rarely needed for our user — the editor agent's system prompt explicitly tells it to avoid `{{` in literal strings.
- **Planner / editor prompts**: the editor agent's system prompt grows a "you can reference earlier nodes via `{{nodes.<id>.output.<path>}}`" paragraph with one example. No code change to the editor logic — it just emits the tokens as strings inside `params`. This update is documented in `chat-authoring`'s spec via a "Modified Capability" note in proposal.md.
- **UI**: the NodeInspector grows a "可用变量" tab. It lists each predecessor node (computed from the workflow graph) and the JSON shape of that node's output as captured by the most recent persisted `Run` for the workflow (if any; otherwise the tab shows "尚无运行历史"). Each leaf in the shape tree is clickable and copies the corresponding `{{nodes.<id>.output.<path>}}` token to the clipboard. Tokens already typed into any params text input render with a special highlight (a small chip) and a tooltip showing the resolved value from the latest run.

## Capabilities

### New Capabilities

- `node-output-interpolation`: the `{{nodes.<id>.output[.path]}}` token, the per-run context dict, the chained interpolation pass, the NodeInspector "可用变量" tab.

### Modified Capabilities

- `hybrid-executor` (from `auto-agent-mvp`): the executor now builds and threads a `context: dict[node_id, output]` and calls `variable_interpolation.resolve_params(node.params, context=context, session=session, workflow_id=workflow_id)` before each node, replacing the direct call to `credential_interpolation.resolve_params(...)`.
- `chat-authoring` (from `auto-agent-platform`): editor system prompt gains a paragraph and an example on `{{nodes...}}` tokens. No API change.
- `credential-vault` (from `auto-agent-platform`): the credential token pass moves behind the new chained `variable_interpolation.resolve_params(...)` entry point. Token syntax for credentials is unchanged; behaviour is unchanged. The chain order is documented: nodes first, credentials second (so a credential cannot accidentally shadow a node id and vice versa, since the two token namespaces have different prefixes).

## Impact

- **Backend**: new module `backend/app/services/variable_interpolation.py`. Executor change: holds the per-run context and calls the new entry point. Tools / actions: every node action returns a dict already (per existing executor convention); no action-level change required. Tests: new unit tests for the path resolver and the chained pass.
- **Frontend**: NodeInspector grows a new tab; chip highlight for tokens in any params text input. New API method `apiClient.workflows.getLastOutputShapes(workflowId)` returning `{ node_id: <output JSON> }` for the most recent successful `Run`. If there is no successful run, the map is empty.
- **Runtime**: extra work per node is a single recursive walk over `params` (already done for credentials). No measurable performance impact.
- **Out of scope**: complex Jinja expressions (no `{% if %}`, no filters, no arithmetic, no string concatenation operators beyond template interpolation), conditionals inside tokens, default-value fallbacks (`{{nodes.n1.output.x or "default"}}`), parallel-branch fan-in semantics ("which n1 if n1 ran twice in a foreach?" — punted to `expanded-node-library`).
