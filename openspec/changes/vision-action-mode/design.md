## Context

The MVP executor dispatches deterministic nodes (`navigate`, `click`, `fill`, `extract`, `wait`) to Playwright actions keyed on author-supplied selectors, and routes the single `fuzzy_action` node to an ADK `LlmAgent` with a small Playwright tool set. `self-healing-selectors` already proved the perception ingredients work: `page.screenshot()` + `page.accessibility.snapshot()` feed an LLM that proposes selectors.

Skyvern's model is structurally different: there are no author selectors in the hot path. The agent receives an annotated screenshot + a flattened, **indexed** list of interactive elements and chooses an element by index. This change adopts that model as a first-class mode while keeping the deterministic selector path intact for speed and determinism where the author wants it.

## Goals / Non-Goals

**Goals:**
- Three vision primitives (`vision_navigate`, `vision_act`, `vision_extract`) that need no selector.
- A single shared perception layer reused by all three (and reusable by self-heal and future captcha work).
- Full step-level observability (`vision_step` events with screenshot refs and the agent's thought/action).
- Backward compatibility: existing `fuzzy_action`, `click`, `fill` workflows behave unchanged.

**Non-Goals:**
- Action-plan / selector caching across runs (separate `selector-cache-learning`).
- A top-level "no workflow graph" autonomous mode (a one-node `vision_navigate` workflow approximates it; full mode is future).
- CAPTCHA / anti-bot handling.

## Decisions

### Decision 1: Indexed element map, not raw coordinates
The perception layer numbers interactive elements (`[0] button "Add to cart"`, `[1] input[type=email]`, …) from the accessibility tree, cross-referenced with bounding boxes from the DOM, and overlays the indices on the screenshot. The agent acts by index (`click_element(3)`), which the executor resolves to a concrete element handle.
- **Why**: index-based action is the consensus pattern (browser-use `dom/` indexing, Skyvern's element annotation). It is far more reliable than asking the LLM for pixel coordinates and cheaper than asking for a full selector each step.
- **Alternative rejected**: pixel-coordinate clicks (brittle across viewport sizes); full-selector-per-step (token-heavy, the self-heal pattern, kept only for healing).

### Decision 2: One agent, three entry shapes
`vision_navigate` runs the full observe→decide→act loop until `done`. `vision_act` is the same loop hard-capped at one action. `vision_extract` runs perception once then a single `extract(schema)` tool call. All three share `app/agents/vision.py`.
- **Why**: one tool surface, one prompt family, one place to evolve. Skyvern's `action` / `navigation` / `extraction` blocks are likewise the same engine with different stop conditions.

### Decision 3: `fuzzy_action` becomes an alias of `vision_navigate`
Deserialised `fuzzy_action` nodes map to the `vision_navigate` executor path. The keyless 3-step demo stub stays wired so the no-API-key demo still runs.
- **Why**: zero migration; the MVP's escape-hatch node was always "vision navigate" in spirit.

### Decision 4: Schema-validated extraction, schema optional
`vision_extract.params.schema` is a JSON Schema. When present, the agent's `extract` output is validated (one repair retry on failure); when absent, free-form JSON is returned.
- **Why**: matches Skyvern's `data_extraction_schema` and Stagehand's Zod requirement, while staying usable without a schema (n8n-style runtime shape).

### Decision 5: Bounded loop, deterministic budget
`vision_navigate.max_steps` defaults to `settings.VISION_MAX_STEPS` (8). Exhausting the budget without `done(success=true)` completes the node with `{completed: false, reason: "max_steps_reached", last_observation}` — the same non-crashing contract `fuzzy_action` already uses.

### Decision 6: Per-step screenshot refs, not inline blobs
Each `vision_step` event carries a `screenshot_ref` (a storage key), not the image bytes, so the event stream stays small. The bytes are written through the artifact store defined by `run-artifacts-observability`; until that change lands, the ref points to an in-memory/temp path and the UI degrades to "screenshot unavailable".

## Risks / Trade-offs

- [Cost: N steps × vision calls] → `max_steps` bound + per-step `cost_hint` in events; `run-cost-tracking` aggregates later.
- [Index drift: the page mutates between perception and action] → re-resolve the element by its captured a11y signature at action time; on miss, re-perceive once before failing.
- [A11y tree incomplete on canvas/SVG-heavy pages] → screenshot is always included; the agent can `scroll` and re-perceive. Pure-canvas apps remain hard (documented limitation).
- [Determinism regression for users who liked selectors] → deterministic `click`/`fill` selector path is untouched; vision is opt-in per node.

## Migration Plan

- Additive `NodeType` literals; no DB migration (node params live in `WorkflowVersion.workflow_json`).
- `fuzzy_action` alias is handled at dispatch; existing workflows untouched.
- New `settings.VISION_MAX_STEPS` (default 8) read from `.env`.

## Open Questions

- Should `vision_extract` without a schema attempt to *infer* one from the instruction for the variable picker? (Deferred; tie to `node-context-variables` output shapes.)
- Element-index annotation overlay on the screenshot: server-side (Pillow) vs. injected JS highlight before capture? (Lean JS-injection; cheaper, matches browser-use.)
