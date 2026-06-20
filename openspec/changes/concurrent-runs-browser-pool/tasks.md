## 1. Context pool

- [x] 1.1 Generalise the session manager into a bounded pool (≤ `MAX_CONCURRENT_RUNS` contexts)
- [x] 1.2 Borrow/release lifecycle for pooled runs; pin session-bound runs to their context
- [x] 1.3 Parked-context handling with `MAX_PARKED_CONTEXTS`
- [x] 1.4 Settings `MAX_CONCURRENT_RUNS=3`, `MAX_QUEUE_DEPTH`, `MAX_PARKED_CONTEXTS`, `allow_parallel_per_workflow`

## 2. Dispatcher

- [x] 2.1 Replace FIFO-per-workflow with a global dispatcher admitting ≤ N
- [x] 2.2 Preserve per-workflow ordering unless `allow_parallel_per_workflow`
- [x] 2.3 Round-robin fairness across workflows
- [x] 2.4 Queue-position computation + `MAX_QUEUE_DEPTH` 429
- [x] 2.5 Release dispatch slot on approval pause; re-acquire on resume

## 3. Concurrency safety

- [x] 3.1 Audit shared mutable state (executor ctx, perception, livestream hub, artifacts) for per-run keying
- [x] 3.2 Add locks where shared state is unavoidable; keep model cache read-mostly
- [x] 3.3 On restart, mark in-flight runs `failed`

## 4. Frontend

- [ ] 4.1 Run-list shows concurrency (N running / M queued) + per-run queue position
- [ ] 4.2 Settings control for `MAX_CONCURRENT_RUNS`

## 5. Tests

- [x] 5.1 N-concurrent isolation
- [x] 5.2 Per-workflow ordering + opt-in parallel
- [x] 5.3 Round-robin fairness; backpressure 429
- [x] 5.4 Approval slot release + re-acquire
- [x] 5.5 `MAX_CONCURRENT_RUNS=1` equivalence to current behaviour
