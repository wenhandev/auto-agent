## Context

`auto_agent` has already implemented the core platform layers: workflow graphs, item data model, expression evaluation, autonomous tasks, vision actions, browser sessions/profiles, selector cache learning, artifacts, cost tracking, captcha handling, public APIs, SDK/MCP surfaces, and org/auth support. The remaining architectural gap is not raw browser execution; it is the runtime abstraction used by agents and users.

The current browser stack is Playwright-backed and selector/vision-node oriented. That remains valuable for reliability and cost. Modern browser-agent systems, however, converge on a hybrid architecture:

```text
deterministic driver: Playwright / CDP / WebDriver
  -> AI primitives: observe / act / extract / agent
  -> autonomous loop: memory / recovery / route context
  -> fallback: Computer Use screenshot + coordinates
  -> infrastructure: local browser or remote/cloud provider
```

This design keeps Playwright/CDP as the execution layer and adds a runtime layer that composes existing capabilities instead of replacing them.

## Goals / Non-Goals

**Goals:**

- Provide a stable `observe` / `act` / `extract` / `agent_task` abstraction over existing browser tools, perception, cache, artifacts, and autonomous tasks.
- Add compact session memory that preserves useful operator context across runs without persisting stale page state.
- Add URL-pattern route skills to constrain prompts and tools by site/route.
- Add short-lived snapshot refs so agent actions can target fresh page elements deterministically.
- Add Computer Use as an explicit fallback path for UI that cannot be handled structurally.
- Add a provider boundary for local Playwright and remote CDP, with cloud browser providers as future adapters.
- Add loop metrics so reliability, no-progress behavior, fallback use, cache use, and cost are visible.

**Non-Goals:**

- Replacing Playwright or CDP as the browser execution substrate.
- Embedding browser-use, Stagehand, or another external agent framework into the core executor.
- Making Computer Use the default execution path.
- Persisting full DOM snapshots, screenshots, or full tool traces as long-term memory.
- Building a Chrome extension or frontend-embedded agent SDK in this change.
- Adding full cloud browser provider implementations beyond the provider interface and minimal remote CDP support.

## Decisions

### Decision 1: Hybrid primitives are a service layer, not new node types first

Add a backend service boundary for `observe`, `act`, `extract`, and `agent_task`. Graph nodes, public API handlers, SDKs, and autonomous mode can call the same service.

- `observe(instruction, context)` returns candidate refs/elements and confidence without side effects.
- `act(instruction, context)` resolves and executes one browser action, preferring cache/deterministic paths before LLM/vision.
- `extract(instruction, schema, context)` returns schema-validated data.
- `agent_task(objective, context)` delegates to the autonomous loop with the same events/artifacts/cost accounting.

Rationale: adding primitives as reusable services avoids duplicating logic across graph nodes, task mode, API endpoints, and SDKs. New graph node forms can be added later as thin wrappers.

Alternative considered: add only new workflow node types. Rejected because it would not help autonomous/API/SDK consumers and would keep the runtime abstraction scattered.

### Decision 2: Compact session memory is separate from page facts

Browser session memory stores compact messages such as objective, final summary, extracted facts summary, final URL, and success/failure status. It MUST NOT store full DOM, screenshots, accessibility trees, or raw tool traces.

The autonomous prompt can receive:

- current observation from fresh perception as the only page fact source;
- compact session memory as historical operator context;
- run memory as the current task scratchpad.

Rationale: AutoPilot-style memory is useful for continuity, but UI state goes stale quickly. Separating memory from fresh perception reduces hallucinated actions and token growth.

Alternative considered: reuse `RunEvent`/`llm_trace` as future prompt input. Rejected as default behavior because traces are too large and can contain stale or unsafe page content.

### Decision 3: Route skills use URL patterns and intersect allowed tools

Route skills are matched using the existing URL normalisation strategy where possible. Each skill contains a route pattern, priority, enabled flag, prompt constraints, and optional allowed tools. If a task also has `allowed_tools`, the effective tool set is the intersection.

Rationale: route skills are a low-risk way to add site-specific behavior for ERP/SPA pages while preserving global task guardrails.

Alternative considered: route skills override task tool allowlists. Rejected because route configuration should not expand a user's explicit safety boundary.

### Decision 4: Snapshot refs are short-lived and observation-bound

