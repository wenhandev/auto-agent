## 1. Data & aggregation

- [x] 1.1 Add cost columns to `Run` (`total_input_tokens`, `total_output_tokens`, `total_llm_calls`, `total_vision_calls`, `estimated_cost_usd`)
- [x] 1.2 Accumulate `cost_hint` / `llm_trace` token counts in `services.runs` (traces authoritative)
- [x] 1.3 Subworkflow child→parent cost rollup
- [x] 1.4 Per-node cost attribution

## 2. Pricing

- [x] 2.1 `model_prices` config (`input_per_1k`/`output_per_1k`), seeded on first boot
- [x] 2.2 Estimator: known model → cost; unknown → null + "未知价格"

## 3. API

- [x] 3.1 Expose totals on `RunOut`/`RunSummary`
- [x] 3.2 `GET /api/runs` sort-by-cost
- [x] 3.3 `GET /api/runs/cost-summary?from=&to=`

## 4. Frontend

- [ ] 4.1 Run-list cost column
- [ ] 4.2 Run-detail cost panel + per-node breakdown
- [ ] 4.3 Settings "模型价格" editor
- [ ] 4.4 Optional dashboard tile "近 7 天用量"

## 5. Tests

- [x] 5.1 Aggregation correctness incl. nested runs
- [x] 5.2 Unknown-model null cost
- [x] 5.3 Trace-over-hint precedence; window summary
