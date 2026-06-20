## Why

`auto_agent` already has Playwright-backed browser control, vision actions, autonomous tasks, sessions, selector cache, artifacts, and Skyvern-like platform surfaces. The next gap is the modern browser-agent runtime layer: Playwright/CDP should remain the execution driver, while users and agents interact with higher-level hybrid primitives, compact memory, route-aware skills, stable snapshot refs, and provider-neutral fallbacks for UI that cannot be handled structurally.

This change captures the architecture shift seen in Stagehand, browser-use, Skyvern SDK, Playwright MCP, and Computer Use systems: deterministic browser control for the stable path, AI primitives for dynamic pages, Computer Use as a fallback, and observable memory/recovery loops for production reliability.

## What Changes

- Add Stagehand/Skyvern-style **hybrid browser primitives**: `observe`, `act`, `extract`, and `agent_task`, backed by the existing browser, perception, selector cache, autonomous loop, run events, and artifacts.
- Add **session-scoped compact agent memory** for browser sessions: objective/result summaries and extracted facts are persisted separately from live DOM/screenshot state and injected into later autonomous runs on the same session.
- Add **URL pattern route skills**: route-matched prompt constraints and allowed tool gates using the existing URL normalisation strategy.
- Add **stable snapshot refs** for interactive elements so agent actions can target short-lived refs instead of only brittle selectors or per-snapshot numeric indices.
- Add a provider-neutral **Computer Use fallback** controller that can execute screenshot/coordinate actions when DOM/a11y/selector strategies fail, while preserving approval, safety, and artifact auditing.
- Add a pluggable **browser provider** boundary so local Playwright remains the default but remote CDP and cloud browser providers can be introduced without rewriting the agent loop.
- Add **agent loop metrics** summarising round count, no-effect count, tool success/failure, fallback usage, cache hit/miss, stop reason, and usage cost.
- No breaking changes to existing graph workflows, browser sessions, selector cache, or autonomous task APIs.

## Capabilities

### New Capabilities

- `hybrid-browser-primitives`: Developer-facing `observe`/`act`/`extract`/`agent_task` primitives that combine deterministic browser control, cache-first replay, perception, LLM resolution, and autonomous fallback.
- `session-agent-memory`: Browser-session-scoped compact memory that stores task summaries and extracted facts without storing stale DOM, screenshots, or full tool traces.
- `route-skill-runtime`: URL-pattern-matched prompt/tool constraints that steer the agent based on the current route or site area.
- `snapshot-element-refs`: Short-lived stable element references derived from fresh page snapshots for deterministic click/type/select targeting.
- `computer-use-fallback`: A provider-neutral screenshot/coordinate action loop used only when structured browser control is insufficient.
- `browser-provider-runtime`: A runtime boundary for local Playwright, remote CDP, and future cloud browser providers.
- `agent-loop-metrics`: Aggregated observability for autonomous/hybrid agent loops.

### Modified Capabilities

- None. Existing change-level capabilities (`autonomous-agent-loop`, `browser-sessions`, `selector-action-cache`, `vision-action-mode`, `run-cost-aggregation`, and `run-artifacts-observability`) remain compatible; this change composes them behind new runtime contracts.

## Impact

- **Backend**: new services around browser primitives, route skills, session memory, snapshot refs, Computer Use controllers, provider adapters, and loop metrics. Existing modules likely affected include `app/agents/autonomous.py`, `app/agents/autonomous_llm.py`, `app/services/perception.py`, `app/services/selector_cache.py`, `app/services/browser_sessions.py`, `app/services/browser_pool.py`, `app/tools/browser.py`, `app/services/runs.py`, and API schemas/routers.
- **Database**: additive tables/columns for session compact memory, route skills, optional browser provider metadata, and persisted metrics summaries.
- **API/SDK**: additive endpoints or SDK methods for the hybrid primitives, route skill management, session memory clearing, and provider selection.
- **Frontend**: optional surfaces for route skill configuration, session memory visibility/clear, primitive run traces, fallback badges, and metrics cards.
- **Runtime/cost**: deterministic and cache-first paths remain preferred; LLM and Computer Use calls are bounded by budgets and recorded in cost/artifact traces.
- **Safety**: Computer Use and route skills must respect existing allowed domains, confirmation gates, approval flows, and artifact audit requirements.
