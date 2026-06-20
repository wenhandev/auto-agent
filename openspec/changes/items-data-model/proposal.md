## depends_on

- `auto-agent-mvp` — workflow schema (`Node`, `Edge`), executor walker, the per-node action-return convention (a `dict`).
- `auto-agent-platform` — `RunEvent` stream, `node_completed.output` payload, the executor's `emit` callback.
- `node-context-variables` — the `{{nodes.<id>.output[.path]}}` token and the per-run `context` dict this change generalises. Hard dependency: the envelope changes what `context[node_id]` holds.

This change is the data-model foundation for `dag-executor-merge` (Merge concatenates item arrays), `data-transform-nodes` (Set / Item Lists operate over items), and the n8n-style nodes generally. It does not depend on any browser-intelligence change.

## Why

n8n's defining trait is that every node consumes and emits an **array of items** (`{json, binary}`), so a single node can fan a list of records through the graph and downstream nodes process each record uniformly. Today every auto-agent node returns exactly one `dict` and the next node has no notion of "a list of things to process" — the only way to loop is a swiss-army `fuzzy_action`. Without an items model, Merge, Set/Edit Fields, Item Lists, Aggregate, and Split Out cannot exist, and binary payloads (downloaded files, screenshots, PDFs) have nowhere to live in the data flow.

We introduce an **items envelope** that is fully backward compatible: existing nodes keep returning a `dict`, the executor wraps it as a single item, and the existing `{{nodes.<id>.output...}}` token keeps working unchanged. New data nodes (shipped in later changes) opt into the array semantics.

## What Changes

- **Canonical node result becomes a `NodeResult`**: `{ output: dict, items: list[Item] }` where `Item = { json: dict, binary: dict[str, BinaryRef] }`. `output` is preserved as the legacy primary dict (equal to `items[0].json` when there is exactly one item), so nothing downstream that reads `output` breaks.
- **Executor wraps every existing action return** `r: dict` into `NodeResult(output=r, items=[Item(json=r, binary={})])`. Action signatures are unchanged.
- **Input-item threading**: the executor passes the predecessor node's `items` to the current node as `input_items`. In a linear chain this is the single predecessor's items; fan-in semantics (concatenating multiple predecessors) are defined by `dag-executor-merge` and only stubbed here (single-predecessor threading). A node that does not consume `input_items` ignores them.
- **Binary data**: `BinaryRef = { kind: "inline" | "artifact", mime: str, filename: str | null, data_b64?: str, artifact_id?: str, size: int }`. Small payloads are inline (base64, capped); larger payloads reference the artifact store when `run-artifacts-observability` is present, else a sandboxed temp file. Binary is never interpolated into string params.
- **`node_completed` event extension**: the payload keeps `output` (unchanged) and gains `items_count: int` plus an `items_preview` (first item's `json`, binary summarised as `{name: {mime, size}}`). The full items array is reconstructable from `output`/artifacts; the event is not bloated with large binaries.
- **Token extensions** (additive to `node-context-variables`): `{{nodes.<id>.items}}` (whole array), `{{nodes.<id>.item.json[.path]}}` (sugar for `items.0.json...`). `{{nodes.<id>.output[.path]}}` is unchanged.
- **Editor / planner prompts**: a short paragraph documents that node outputs are an item array and that `output` is the first item, so authored tokens keep using `output` for the common single-item case.

## Capabilities

### New Capabilities

- `items-envelope`: the `NodeResult` / `Item` shape, the backward-compatible `output` alias, the executor wrapping of legacy returns, input-item threading for linear chains, the `node_completed` event extension, and the additive `{{nodes.<id>.items}}` / `{{nodes.<id>.item...}}` tokens.
- `item-binary-data`: the `BinaryRef` model, inline-vs-artifact thresholds, binary passthrough between nodes, and the rule that binary is never string-interpolated.

### Modified Capabilities

- `hybrid-executor` (from `auto-agent-mvp`): the executor threads `input_items` and stores a `NodeResult` per node id in the per-run context instead of a bare dict.
- `node-output-interpolation` (from `node-context-variables`): `context[node_id]` now holds a `NodeResult`; `output` resolves against `NodeResult.output` (unchanged behaviour); new `items` / `item` token roots are added.
- `run-history` (from `auto-agent-platform`): `node_completed` payload gains `items_count` and `items_preview`.
- `chat-authoring` / `nl-workflow-planner`: prompts note the item-array model.

## Impact

- **Backend**: new module `app/nodes/result.py` (`NodeResult`, `Item`, `BinaryRef`); executor wraps returns and threads `input_items`; `variable_interpolation.py` learns the `items` / `item` roots and keeps `output` resolving against `NodeResult.output`. ~300 LOC + ~200 LOC tests. No DB migration (the envelope is in-memory + event payload only).
- **Frontend**: RunLog / ResultPanel render `items_count` and the items preview; NodeInspector "可用变量" tab can show `item.json.*` paths. ~150 LOC.
- **Runtime**: wrapping is O(1) per node; inline-binary cap (default 256 KB) prevents event/DB bloat.
- **Migration**: none. Existing workflows and the seeded sample run unchanged because every legacy return becomes a single-item envelope and `output` is preserved.
- **Out of scope**: real fan-in concatenation (Merge) — `dag-executor-merge`; per-item parallel browser execution (the single Chromium tab stays sequential) — only the data shape is array-valued, not the browser session; streaming/iterator items (the array is materialised in memory, capped) — a future change if needed; binary stores beyond local disk / artifact store (no S3) — consistent with `run-artifacts-observability`.
