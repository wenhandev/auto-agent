## Context

`self-healing-selectors` and `vision-action-mode` emit `cost_hint` per event; `run-artifacts-observability` records exact token counts in `llm_trace` artifacts. The data exists; there is no aggregation or display. This change is deliberately small (S effort): accumulate, estimate, render.

## Goals / Non-Goals

**Goals:**
- Per-run token/call totals + an estimated USD cost.
- Per-node breakdown so the expensive step is obvious.
- A windowed spend summary.

**Non-Goals:**
- Budget enforcement / run cutoffs (future `cost-budgets`).
- Billing.
- Per-user attribution (waits for `multi-user-orgs`).

## Decisions

### Decision 1: Aggregate on the `Run`, source-of-truth = traces when present
Totals live on the `Run` row, updated as events/traces arrive. When `run-artifacts-observability` traces exist, their exact token counts win over `cost_hint` estimates.
- **Why**: one durable place to read totals; traces are authoritative when available.

### Decision 2: Estimation via an editable price table, null on unknown
`estimated_cost_usd = Σ tokens × price`; unknown model ⇒ null cost but counts still tracked.
- **Why**: prices change and vary by provider; an editable table keeps it accurate without code changes. Never show a wrong number — show null + "未知价格".

### Decision 3: Nested runs roll up
A `subworkflow` child run's cost rolls into the parent's totals (and is also visible on the child).
- **Why**: "how much did this run cost?" must include sub-runs; matches Prefect's parent/child rollup.

### Decision 4: Per-node breakdown from event/trace linkage
Costs are attributed to the node/step that produced them, enabling the breakdown view.
- **Why**: the actionable insight is *which* node is expensive.

## Risks / Trade-offs

- [Wrong prices] → editable table + null on unknown; the number is labelled "估算".
- [Double counting trace + cost_hint] → traces take precedence; when both exist, the hint is ignored for that call.
- [Nested rollup complexity] → child totals computed first, then summed into the parent at child completion.

## Migration Plan

- Additive `Run` cost columns (default 0/null).
- Seed `model_prices` on first boot; editable in Settings.
- Existing runs show zero/"无成本数据".

## Open Questions

- Cache vs. recompute the window summary? (Lean: compute on read for the POC; cache if it gets slow.)
- Show cost in the livestream/run header in real time? (Lean: yes, update the running total as traces arrive.)
