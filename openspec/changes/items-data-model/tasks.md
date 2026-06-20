## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Add `backend/app/nodes/result.py` with `BinaryRef`, `Item`, `NodeResult` (+ `NodeResult.single`). Export from a package `__init__`.
- [x] 1.2 `[shared-contract]` Add settings `inline_binary_max_bytes: int = 262144` and `max_items_per_node: int = 10000` to `backend/app/settings.py`.
- [x] 1.3 `[shared-contract]` Extend the `node_completed` event payload contract (docstring/schema) with `items_count: int` and `items_preview: dict`.
- [ ] 1.4 `[shared-contract]` Add TS mirrors to `frontend/src/types-platform.ts`: `BinaryRefSummary`, `ItemPreview`, and the extended `node_completed` payload fields.
- [ ] 1.5 `[shared-contract]` Smoke-check: `python -c "from app.nodes.result import NodeResult; print(NodeResult.single({'a':1}))"` and `cd frontend && npx tsc --noEmit`.

## 2. Executor envelope + threading (Sibling A — `[backend-runtime]`)

- [x] 2.1 In `backend/app/executor.py`, wrap every `_run_node` return via `NodeResult.single(...)` (treat `None` as `{}`); store `context[node.id] = NodeResult` instead of the bare dict.
- [x] 2.2 Thread `input_items`: compute the predecessor's `NodeResult.items` and pass to `_run_node(..., input_items=...)`. Start node gets `[Item(json={}, binary={})]`. Add the optional `input_items` keyword to `_run_node` (existing branches ignore it).
- [x] 2.3 Emit the bounded `node_completed` payload: keep `output`, add `items_count` and `items_preview` (first item json + binary summary). Never serialise the full array.
- [x] 2.4 Enforce `max_items_per_node`: if a node's `items` exceeds the cap, raise a node failure with message `"item cap <N> exceeded by node <id>"`.
- [x] 2.5 Unit tests `backend/tests/test_items_envelope.py`: single-item wrap; None→`{}`; multi-item `output==items[0].json`; start gets one empty item; downstream receives predecessor items; cap exceeded fails.

## 3. Binary model (Sibling A continued — `[backend-runtime]`)

- [x] 3.1 Implement `BinaryRef` tiering helper `app/nodes/binary.py::make_binary_ref(data: bytes, mime, filename) -> BinaryRef` honouring `inline_binary_max_bytes`; spill to `backend/data/workflow_files/_binary/` (created on first use) when large and no artifact store.
- [x] 3.2 Implement binary passthrough in threading (carry `item.binary` unchanged) and the binary summary helper `{name: {mime, size, filename}}`.
- [x] 3.3 Unit tests `backend/tests/test_item_binary.py`: inline under threshold; artifact/temp spill over threshold; passthrough preserves ref; summary omits `data_b64`.

## 4. Interpolation roots (Sibling A continued — `[backend-runtime]`)

- [x] 4.1 In `backend/app/services/variable_interpolation.py`, resolve `context[node_id]` as a `NodeResult`: `output[.path]` against `NodeResult.output` (unchanged); add `items` (whole list, binary summarised) and `item.json[.path]` (index-0 sugar) roots.
- [x] 4.2 Reject any token resolving to a `BinaryRef` with `VariableResolutionError("binary values cannot be interpolated into text; use a file node to consume binary")`.
- [x] 4.3 Unit tests in `backend/tests/test_variable_interpolation.py` (extend): `output` unchanged; `item.json.x`; whole-token `items`; binary token rejected.

## 5. Prompts (Sibling A continued — `[backend-runtime]`)

- [x] 5.1 Append a short paragraph to `backend/app/agents/editor.py` and `backend/app/agents/planner.py` system prompts: node outputs are an item array; `output` is the first item; keep using `{{nodes.<id>.output...}}` for the common single-item case.
- [x] 5.2 Substring regression test that the paragraph is present.

## 6. Frontend (Sibling B — `[frontend]`)

- [x] 6.1 RunLog / `ResultPanel` render `items_count` (e.g. a small "N 条" badge) and use `items_preview.json` when present, falling back to `output`.
- [ ] 6.2 NodeInspector "可用变量" tab also offers `item.json.*` paths (in addition to `output.*`).
- [ ] 6.3 Smoke-check: `npm run build` clean; open a run, confirm item count + preview render and existing single-item outputs look unchanged.

## 7. Verification (parent worker)

- [ ] 7.1 `[verification]` Run the seeded `示例工作流` and the Apple workflows; confirm identical `output` values and successful completion (backward compatibility).
- [ ] 7.2 `[verification]` A tiny workflow where a node emits 3 items; confirm `items_count==3`, `output` equals the first item, and a downstream `{{nodes.<id>.item.json.<k>}}` resolves the first item's field.
- [ ] 7.3 `[verification]` Attach a small binary and a >256 KB binary; confirm inline vs artifact/temp tiering and that the event preview omits the bytes.
- [ ] 7.4 `[verification]` Confirm a `{{nodes.<id>.item.binary.data}}` token fails with the binary-not-interpolable message.
- [ ] 7.5 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

### Sibling A — Backend runtime `[backend-runtime]`
**Mission.** Envelope, threading, binary model, interpolation roots, prompts (§2–§5).
**Owns.** `backend/app/nodes/result.py`, `backend/app/nodes/binary.py`, `backend/app/executor.py`, `backend/app/services/variable_interpolation.py`, `backend/app/agents/editor.py`, `backend/app/agents/planner.py`, the new backend tests.
**Must NOT touch.** `frontend/`, action signatures in `backend/app/tools/actions.py`.

### Sibling B — Frontend `[frontend]`
**Mission.** Item-count/preview rendering and inspector `item.json.*` paths (§6).
**Owns.** `frontend/src/components/RunLog.tsx`, `frontend/src/components/ResultPanel.tsx`, the inspector variables tab, TS mirrors.
**Must NOT touch.** Backend files.

**Shared contract deps (§1).** `NodeResult`/`Item`/`BinaryRef`, the extended event payload, TS mirrors.
