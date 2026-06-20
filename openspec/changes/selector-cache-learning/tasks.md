## 1. Cache store

- [x] 1.1 Add `SelectorCache` SQLModel keyed by `(workflow_id, node_id, page_url_pattern)`
- [x] 1.2 Create `app/services/selector_cache.py` with get/upsert/evict + hit/miss counters
- [x] 1.3 URL-pattern normaliser (drop volatile params), per-node configurable
- [x] 1.4 Settings `CACHE_MAX_MISSES`, `CACHE_TTL_DAYS`; `LlmConfig.selector_cache_enabled` (default on)

## 2. Executor integration

- [x] 2.1 Cache-first lookup before LLM for `click`/`fill`/`vision_act`
- [x] 2.2 Deterministic replay of cached selector/plan with short timeout
- [x] 2.3 Fall through to vision/self-heal on miss/failure and update the entry
- [x] 2.4 Emit `cache_hit` / `cache_miss` events (with avoided-cost hint)

## 3. Learning

- [x] 3.1 Write-through from successful self-heal (`node_self_healed`)
- [x] 3.2 Write-through from successful vision resolution
- [x] 3.3 Invalidation after `CACHE_MAX_MISSES` / `CACHE_TTL_DAYS`

## 4. Frontend

- [ ] 4.1 "⚡ cached" badge on cached steps in the run timeline
- [ ] 4.2 Per-workflow "选择器缓存" panel (entries + hit/miss stats + "清空缓存")
- [ ] 4.3 Surface "cost avoided" via run-cost-tracking when present

## 5. Tests

- [x] 5.1 Hit → no LLM call
- [x] 5.2 Miss → fallback + entry update
- [x] 5.3 URL normalisation grouping
- [x] 5.4 Invalidation after N misses + TTL eviction
