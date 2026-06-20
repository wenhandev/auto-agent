## Context

`self-healing-selectors` chose chat-prefill (operator approves a healed selector) for auditability and explicitly deferred caching. `vision-action-mode` resolves an element per step via the LLM. Both pay the LLM tax every run. Stagehand and Skyvern both cache the resolved action to skip AI when the page is unchanged. This change adds that cache as a read-through layer, keeping vision/heal as the miss path.

## Goals / Non-Goals

**Goals:**
- Skip the LLM when a previously-resolved selector/plan still works.
- Automatically learn from successful heals and vision resolutions.
- Safe fallback + self-correcting invalidation on misses.

**Non-Goals:**
- Cross-workflow / global selector knowledge base.
- Response caching for HTTP/parse nodes.
- DOM-structure fingerprinting (future).

## Decisions

### Decision 1: Cache key = (workflow, node, normalised page-URL)
Entries are scoped to a node within a workflow at a URL pattern.
- **Why**: a node's target is stable per page; scoping avoids cross-contamination. URL pattern lets `/product/{id}` pages share an entry.

### Decision 2: Cache-first, deterministic replay, fall through on failure
On hit, try the cached selector/plan with a short timeout; success skips the LLM; failure falls through to vision/heal and updates the entry.
- **Why**: the cache is an optimisation, never a correctness dependency. A stale entry self-heals on the next miss.

### Decision 3: Write-through from heal and vision success — resolve the audit tension
A successful heal/vision resolution writes the cache automatically. The `self-healing-selectors` chat-prefill (operator applies the selector to the *workflow JSON*) remains for *permanent* changes; the cache is a *runtime* memory that is always evictable.
- **Why**: `self-healing-selectors` Decision (no auto-persist to workflow) was about not silently mutating the authored workflow. The cache is separate, transient, and clearable — so automatic learning is safe without violating that principle.

### Decision 4: Self-correcting invalidation
Evict after `CACHE_MAX_MISSES` consecutive misses or `CACHE_TTL_DAYS`; track hit/miss counts.
- **Why**: a redesigned page should stop serving a dead selector quickly; TTL bounds staleness even for rarely-run workflows.

### Decision 5: Global + per-config toggle
`LlmConfig.selector_cache_enabled` (default on); a per-workflow clear.
- **Why**: cost-sensitive default-on; an escape hatch for debugging "is the cache lying to me?".

## Risks / Trade-offs

- [Stale entry causes a wrong-but-plausible action] → deterministic replay verifies the selector resolves; on any failure it falls through; misses evict. For vision, the cached plan is verified by the action succeeding.
- [URL over-normalisation groups distinct pages] → per-node configurable normaliser; conservative default (drop only known-volatile params).
- [Cache masks a real regression] → hit/miss stats + the "⚡ cached" badge make cache use visible; clear button forces cold re-resolve.
- [Concurrency writes] → upsert with last-write-wins keyed on the tuple; benign under `concurrent-runs-browser-pool`.

## Migration Plan

- `create_all` makes `selector_cache`. `LlmConfig.selector_cache_enabled` (additive, default true).
- New settings `CACHE_MAX_MISSES`, `CACHE_TTL_DAYS`.
- Cold start; warms over runs. No behaviour change beyond faster/cheaper repeat runs.

## Open Questions

- Cache the full multi-step vision plan vs. per-step element resolution? (Lean: per-step element signature first; full-plan caching is a follow-up once per-step proves out.)
- Surface "cache confidence" decay over time? (Defer; hit/miss + TTL is enough for v1.)
