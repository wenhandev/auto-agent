## depends_on

- `auto-agent-platform` — `Run` / `RunEvent`, `services.runs`, run-list/detail UI.
- `self-healing-selectors` / `vision-action-mode` — the per-event `cost_hint` (`input_tokens`, `output_tokens`, `vision_calls`) these changes already emit but never aggregate.

Soft synergy with `run-artifacts-observability` (LLM traces carry exact token counts to aggregate).

## Why

`auto-agent` emits a per-event `cost_hint` and then drops it on the floor — there is no surface that answers "how much did this run cost?". `REFERENCES.md` Cross-cutting theme #3 ("Cost surface is the gap") names this as the most-asked-for feature once `vision-action-mode`, `foreach`, and `subworkflow` multiply LLM call counts. Skyvern surfaces `total_cost` per run. This change aggregates the cost signal we already produce into per-run totals and renders them.

## What Changes

- **Aggregation**: `services.runs` accumulates each emitted/persisted `cost_hint` into running totals on the `Run`: `total_input_tokens`, `total_output_tokens`, `total_vision_calls`, `total_llm_calls`, and a derived `estimated_cost_usd` (computed from a per-model price table; null when the model price is unknown). When `run-artifacts-observability` is present, the exact token counts from `llm_trace` artifacts are the source of truth; otherwise the per-event `cost_hint` is used.
- **Price table**: a small, editable `model_prices` config (`{model: {input_per_1k, output_per_1k}}`) seeded with common models and overridable in Settings. Unknown models contribute token/call counts but `estimated_cost_usd` stays null with a "未知价格" note.
- **Per-node breakdown**: the run-detail timeline shows per-node token/cost so the operator can see which node is expensive (a `foreach` body, a long `vision_navigate`).
- **API**: `RunOut` / `RunSummary` expose the totals; `GET /api/runs` supports sorting by cost; an optional `GET /api/runs/cost-summary?from=&to=` returns aggregate spend over a window.
- **UI**: run-list shows a cost column; run-detail shows a cost panel (totals + per-node breakdown); Settings has a "模型价格" editor; an optional dashboard tile "近 7 天用量".

## Capabilities

### New Capabilities

- `run-cost-aggregation`: the per-run token/call/cost totals, the per-model price table + estimation, the per-node breakdown, the cost API (totals, sort, window summary), and the cost UI surfaces.

### Modified Capabilities

- `run-history` (from `auto-agent-platform`): `Run` gains the cost columns; `RunOut`/`RunSummary` expose them; run-list/detail render cost.
- `runtime-llm-config` (from `auto-agent-platform`): the `model_prices` table is configured alongside LLM settings.
- `self-healing-selectors` / `vision-action-mode`: their `cost_hint` payloads are now consumed (no change to the emitted shape).

## Impact

- **Backend**: aggregation in `services.runs` (~60 LOC), cost columns on `Run` (additive), a `model_prices` config + estimator, two API additions. Tests: aggregation correctness across nested `subworkflow`/`foreach` runs, unknown-model null cost, window summary.
- **Frontend**: run-list cost column, run-detail cost panel + per-node breakdown, Settings price editor, optional dashboard tile. ~250 LOC.
- **Runtime**: aggregation is arithmetic on signals already produced; negligible cost.
- **Migration**: additive `Run` columns (default 0/null); existing runs show counts of 0 and "无成本数据（早于成本功能）". New `model_prices` config seeded on first boot.
- **Out of scope**: hard budget enforcement / run cutoffs at a cost cap (a future `cost-budgets` change can gate runs once this surface exists); billing/invoicing; multi-currency; cost attribution per API key / per user (waits for `multi-user-orgs`).
