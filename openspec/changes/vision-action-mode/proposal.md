## depends_on

- `auto-agent-mvp` — workflow schema (`NodeType`), executor dispatch, `fuzzy_action` agent, action set, `node_*` event shape.
- `auto-agent-platform` — `runtime-llm-config`'s `get_adk_model_cached()` (vision primitives use the active LLM), `RunEvent` table for new step events.
- `self-healing-selectors` — the screenshot + accessibility-snapshot perception code is the foundation the vision primitives generalise.

No hard dependency on other in-flight changes.

## Why

`auto-agent` is **selector-first**: `click` / `fill` nodes require a CSS/text selector, and the only AI-driven primitive is the catch-all `fuzzy_action` node. Skyvern's defining property is the opposite — every interaction is **vision-first**: the agent looks at a screenshot plus the accessibility tree, reasons about the page, and acts toward a *goal* with no author-supplied selector. Sites can be redesigned and the automation keeps working.

To "做到和 Skyvern 一样" we must promote vision from a single escape-hatch node to a **first-class action mode**. This change introduces three vision-driven node types that mirror Skyvern's `navigation`, `action`, and `extraction` blocks, backed by a shared perception layer. Selectors become an *optional optimisation*, not a requirement.

## What Changes

- **New node types** on the `NodeType` literal:
  - `vision_navigate`: AI-goal-guided navigation. Params `{goal: str, max_steps?: int, success_criteria?: str}`. The agent loops (observe → decide → act) toward `goal`, calling vision tools, until it judges the goal met or hits `max_steps`.
  - `vision_act`: a single AI-decided action on the current page. Params `{instruction: str}` (e.g. "click the 'Add to cart' button"). One observe→act step.
  - `vision_extract`: structured data extraction. Params `{instruction: str, schema?: JSONSchema}`. Returns data validated against `schema` when supplied, else free-form JSON.
- **Shared perception layer** `app/services/perception.py`: captures a viewport screenshot + `page.accessibility.snapshot()`, builds an **indexed element map** (numbered interactive elements, à la browser-use / Skyvern), and packages a compact observation for the LLM.
- **Vision tool surface** for the ADK agent: `click_element(index)`, `type_text(index, text)`, `select_option(index, value)`, `scroll(direction)`, `go_back()`, `wait(ms)`, `extract(schema)`, `done(success, summary)`. Each tool emits a `node_progress` sub-step event with the chosen element + rationale.
- **Generalise `fuzzy_action`**: `fuzzy_action` becomes a thin alias of `vision_navigate` (same agent, same tools) for backward compatibility; existing workflows keep working. The 3-step keyless stub is preserved for demo mode.
- **Per-step events**: each vision step emits `vision_step` (`step_index`, `thought`, `action`, `target_index`, `screenshot_ref`) so the run is fully observable (consumed by `run-artifacts-observability`).
- **Planner / editor prompts**: documented to prefer vision primitives over brittle selectors; one example each.

## Capabilities

### New Capabilities

- `vision-perception`: the screenshot + accessibility-tree capture, the indexed interactive-element map, and the compact observation payload handed to the agent.
- `vision-action-primitives`: the `vision_navigate` / `vision_act` / `vision_extract` node types, the bounded observe-decide-act loop, the vision tool surface, the `vision_step` event, and schema-validated extraction.

### Modified Capabilities

- `workflow-schema` (from `auto-agent-mvp`): `NodeType` grows by three literals; per-type params/output models added.
- `hybrid-executor` (from `auto-agent-mvp`): dispatch routes the three vision node types to the perception+agent loop.
- `fuzzy-action-agent` (from `auto-agent-mvp`): re-homed as the engine behind `vision_navigate`; `fuzzy_action` becomes an alias. Tool surface widens from the demo stub to the full vision toolset.
- `nl-workflow-planner` (from `auto-agent-mvp`): system prompt prefers vision primitives; selectors become optional hints.

## Impact

- **Backend**: new `app/services/perception.py` (~200 LOC), new `app/agents/vision.py` (or extension of `fuzzy.py`), vision tool functions in `app/tools/`. Executor dispatch additions. Schema literal + per-type models. Tests: perception map determinism, extraction-schema validation, bounded-loop termination.
- **Frontend**: NodeInspector renders the three new types (goal / instruction / schema editors). Canvas icon mapping. RunLog renders `vision_step` rows with thumbnail + thought + action.
- **Runtime**: each vision step is one (vision) LLM call. Cost scales with `max_steps`; the bound is the operator's circuit breaker. Screenshots are produced per step (consumed by the artifacts change).
- **Out of scope**: caching the resolved action plan to skip the LLM on re-runs (→ `selector-cache-learning`); CAPTCHA handling (→ `captcha-antibot-proxy`); the autonomous "give a URL + goal, no graph" top-level mode beyond a single `vision_navigate` node (a future `autonomous-task-mode` can wrap a one-node workflow).