Perception emits stable-ish refs derived from current snapshot structure, such as URL pattern + role/name + structural path/signature hash. Refs are valid only within the current run/session ref map and must be revalidated against the latest observation before action.

Rationale: refs improve determinism compared with numeric indices, but long-lived refs become stale. Keeping them short-lived aligns with the "fresh snapshot is truth" rule.

Alternative considered: make refs permanent cache keys. Rejected because selector/action cache already handles long-lived reuse with miss/eviction policies.

### Decision 5: Computer Use is a fallback controller with explicit audit

Define a provider-neutral controller for screenshot/coordinate actions (`screenshot`, `click_at`, `type_text`, `scroll`, `keypress`, `drag`, `wait`). The first implementation can execute coordinates locally through the current Playwright page; external providers are adapter implementations later.

Computer Use is entered only when configured and when structured methods fail or are unsuitable, such as canvas-heavy UI, inaccessible iframe content, or repeated no-effect DOM actions. Each fallback action records reason, screenshot artifact, provider, coordinates/actions, and result.

Rationale: Computer Use expands coverage but is slower, costlier, and riskier. Treating it as a fallback keeps normal runs fast and auditable.

Alternative considered: use Computer Use as the primary autonomous mode. Rejected due to cost, latency, weaker determinism, and weaker structured observability.

### Decision 6: Browser providers expose capabilities, not implementation details

Introduce a provider boundary with capabilities such as `persistent_context`, `remote_cdp`, `recording`, `live_view`, `proxy`, `captcha`, and `computer_use`. The default provider remains local Playwright. Remote CDP is the first non-local adapter. Cloud browser providers can be added behind the same interface later.

Rationale: provider capability checks let runs fail explicitly when a requested feature is unsupported instead of silently degrading.

Alternative considered: add provider-specific branches in `browser_pool` and `browser_sessions`. Rejected because it would spread provider logic across runtime modules.

### Decision 7: Loop metrics are written as summaries, events remain detailed

The runtime should continue emitting detailed step events. At completion, it writes an aggregate metrics summary containing round count, tool success/failure, no-effect count, fallback count, cache hits/misses, final stop reason, and usage/cost.

Rationale: detailed events support replay/debugging; summary metrics support dashboards, regression analysis, and quick run triage.

## Risks / Trade-offs

- **Scope creep across many subsystems** -> Land in phases: hybrid primitives + autonomous stability first, then session memory/route skills, then Computer Use/provider adapters, then UI polish.
- **Prompt/tool conflicts from route skills** -> Resolve with deterministic precedence: task safety constraints and allowed tools always win; route skills only narrow or guide behavior.
- **Stale memory causing wrong actions** -> Never persist DOM/screenshots as memory; prompts must state that current observation is the only page fact source.
- **Computer Use cost or unsafe actions** -> Default disabled; require configuration; record artifacts; reuse existing confirmation gates and domain restrictions.
- **Provider abstraction too generic** -> Start with only capabilities needed by current local Playwright and remote CDP; add cloud-specific details only when implementing a provider.
- **Refs drifting across DOM changes** -> Revalidate refs against the latest observation and fall back to current indices/perception when confidence is low.

## Migration Plan

1. Additive services and schemas only; existing graph workflows and task runs continue using current paths.
2. Introduce hybrid primitives behind internal service APIs and tests.
3. Add session memory fields/tables and route skill tables with default-empty behavior.
4. Add snapshot refs to perception while retaining existing numeric indices.
5. Add Computer Use controller disabled by default.
6. Add provider capability metadata with `local_playwright` as the default.
7. Add metrics summary generation after the loop is stable.

Rollback is straightforward for each phase because defaults preserve current behavior. If a later phase fails, disable the feature flag/config and keep existing Playwright/vision/autonomous execution.

## Open Questions

- Should route skills be global, org-scoped, workflow-scoped, or all three? Initial implementation should prefer org/workflow scoping to avoid cross-tenant leakage.
- Should session memory be retained after a browser session expires, or only while the session row exists? Initial implementation should keep memory until explicit delete/clear of the session row.
- Which Computer Use provider should be implemented first after the neutral controller: OpenAI, Anthropic, Gemini, or none until the local coordinate harness is proven?
- Should hybrid primitives become first-class workflow nodes in the same change, or should the first implementation expose backend service/API only and add node UI later?
