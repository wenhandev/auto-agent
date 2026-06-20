## depends_on

- `self-healing-selectors` — the heal events (`node_self_healed` with `old_selector`/`new_selector`/`confidence`) this change persists and reuses.
- `vision-action-mode` — the vision action plan (chosen element per step) this change caches to skip the LLM on re-runs.
- `auto-agent-platform` — persistence, `runtime-llm-config`.

No hard dependency on other in-flight changes.

## Why

Vision and self-heal are powerful but **expensive and slow** — every run re-asks the LLM where to click even when the page hasn't changed. Skyvern advertises "**code caching for repeatability and cost savings**" and Stagehand's whole pitch is "auto-caching combined with self-healing... knows when to involve AI". `self-healing-selectors` explicitly flagged "caching healed selectors (per-workflow learning that bypasses the LLM after the first successful heal)" as the next iteration. This change adds that learning layer: remember what worked, skip the LLM next time, fall back to vision/heal when the cache misses.

## What Changes

- **Cache store**: a `SelectorCache` SQLModel keyed by `(workflow_id, node_id, page_url_pattern)` → `{resolved_selector | element_signature, kind, last_verified_at, hit_count, miss_count}`. For vision nodes, the cached entry is the **resolved element signature / action plan** for a given page signature, not free text.
- **Page-URL pattern**: URLs are normalised to a pattern (drop volatile query params/ids) so `/product/123` and `/product/456` share a cache entry where appropriate; the normaliser is configurable per node.
- **Read path (cache-first)**: before invoking the LLM for a `click`/`fill`/`vision_act` step, the executor checks the cache. On hit, it tries the cached selector/plan deterministically. On success → no LLM call (the win). On failure → fall through to vision/self-heal as today, and **update** the cache with the new result.
- **Self-heal integration**: a successful `node_self_healed` writes its `new_selector` to the cache automatically (the operator-approval chat-prefill from `self-healing-selectors` remains available, but learning no longer *requires* manual application — Decision below resolves the audit-vs-automation tension).
- **Invalidation**: an entry is evicted after `CACHE_MAX_MISSES` consecutive misses or `CACHE_TTL_DAYS`; the UI can clear a workflow's cache.
- **Events/UI**: `cache_hit` / `cache_miss` events (carry the entry id + the avoided cost); the run timeline shows a "⚡ cached" badge on steps that skipped the LLM; a per-workflow "选择器缓存" panel lists entries with hit/miss stats and a "清空缓存" button; `run-cost-tracking` shows cost *avoided* by cache hits.

## Capabilities

### New Capabilities

- `selector-action-cache`: the `SelectorCache` entity, the URL-pattern normaliser, the cache-first read path with deterministic replay + vision/heal fallback, self-heal write-through, invalidation policy, the cache events + badge + management UI.

### Modified Capabilities

- `selector-self-healing` (from `self-healing-selectors`): a successful heal writes through to the cache; the chat-prefill audit path is preserved but no longer the only way learning happens.
- `vision-action-primitives` (from `vision-action-mode`): vision steps consult the cache before the LLM and write the resolved plan on success.
- `hybrid-executor` (from `auto-agent-mvp`): `click`/`fill`/`vision_*` dispatch gains the cache-first lookup.
- `run-cost-tracking` (soft): surfaces "cost avoided" from `cache_hit` events.

## Impact

- **Backend**: new model + `app/services/selector_cache.py` (~150 LOC), the URL normaliser, cache-first hooks in the executor + self-heal write-through. New events. Tests: hit→no-LLM, miss→fallback+update, normalisation grouping, invalidation after N misses, TTL eviction.
- **Frontend**: cache panel + "⚡ cached" badge + clear button. ~150 LOC.
- **Runtime**: a cache hit replaces an LLM/vision round-trip with a deterministic selector try — the core cost/latency win. A miss adds one cheap DB lookup before the existing path.
- **Migration**: `create_all` makes `selector_cache`; new settings `CACHE_MAX_MISSES`, `CACHE_TTL_DAYS`, default-on `selector_cache_enabled` toggle on `LlmConfig`. Existing workflows start with an empty cache (cold) and warm over runs.
- **Out of scope**: cross-workflow cache sharing; a global selector knowledge base; semantic page-change detection beyond URL pattern + cached-selector-success (a future `page-fingerprint-cache` could key on DOM structure hash); caching `http_request`/`parse_*` outputs (that's response caching, a different change).
