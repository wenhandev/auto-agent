## Context

The platform deliberately chose one-run-at-a-time with a single Chromium tab to keep the POC simple. `browser-sessions-profiles` already introduced a manager that holds multiple contexts. Concurrency is the natural next step: contexts are isolated, so N contexts = N parallel runs, bounded to protect a single machine.

## Goals / Non-Goals

**Goals:**
- Bounded parallelism (N isolated runs) with per-workflow ordering preserved by default.
- Free the slot an approval-paused run was holding.
- A safe `MAX_CONCURRENT_RUNS=1` mode identical to today.

**Non-Goals:**
- Multi-process/distributed workers.
- Autoscaling.
- Per-run CPU/memory quotas.

## Decisions

### Decision 1: Contexts, not processes, are the parallelism unit
One browser process, a pool of ≤N contexts.
- **Why**: contexts are isolated (cookies/storage/page) and far cheaper than processes; matches the session manager already built.
- **Alternative rejected**: process-per-run (heavy, slow to spawn, complex lifecycle).

### Decision 2: Global dispatcher, per-workflow ordering by default
A single dispatcher admits up to N runs; runs of the same workflow serialise unless `allow_parallel_per_workflow`.
- **Why**: preserves the safety of today's per-workflow FIFO (a workflow that logs in then acts must not race itself) while allowing cross-workflow parallelism. Opt-in parallelism within a workflow for stateless ones.

### Decision 3: Approval-paused runs release the slot
On `node_awaiting_approval`, the run parks its context (kept alive, not pooled) and frees its dispatcher slot; on resume it re-acquires a slot (may queue).
- **Why**: resolves `human-in-the-loop` Decision 4's known tradeoff; a human taking an hour must not block N-1 other runs.
- **Trade-off**: a parked context still consumes memory; bounded by `MAX_PARKED_CONTEXTS`.

### Decision 4: Round-robin fairness across workflows
The dispatcher picks the next admit round-robin over workflows with queued runs.
- **Why**: prevents one busy workflow from starving others.

### Decision 5: Audit shared mutable state, lock or per-run-key it
Executor context, perception caches, livestream hub, artifact paths are all `run_id`-keyed; the model cache is read-mostly. An explicit audit + locks where needed.
- **Why**: correctness under concurrency; most state is already per-run by construction.

### Decision 6: `MAX_CONCURRENT_RUNS=1` ≡ today
The default-compatible mode behaves identically to the current single-run platform.
- **Why**: zero-risk rollout; operators opt into concurrency.

## Risks / Trade-offs

- [Memory blow-up at high N] → conservative default (3) + parked-context cap + Settings control.
- [Races in shared state] → audit + locks; concurrency tests asserting isolation.
- [Per-workflow self-race if misconfigured] → `allow_parallel_per_workflow` defaults off.
- [Restart with in-flight runs] → mark in-flight `failed` on boot (no resumable browser state, consistent with prior changes).

## Migration Plan

- Generalise the session manager into a pool; rework the queue into a dispatcher.
- New settings `MAX_CONCURRENT_RUNS=3`, `MAX_QUEUE_DEPTH`, `MAX_PARKED_CONTEXTS`, `allow_parallel_per_workflow`.
- Ship with concurrency enabled at 3; document the `=1` compatibility mode.

## Open Questions

- Priority lanes (API run-task vs. cron) — do interactive runs preempt scheduled ones? (Lean: simple FIFO+round-robin v1; priorities later.)
- Per-workflow concurrency caps (allow 2 of workflow A, 1 of B)? (Defer; global cap + per-workflow ordering is enough for v1.)
