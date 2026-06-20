## Context

auto_agent targets B2B browser automation with two authoring modes:

1. **Deterministic workflows** — DAG nodes (`click`, `fill`, `navigate`) with explicit Playwright selectors executed by `executor.py`.
2. **Autonomous tasks** — LLM-driven loop using indexed a11y elements and short-lived refs from `perception.py`.

The platform already provides:

- Live **browser sessions** (`browser_sessions.py`) with 24h TTL and run attachment.
- **Self-healing selectors** (`selector_finder.py`) — LLM proposes replacement selectors on miss (reactive, not visual pick).
- **Recording** (`recording.py`) — passive DOM event capture with basic `#id` selectors.
- **Workflow editor** (`NodeParamsEditor.tsx`) — manual selector text field for `click` / `fill`.
- **Live stream** (`LiveStreamPanel.tsx`) — JPEG frames over WebSocket during runs (run-scoped, not session-scoped).

What is missing is the proactive **UI Selector** common in UiPath, 影刀, Power Automate Desktop: point at an element, get a stable locator, paste into workflow.

User chose **Option D**: Phase 1 in workflow editor first; expand to standalone debug and recording later.

## Goals / Non-Goals

**Goals:**

- Phase 1: Authors can pick elements for `click` / `fill` nodes without writing selectors by hand.
- Phase 2: RPA-like in-page hover highlight and click-to-select experience.
- Phase 3: Power-user observe overlay, standalone debug tool, recording integration.
- Shared `selector_builder` used across all phases and reusable by recording/self-heal adoption flows.
- Picker operates on live browser sessions already in the product.

**Non-Goals:**

- Replacing autonomous agent perception or ref-based targeting.
- Automatic workflow mutation without user confirmation (aligns with self-heal adopt-via-chat pattern).
- Cross-origin iframe deep picking in Phase 1 (best-effort only).
- Shadow DOM / canvas-only elements in Phase 1 (Computer Use fallback remains separate).
- Selector cache UI (deferred per ROADMAP; picker may write node params only).

## Decisions

### D1: Three-phase delivery

| Phase | UX | Backend | Rationale |
|-------|-----|---------|-----------|
| **1** | Screenshot + click coordinates in modal | `POST pick-element {x,y}` + `selector_builder` | Fastest path to value; no script injection |
| **2** | In-page hover highlight + click | Inject/uninject picker script via `page.add_init_script` or `evaluate` | Authentic RPA feel; avoids coordinate scaling bugs |
| **3** | Observe list/overlay + debug page + recording | `bounding_box()` per element, new route, recording hook | Parity with agent perception; closes recording gap |

### D2: Browser session as picker host

Picker runs against **live browser sessions**, not ephemeral run contexts.

- User selects or creates a session in the picker dialog.
- Optional URL navigation before picking.
- **Picker lock**: while picker modal is open, session is locked (`picker_attached` flag, distinct from `attached_run_id`). Runs attempting to attach receive HTTP 409.

Alternative considered: attach picker to an active run's live stream. Rejected for Phase 1 — runs are transient and complicate editing workflows offline from execution.

### D3: Selector candidate ranking (`selector_builder`)

Generate 1–5 candidates per element, ordered by stability:

1. `#id` (if unique on page)
2. `[data-testid="..."]`
3. `[name="..."]` for form controls
4. `[aria-label="..."]`
5. Playwright text selector hint (`text="..."`) stored as metadata; executor uses `page.get_by_text` when node param prefix is `text=`
6. Short CSS path (tag + limited attribute chain, max depth 4, skip generated class hashes)

Each candidate includes: `selector`, `strategy`, `confidence` (1.0 for id/testid, lower for path), `match_count` from `page.locator(selector).count()`.

Alternative considered: LLM-generated selectors only. Rejected — slow, costly, non-deterministic; LLM remains in self-heal path.

### D4: Phase 1 screenshot transport

Use **polling `GET /screenshot`** (JPEG + viewport `{width, height}`) every 1–2s while picker dialog is open.

Alternative considered: WebSocket session stream. Deferred — requires new WS route; screenshot polling sufficient for MVP.

Frontend maps click coordinates: `viewportX = (clickX / displayedWidth) * viewport.width`.

### D5: Phase 2 injected picker script

Inject a namespaced IIFE (`window.__autoAgentPicker`) that:

- On `mouseover`: outlines element with colored border + tooltip (tag, id, role).
- On `click` (capture phase): `preventDefault` + `stopPropagation`, posts element descriptor to backend via polling endpoint or stores in `window.__autoAgentPicker.lastPick`.
- Backend reads pick result, runs `selector_builder`, returns candidates.

Script MUST be removed on picker disable / dialog close to avoid polluting customer sites.

### D6: Phase 3 observe overlay

Extend `perceive()` or add `observe_with_boxes()`:

- For each interactive element in observation, call `locator.bounding_box()` (skip if null/offscreen).
- Return `{ index, role, name, ref, box: {x,y,w,h} }` relative to viewport.
- Frontend draws SVG overlay on screenshot; click box → same pick flow as coordinate pick.

Standalone **Selector Debug** page (`/selector-debug`): session picker + URL bar + full-height picker panel + selector test console. Not embedded in workflow editor.

Recording integration: on `click`/`fill` capture, if `#id` absent, call `selector_builder` on target element and store `selector_candidates[]` in event payload.

### D7: Frontend integration point

Phase 1: `NodeParamsEditor.tsx` — add **Pick Element** button adjacent to `selector` field for `click` and `fill` node types only.

Phase 3: `RecordingDetailPage.tsx` — "Use as selector" action on events with candidates.

### D8: Test selector endpoint

`POST /test-selector { selector }` returns `{ match_count, preview: { tag, text, role } }` using first match. Shown in picker UI before confirm.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Coordinate mapping errors (Phase 1) | Show viewport dimensions; snap pick to nearest interactive element within 8px radius |
| Picker lock vs run attachment race | Atomic lock in `browser_sessions` under `_lock`; clear error messages |
| Injected script breaks target page | Namespaced, removed on exit; no global overrides except during active pick |
| Non-unique selectors | Show `match_count` in UI; warn when > 1 |
| Session on different backend instance after restart | Sessions invalidated on restart (existing behaviour); picker shows "session expired" |
| iframe content | Phase 1: pick in main frame only; Phase 2+: document limitation |

## Migration Plan

1. Deploy backend APIs (backward compatible — new routes only).
2. Deploy frontend Phase 1 behind no flag (additive UI).
3. Phase 2/3 ship incrementally; no migration required for existing workflows.
4. Rollback: hide Pick Element button via frontend; disable picker routes (return 503) if needed.

## Open Questions

- Should picked selectors optionally write to `SelectorCache` for the workflow node? (Defer to post-Phase 1.)
- Phase 2: use CDP screencast for session (reuse `livestream.py`) vs screenshot polling? (Evaluate during Phase 2 implementation.)
- i18n for picker UI: follow existing `react-i18next` keys under `elementPicker.*`.
