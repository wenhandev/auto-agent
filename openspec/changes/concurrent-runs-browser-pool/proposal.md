## depends_on

- `auto-agent-platform` — the single-Chromium singleton, the per-workflow FIFO run queue, the `Run` lifecycle, the `lifespan`.
- `browser-sessions-profiles` — the context-pool/session-manager abstraction this change scales out.

Soft synergy with `run-artifacts-observability` (artifacts must be keyed per concurrent run) and `browser-livestream` (one stream per run).

## Why

`auto-agent` runs **one run at a time** against a single Chromium tab. The whole queue stalls behind a slow vision run, an approval pause holds the only slot, and an API caller's `run-task` waits behind unrelated work. Skyvern's infrastructure does "**parallel execution at scale**". To be usable as a real platform — and to make `public-api-and-auth`/`sdk-and-mcp` worth having — `auto-agent` needs bounded concurrency: N runs in N isolated browser contexts.

## What Changes

- **Browser context pool**: generalise the `browser-sessions-profiles` manager into a pool of up to `MAX_CONCURRENT_RUNS` (default 3) live contexts, each isolated. The single browser *process* stays; contexts are the unit of parallelism. Session-bound runs attach to their pinned context; pool runs borrow a free context and release it on completion.
- **Run scheduler rework**: the per-workflow FIFO queue becomes a global **dispatcher** that admits up to `MAX_CONCURRENT_RUNS` simultaneously, preserving per-workflow ordering (a workflow's runs still serialise relative to each other unless `allow_parallel_per_workflow` is set). Approval-paused runs **release their pool slot** (resolving the `human-in-the-loop` tradeoff) — the context is parked, the slot freed, re-acquired on resume.
- **Concurrency-safe state**: per-run isolation of the executor context, the perception layer, livestream hub keying, and artifact paths (all already keyed by `run_id`; this change audits and locks any shared mutable state). The model cache is read-mostly and shared.
- **Backpressure**: when the pool is full, new runs stay `queued` with a computed queue position; the API returns it. A configurable `MAX_QUEUE_DEPTH` rejects with `429` beyond a ceiling.
- **Fairness**: round-robin across workflows so one busy workflow can't starve others.
- **UI**: the run-list shows live concurrency (N running / M queued) and per-run queue position; a Settings control for `MAX_CONCURRENT_RUNS`.

## Capabilities

### New Capabilities

- `concurrent-run-dispatcher`: the global dispatcher admitting up to N runs, per-workflow ordering, round-robin fairness, queue-position reporting, `MAX_QUEUE_DEPTH` backpressure, and the slot-release-on-approval behaviour.
- `browser-context-pool`: the bounded pool of isolated contexts over the single browser process, borrow/release lifecycle, and session-pinned vs. pooled contexts.

### Modified Capabilities

- `run-history` (from `auto-agent-platform`): the FIFO-per-workflow queue becomes the concurrent dispatcher; `RunSummary` exposes `queue_position` and the run-list shows concurrency.
- `hybrid-executor` (from `auto-agent-mvp`): the executor acquires a pooled context instead of the singleton; per-run state isolation is enforced.
- `approval-node` (from `human-in-the-loop`): an approval-paused run releases its pool slot (the v1 "holds the slot" tradeoff is resolved); the context is parked and re-acquired on resume.
- `browser-sessions` (from `browser-sessions-profiles`): the session manager is the pool; `MAX_LIVE_SESSIONS` and `MAX_CONCURRENT_RUNS` are reconciled.

## Impact

- **Backend**: dispatcher rewrite in `services.runs`/`services.scheduler`, pool in `services.browser_sessions`, an audit pass for shared mutable state, slot-release on approval. New settings `MAX_CONCURRENT_RUNS=3`, `MAX_QUEUE_DEPTH`, `allow_parallel_per_workflow`. Tests: N-concurrent isolation, per-workflow ordering, fairness, backpressure 429, approval slot release/re-acquire, restart drains in-flight to `failed`.
- **Frontend**: run-list concurrency + queue-position; Settings concurrency control.
- **Runtime**: memory scales with `MAX_CONCURRENT_RUNS` × per-context cost; the default of 3 is conservative for a laptop. CPU bound by the LLM/network, not the browser, for vision runs.
- **Migration**: no DB migration; behavioural. With `MAX_CONCURRENT_RUNS=1` the system behaves exactly as today (safe default-compatible mode).
- **Out of scope**: multi-process / multi-machine workers (distributed scheduler — explicitly deferred in `triggers-and-scheduling` and here); autoscaling; per-run resource quotas beyond the slot; GPU/headed display multiplexing.
