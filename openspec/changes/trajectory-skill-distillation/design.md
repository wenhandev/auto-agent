## Context

`record-and-generate` captures action traces and synthesises draft workflows via deterministic rules. `modern-browser-agent-runtime` adds URL-scoped route skills whose `prompt` field is injected into autonomous and hybrid agent steps. Operators currently author route skills manually even when they have recordings or successful task trajectories that already encode site-specific know-how.

Browser-BC demonstrates a complementary pattern: **atomize** a long trace into segments, **classify** each segment into a capability, **bucket** evidence by domain+capability, and **distill** merged prose instructions. auto_agent adapts this pattern to its existing artifacts: Workflow JSON graphs and `RouteSkill` rows.

## Goals / Non-Goals

**Goals:**

- Turn stopped recordings into route skill **proposals** plus the existing workflow draft.
- Provide a deterministic distillation path that works without an LLM API key (tests + offline dev).
- On adopt, merge proposal prompt into an existing route skill when `url_pattern` matches, or create a new skill.
- Keep human-in-the-loop: proposals are never auto-enabled route skills.

**Non-Goals:**

- Chrome extension recording ingest (separate follow-up).
- Auto-running distilled workflows or auto-enabling proposals.
- Cross-org shared skill buckets.
- Replacing autonomous task execution or selector cache.

## Decisions

### Decision 1: Segment by normalized URL pattern

Atomization splits a trace when the normalized page URL changes (reuse `selector_cache.normalize_url`). Each segment carries its events, domain host, and url pattern.

- **Why**: route skills are URL-scoped today; segments align with runtime matching.

### Decision 2: Rule-based capability classification (LLM optional later)

Capabilities are inferred from event shapes: `login` (sensitive fill), `search` (fill then click), `form-submit`, `navigation`, `interaction` (default). Slugs are kebab-case, e.g. `login-with-credentials`, `search-and-select`.

- **Why**: deterministic tests; LLM can refine labels in a follow-up without blocking MVP.

### Decision 3: Distill route prompt as numbered operator instructions

Each segment becomes a markdown prompt listing steps derived from event descriptions/selectors, omitting sensitive values.

- **Why**: matches route skill injection semantics and Claude SKILL.md shape without a separate format.

### Decision 4: Proposals are first-class rows; adopt merges or creates

`RouteSkillProposal` stores distilled prompt + metadata. Adopt either updates an existing enabled `RouteSkill` with the same `url_pattern` and scope (append/consolidate prompt) or inserts a new disabled-by-default skill the operator can enable in settings.

- **Why**: preserves audit trail; avoids silent overwrite of production route skills.

### Decision 5: Workflow synthesis stays rule-based by default; LLM distiller is opt-in

`trace_to_graph` remains the default graph builder. When `llm_is_configured()`, an ADK distiller may rewrite the graph from the trace; validation failure falls back to rules.

- **Why**: matches existing platform pattern (planner requires key; demos work without).

## Risks / Trade-offs

- [Over-segmentation on SPAs] → normalize URL strips volatile query params; single-page flows may produce one segment (acceptable).
- [Noisy recordings] → scroll/wait events dropped during distillation (same as synthesis).
- [Prompt merge duplicates] → adopt concatenates with a separator; operator edits in route skill UI.
- [LLM cost] → LLM workflow distillation only when configured and explicitly requested via `use_llm=true`.

## Migration Plan

- Add `route_skill_proposal` table via `create_all`.
- New routes under `/api/route-skill-proposals` and `/api/recordings/{id}/distill`.
- Extend generate endpoint to persist proposals; UI adds proposals panel.

## Open Questions

- Distill from successful autonomous task trajectories on finish? (Defer: recording-first MVP.)
- Org-scoped proposal visibility rules? (Lean: same as recordings list — global for now.)
