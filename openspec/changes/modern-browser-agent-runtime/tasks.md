## 1. Foundations

- [x] 1.1 Add focused backend tests for the hybrid primitive service contracts: `observe` has no page side effects, `act` executes one action, `extract` validates schema, and `agent_task` emits autonomous task events.
- [x] 1.2 Create the backend primitive service module with provider-neutral request/response models for `observe`, `act`, `extract`, and `agent_task`.
- [x] 1.3 Wire primitive calls to existing run context, artifact context, cost tracking, and run event emission without changing existing graph node behavior.
- [x] 1.4 Run the new primitive service tests and confirm existing autonomous and vision tests still pass.

## 2. Hybrid Browser Primitives

- [x] 2.1 Implement `observe` using fresh perception and candidate element formatting with refs, labels, roles, confidence, and source metadata.
- [x] 2.2 Implement `act` with cache-first replay for eligible actions and fallback to perception/LLM resolution when cache is missing or stale.
- [x] 2.3 Implement cache write-through for successful `act` resolutions using existing selector/action cache policies.
- [x] 2.4 Implement `extract` with schema validation and audit metadata for LLM/perception calls.
- [x] 2.5 Implement `agent_task` as a thin wrapper over autonomous task mode, preserving budgets, browser session/profile, allowed domains/tools, confirmation settings, run events, artifacts, and cost tracking.
- [x] 2.6 Add API or internal service entry points needed by backend tests and future SDK/UI surfaces.

## 3. Autonomous Stability Memory

- [x] 3.1 Extend autonomous run memory with explicit original goal anchor, remaining/in-progress plan context, and last-action effect summary.
- [x] 3.2 Update autonomous LLM prompt construction so the original objective is always present and current observation is declared as the only source of page facts.
- [x] 3.3 Add effect-check logic comparing before/after observations for URL, title, element signature, key text, extracted data, and repeated no-effect actions.
- [x] 3.4 Emit effect-check summaries into step events and bounded working memory.
- [x] 3.5 Add tests for no-effect detection, repeated action handling, prompt goal anchoring, and preserving existing budget/guardrail behavior.

## 4. Session Agent Memory

- [x] 4.1 Add additive database migration/model support for browser-session compact memory entries or a bounded `memory_json` field.
- [x] 4.2 Implement session memory service functions to append, list, bound/compact, and clear memory entries.
- [x] 4.3 Append compact memory after autonomous or hybrid runs attached to a browser session, excluding DOM, screenshots, accessibility trees, and raw tool traces.
- [x] 4.4 Inject relevant session memory into later runs on the same browser session while preserving the fresh-observation contract.
- [x] 4.5 Add API/schema support to inspect and clear session memory.
- [x] 4.6 Add tests for empty session memory, append-on-finish, injection-on-next-run, clear behavior, and deletion cleanup.

## 5. Route Skill Runtime

- [x] 5.1 Add route skill database model and migration with scope, URL pattern, priority, enabled flag, prompt constraints, and allowed tools.
- [x] 5.2 Implement route skill matching using existing URL normalization where possible.
- [x] 5.3 Merge route prompts into autonomous/hybrid prompt context without replacing original objective or safety instructions.
- [x] 5.4 Intersect route allowed tools with task-level allowed tools so route skills can narrow but never expand the tool surface.
- [x] 5.5 Record applied route skill identifiers and prompt/tool effects in run events or LLM traces.
- [x] 5.6 Add tests for normalized URL matching, priority order, disabled skills, prompt trace visibility, and allowed-tool intersection.

## 6. Snapshot Element Refs

- [x] 6.1 Extend perception output with short-lived refs for interactive elements while retaining existing numeric indices.
- [x] 6.2 Add a run/session ref resolver that revalidates refs against the latest observation before action.
- [x] 6.3 Update click/type/select/drag actions to accept valid refs in addition to indices.
- [x] 6.4 Ensure invalid or low-confidence refs do not act on stale page state and return a clear resolution error or safe fallback.
- [x] 6.5 Feed successful ref-based actions into selector/action cache write-through without storing refs as permanent cache keys.
- [x] 6.6 Add tests for ref generation, ref action success, index backward compatibility, stale ref rejection, and cache integration.

## 7. Computer Use Fallback

- [x] 7.1 Define the provider-neutral Computer Use controller interface for screenshot, click-at, type-text, scroll, keypress, drag, and wait.
- [x] 7.2 Implement the initial local Playwright coordinate executor behind the Computer Use controller interface.
- [x] 7.3 Add configuration to keep Computer Use disabled by default and provider-unavailable errors explicit.
- [x] 7.4 Add fallback selection logic for configured cases where structured cache/ref/DOM/perception execution fails or is unsuitable.
- [x] 7.5 Record provider, fallback reason, screenshot artifact, action payload, coordinates, result, and URL for every Computer Use action.
- [x] 7.6 Enforce existing allowed-domain and confirmation guardrails before high-risk Computer Use actions.
- [x] 7.7 Add tests for disabled fallback, provider-unavailable error, local coordinate execution, audit event emission, and guardrail enforcement.

## 8. Browser Provider Runtime

- [x] 8.1 Define browser provider interfaces and capability metadata for local Playwright, remote CDP, and future cloud providers.
- [x] 8.2 Refactor browser session/pool acquisition to use the provider interface while preserving current local Playwright behavior by default.
- [x] 8.3 Implement remote CDP session attachment with secret-safe metadata handling.
- [x] 8.4 Add provider capability checks that fail clearly when a requested feature is unsupported.
- [x] 8.5 Persist provider identifier and non-secret connection metadata on browser sessions/runs.
- [x] 8.6 Add tests proving local Playwright behavior remains unchanged, remote CDP configuration is accepted, unsupported capabilities fail clearly, and secrets are not exposed.

## 9. Agent Loop Metrics

- [x] 9.1 Add metrics accumulator for autonomous and hybrid primitive loops: round count, tool successes/failures, cache hits/misses, Computer Use fallbacks, no-effect count, final stop reason, and usage/cost.
- [x] 9.2 Write metrics summary to run detail storage and emit an `agent_loop_metrics` run event on terminal completion/failure.
- [x] 9.3 Expose metrics summary in run detail API responses.
- [x] 9.4 Add tests for successful metrics, failed/no-progress metrics, metrics API visibility, and coexistence with detailed events/artifacts.

## 10. Frontend and SDK Surfaces

- [x] 10.1 Add minimal frontend visibility for session memory inspect/clear where browser sessions are managed.
- [x] 10.2 Add route skill management UI or a backend-only API smoke path if UI scope is deferred.
- [x] 10.3 Add run detail badges or summary rows for cache hits, fallback usage, route skill application, and agent loop metrics.
- [x] 10.4 Update Python/TypeScript SDK surfaces or examples for `observe`, `act`, `extract`, and `agent_task` if SDK support is in scope for this change.

## 11. Verification

- [x] 11.1 Run focused backend tests for primitives, autonomous loop, browser sessions, selector cache, route skills, refs, Computer Use, providers, and metrics.
- [x] 11.2 Run the full backend test suite.
- [x] 11.3 Run frontend build/tests if frontend surfaces are implemented.
- [x] 11.4 Run `openspec validate modern-browser-agent-runtime`.
- [x] 11.5 Manually smoke-test a local browser task that uses `observe` → `act` → `extract`, and verify run events/artifacts/metrics are coherent.
