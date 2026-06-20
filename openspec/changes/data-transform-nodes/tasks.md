## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Add the nine node types (`set`, `filter`, `sort`, `limit`, `aggregate`, `split_out`, `remove_duplicates`, `rename_keys`, `datetime`) to the `NodeType` literal in `backend/app/schemas.py`.
- [x] 1.2 `[shared-contract]` Define per-type `Params` Pydantic models in `app/nodes/` modules; register them in the executor's params discriminator.
- [x] 1.3 `[shared-contract]` Define a `ctx` protocol that exposes the expression namespace builder (current `item`, `items`, `nodes`, `params`, `now`).
- [x] 1.4 `[shared-contract]` TS mirrors for the new node types + their params in `frontend/src/types-platform.ts`.
- [ ] 1.5 `[shared-contract]` Smoke-check imports + `tsc --noEmit`.

## 2. Field-mutation nodes (Sibling A — `[backend-nodes]`)

- [x] 2.1 `app/nodes/set.py` — manual assignments (literal or `{{= }}`), `keep_only_set`, `fields_to_remove`, `include_binary`.
- [x] 2.2 `app/nodes/rename_keys.py` — `{from,to}` pairs, `error_on_collision`.
- [x] 2.3 `app/nodes/datetime.py` — `now`/`parse`/`format`/`add`/`subtract`, reuse expression date helpers.
- [x] 2.4 Tests `backend/tests/test_field_mutation_nodes.py` — computed assignment; keep-only; remove; rename + collision; datetime format/add.

## 3. Item-list nodes (Sibling B — `[backend-nodes]`)

- [x] 3.1 `app/nodes/filter.py` — predicate keep; error names item index.
- [x] 3.2 `app/nodes/sort.py` — multi-key stable sort; None last.
- [x] 3.3 `app/nodes/limit.py` — first/last N.
- [x] 3.4 `app/nodes/aggregate.py` — concat/sum/avg/min/max/count/group_by; non-numeric op fails loudly; empty-input identities.
- [x] 3.5 `app/nodes/split_out.py` — explode array field; `include_other_fields`.
- [x] 3.6 `app/nodes/remove_duplicates.py` — all/selected fields, first-wins.
- [x] 3.7 Tests `backend/tests/test_item_list_nodes.py` — one per node incl. empty input, mixed-type sort, group_by, dedupe.

## 4. Executor dispatch + prompts (parent worker — `[backend-runtime]`)

- [x] 4.1 Wire the nine modules into the executor dispatch (type → `run(params, input_items, ctx)`), respecting `max_items_per_node`.
- [x] 4.2 Append catalogue entries (params + behaviour + one example each) to `editor.py` and `planner.py` prompts; emphasise expressions in `set`/`filter`.
- [x] 4.3 Substring regression test for the catalogue.

## 5. Frontend (Sibling C — `[frontend]`)

- [x] 5.1 NodeInspector per-type forms: assignment rows (`set`), predicate (`filter`), key list (`sort`/`remove_duplicates`), operation+field (`aggregate`), field+output (`split_out`/`rename_keys`/`datetime`).
- [ ] 5.2 Canvas icons per node type; RunLog shows item-count delta (e.g. `filter: 10 → 3`) using `items_count`.
- [ ] 5.3 Smoke-check: `npm run build`; build a `scrape → filter → sort → limit` chain and inspect each form.

## 6. Verification (parent worker)

- [ ] 6.1 `[verification]` End-to-end: `extract (list) → split_out → set(total) → filter(total>0) → sort(total desc) → limit(5) → aggregate(sum total)`; confirm correct final item and item-count deltas in the run log.
- [ ] 6.2 `[verification]` Empty input through each node behaves per spec (empty out / identity for aggregate).
- [ ] 6.3 `[verification]` A non-numeric `aggregate sum` fails with a clear message.
- [ ] 6.4 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

### Sibling A — Field-mutation nodes `[backend-nodes]`
**Owns.** `app/nodes/set.py`, `rename_keys.py`, `datetime.py`, their tests.
**Must NOT touch.** Item-list modules, frontend.

### Sibling B — Item-list nodes `[backend-nodes]`
**Owns.** `app/nodes/filter.py`, `sort.py`, `limit.py`, `aggregate.py`, `split_out.py`, `remove_duplicates.py`, their tests.
**Must NOT touch.** Field-mutation modules, frontend.

### Sibling C — Frontend `[frontend]`
**Owns.** Per-type inspector forms, icons, RunLog delta, TS mirrors.
**Must NOT touch.** Backend modules.

**Shared contract deps (§1).** `NodeType` literals, per-type params models, the `ctx` namespace protocol, TS mirrors. Executor dispatch + prompts (§4) land in the parent after siblings.
