## Description

Every node's canonical result is a `NodeResult { output: dict, items: list[Item] }`, where `Item = { json: dict, binary: dict[str, BinaryRef] }`. `output` is the backward-compatible primary dict; for a single-item node it equals `items[0].json`. The executor wraps every existing action return (a `dict`) into a single-item envelope, threads a predecessor's `items` into the next node as `input_items`, stores the `NodeResult` in the per-run context, and emits a bounded `node_completed` payload. Token resolution gains `items` and `item` roots while `output` is unchanged.

## User stories

- **As a workflow author**, I want a node to emit a list of records so a downstream node can process each one, without a swiss-army `fuzzy_action`.
- **As an existing workflow**, I want to keep running unchanged: my nodes still return one dict and `{{nodes.<id>.output...}}` still resolves the same value.
- **As an operator**, I want the run log to tell me how many items a node produced and show a preview, without dumping a 1000-record array into the event stream.

## ADDED Requirements

### Requirement: Canonical NodeResult Envelope

Every node's result SHALL be a `NodeResult` with fields `output: dict` and `items: list[Item]`, where each `Item` has `json: dict` and `binary: dict[str, BinaryRef]`. For a node producing exactly one item, `output` SHALL equal `items[0].json`. For a node producing zero items, `output` SHALL be `{}`. For a node producing multiple items, `output` SHALL equal `items[0].json`.

#### Scenario: Single-item node sets output to the item json

- **WHEN** a node action returns `{"url": "https://x", "title": "X"}`
- **THEN** the `NodeResult` SHALL be `output={"url":"https://x","title":"X"}` and `items=[Item(json={"url":"https://x","title":"X"}, binary={})]`.

#### Scenario: Multi-item node output is the first item

- **WHEN** a node produces `items` whose json values are `[{"sku":"A"},{"sku":"B"}]`
- **THEN** `output` SHALL be `{"sku":"A"}`.

#### Scenario: Empty-result node has output equal to empty dict

- **WHEN** a node action returns `None` (e.g. `start`, `wait`)
- **THEN** the `NodeResult` SHALL be `output={}` and `items=[Item(json={}, binary={})]`.

### Requirement: Executor Wraps Legacy Action Returns Without Signature Change

The executor SHALL wrap every existing action's `dict` (or `None`) return into a single-item `NodeResult` via `NodeResult.single(...)`. Action function signatures in `app/tools/actions.py` SHALL NOT change. The per-run context entry for a node SHALL be its `NodeResult` (not a bare dict).

#### Scenario: Existing navigate action is wrapped

- **WHEN** the `navigate` action returns `{"url": ..., "title": ...}`
- **THEN** the executor SHALL store `context["<navigate_id>"] = NodeResult.single({"url":...,"title":...})` and SHALL NOT require any change to the `navigate` signature.

#### Scenario: Backward-compatible sample workflow

- **WHEN** the seeded `示例工作流` runs end to end
- **THEN** every node SHALL complete with the same observable `output` values as before this change AND the run SHALL complete successfully.

### Requirement: Input-Item Threading For Linear Chains

Before running a node, the executor SHALL set `input_items` to the predecessor node's `NodeResult.items`. The start node (no predecessor) SHALL receive `input_items = [Item(json={}, binary={})]`. `_run_node` SHALL accept an optional `input_items` keyword; existing actions SHALL ignore it.

#### Scenario: Start node receives one empty item

- **WHEN** the workflow begins at `start`
- **THEN** `input_items` for the start node SHALL be a list with exactly one `Item` whose `json == {}`.

#### Scenario: Downstream node receives predecessor items

- **WHEN** node `n1` produced `items` of length 3 and the edge `n1 -> n2` is followed
- **THEN** `n2` SHALL be invoked with `input_items` equal to `n1`'s 3-item list.

### Requirement: Additive Token Roots `items` And `item`, `output` Unchanged

Token resolution against `context[node_id]: NodeResult` SHALL support: `{{nodes.<id>.output[.path]}}` resolving against `NodeResult.output` (UNCHANGED from `node-context-variables`); `{{nodes.<id>.items}}` resolving to the whole `items` list; `{{nodes.<id>.item.json[.path]}}` resolving against `items[0].json`. `item` SHALL always reference index 0.

#### Scenario: output token unchanged

- **WHEN** `n1` returned `{"product_id": "P-42"}` and a later node has `"{{nodes.n1.output.product_id}}"`
- **THEN** the resolved value SHALL be `"P-42"` exactly as before this change.

#### Scenario: item.json sugar resolves first item

- **WHEN** `n1`'s `items[0].json` is `{"sku": "A"}` and a later node has `"{{nodes.n1.item.json.sku}}"`
- **THEN** the resolved value SHALL be `"A"`.

#### Scenario: items whole-token preserves the array

- **WHEN** a later node has the whole-token value `"{{nodes.n1.items}}"`
- **THEN** the resolved value SHALL be the full `items` list (with binary summarised, never the raw bytes).

### Requirement: Bounded `node_completed` Payload

The `node_completed` event payload SHALL keep `output` verbatim and SHALL add `items_count: int` and `items_preview`. `items_preview` SHALL contain the first item's `json` and a binary summary `{name: {mime, size, filename}}`. The full `items` array SHALL NOT be serialised into the event.

#### Scenario: Count and preview present

- **WHEN** a node produces 250 items
- **THEN** the `node_completed` payload SHALL include `items_count == 250` AND `items_preview.json` equal to the first item's json AND SHALL NOT include all 250 items.

### Requirement: Per-Run Item Cap

The number of items a single node may produce SHALL be capped (default 10000). Exceeding the cap SHALL raise a node failure whose message names the cap and the producing node.

#### Scenario: Cap exceeded fails the node

- **WHEN** a node attempts to emit 10001 items with the default cap of 10000
- **THEN** the node SHALL fail with an error containing `"item cap 10000 exceeded"` AND the run SHALL surface a `node_failed` event for that node.

## Out of Scope

- Fan-in concatenation across multiple predecessors (owned by `dag-executor-merge`).
- Per-item parallel browser execution (the single Chromium tab stays sequential).
- Streaming/iterator items (the array is materialised, capped).
- Loop-scoped `{{item...}}` iteration variables inside `foreach`/`while` bodies (owned by the loop nodes).
