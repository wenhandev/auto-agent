## ADDED Requirements

### Requirement: Cache-first resolution

The system SHALL consult the selector/action cache before invoking the LLM for a `click`/`fill`/`vision_act` step, keyed by `(workflow_id, node_id, normalised_page_url)`.

#### Scenario: Cache hit skips the LLM

- **WHEN** a cached selector/plan exists for the step and replays successfully
- **THEN** the step completes without an LLM/vision call and a `cache_hit` event is emitted

#### Scenario: Cache miss falls through

- **WHEN** no cache entry exists or the cached selector/plan fails to replay
- **THEN** the step falls through to vision/self-heal as normal and a `cache_miss` event is emitted

### Requirement: Learning write-through

The system SHALL write a successful vision resolution or self-heal result into the cache for reuse.

#### Scenario: Successful heal cached

- **WHEN** a self-heal succeeds with a new selector
- **THEN** the cache entry for the step is updated with the new selector

#### Scenario: Stale entry self-corrects

- **WHEN** a cached selector fails and the fallback resolves a different selector
- **THEN** the cache entry is updated to the newly-resolved selector

### Requirement: URL pattern normalisation

The system SHALL normalise page URLs to a pattern so structurally-equivalent pages share a cache entry, with a per-node configurable normaliser.

#### Scenario: Volatile ids grouped

- **WHEN** the same node runs on `/product/123` and `/product/456`
- **THEN** both map to the same normalised pattern entry (subject to the node's normaliser config)

### Requirement: Invalidation policy

The system SHALL evict a cache entry after `CACHE_MAX_MISSES` consecutive misses or `CACHE_TTL_DAYS`, and allow clearing a workflow's cache.

#### Scenario: Evict after repeated misses

- **WHEN** a cached entry misses `CACHE_MAX_MISSES` times in a row
- **THEN** it is evicted so future runs re-resolve fresh

#### Scenario: Manual clear

- **WHEN** an operator clears a workflow's selector cache
- **THEN** all its entries are removed and subsequent steps re-resolve via vision/heal

### Requirement: Cache visibility

The system SHALL make cache use visible in the run timeline and expose hit/miss statistics.

#### Scenario: Cached step badged

- **WHEN** a step completes via a cache hit
- **THEN** the run timeline marks it with a "cached" badge and the avoided cost is attributed
