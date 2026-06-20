## Why

Workflow authors today must hand-write Playwright CSS selectors for `click` and `fill` nodes. Typical RPA tools provide a visual **UI Selector** (point-and-click element picking) that generates stable locators. auto_agent already has browser sessions, perception, self-healing selectors, and a workflow editor — but no interactive picker. Adding UI Selector closes the gap between agent-driven automation and deterministic workflow authoring, and makes customer demos easier to build and maintain.

## What Changes

- **Phase 1 (MVP)**: Add **Pick Element** to the workflow editor for `click` / `fill` nodes — screenshot + coordinate pick on a live browser session, auto-fill selector field, optional test.
- **Phase 2**: Upgrade picker to **in-page hover highlight** mode (UiPath / 影刀 style) injected into the session page, with live screenshot refresh and richer selector candidates.
- **Phase 3**: Add **observe overlay** (element list + bounding boxes), a **standalone Selector Debug** page, and **recording integration** so captured events can adopt picker-generated selectors.
- Introduce a shared **`selector_builder`** module for deterministic DOM → Playwright selector generation (reused by picker, recording, and self-heal).
- Extend **browser session APIs** with navigate, screenshot, pick-element, test-selector, and picker-mode lifecycle endpoints.
- Session **picker lock** so picker and workflow runs cannot operate the same session concurrently.

No breaking changes to existing workflow JSON or executor behaviour.

## Capabilities

### New Capabilities

- `selector-builder`: Deterministic algorithm to generate ranked Playwright selector candidates from a DOM element (id, data-testid, aria-label, role+name, stable CSS path).
- `element-picker-session-api`: HTTP endpoints on `/api/browser-sessions/{id}/` for picker operations (navigate, screenshot, pick at coordinates, test selector, enable/disable picker mode).
- `element-picker-workflow-ui`: Phase 1 frontend — `ElementPickerDialog` in workflow NodeInspector for `click` / `fill` nodes.
- `element-picker-injected-mode`: Phase 2 — inject hover-highlight + click-capture script into session page; return selector on element click without coordinate mapping.
- `element-picker-advanced`: Phase 3 — observe overlay with bounding boxes, standalone Selector Debug page, recording enhancement to emit picker-quality selectors.

### Modified Capabilities

- `browser-sessions`: Add picker lock semantics, navigate/screenshot endpoints, and session exclusivity rules when picker mode is active.
- `action-recording`: Phase 3 — enrich recorded click/fill events with selector candidates from `selector_builder` when available.

## Impact

- **Backend**: `backend/app/services/selector_builder.py` (new), `backend/app/routers/browser_sessions.py`, `backend/app/services/browser_sessions.py`, optional `backend/app/services/element_picker.py`.
- **Frontend**: `NodeParamsEditor.tsx`, new `ElementPickerDialog.tsx`, `api-platform.ts`, types; Phase 3 adds `SelectorDebugPage.tsx` and recording UI hooks.
- **Dependencies**: Reuses Playwright, existing `perception.py`, `browser_primitives.py`, `recording.py`, `selector_finder.py` (LLM heal remains separate).
- **Operations**: Picker uses live browser sessions (same capacity limits as `MAX_LIVE_SESSIONS`).
