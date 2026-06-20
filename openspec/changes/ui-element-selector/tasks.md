# UI Element Selector — Implementation Tasks

Phases align with `design.md`. Complete Phase 1 before starting Phase 2; Phase 3 builds on both.

## Phase 1 — MVP (Workflow Pick Element)

### 1. Selector builder (backend core)

- [x] 1.1 Create `backend/app/services/selector_builder.py` with candidate generation (id, data-testid, name, aria-label, text, css-path)
- [x] 1.2 Implement `element_from_point(page, x, y)` with interactive-ancestor walk
- [x] 1.3 Add unit tests for selector ranking, non-unique id exclusion, and ancestor resolution

### 2. Browser session picker API

- [x] 2.1 Add picker lock fields to in-memory session entry (`picker_token`, `picker_mode`)
- [x] 2.2 Implement `POST /picker/enable` and `POST /picker/disable`
- [x] 2.3 Implement `POST /navigate`, `GET /screenshot`, `POST /pick-element`, `POST /test-selector`
- [x] 2.4 Enforce mutual exclusion: picker lock vs `attached_run_id`
- [x] 2.5 Add API schemas to `schemas_api.py` and router tests

### 3. Workflow editor UI

- [x] 3.1 Add `elementPicker.*` i18n keys (en + zh)
- [x] 3.2 Add API client methods in `api-platform.ts`
- [x] 3.3 Create `ElementPickerDialog.tsx` (session select, URL bar, screenshot, candidates, test, apply)
- [x] 3.4 Add Pick Element button to `NodeParamsEditor.tsx` for `click` / `fill`
- [x] 3.5 Implement coordinate mapping (displayed image size → viewport)
- [x] 3.6 Prefill URL from upstream `navigate` node when available
- [x] 3.7 Wire picker/enable on open and picker/disable on close

### 4. Phase 1 verification

- [x] 4.1 Manual test: pick login button on demo portal → selector applied to click node
- [x] 4.2 Manual test: test-selector shows match_count=1 for picked element
- [x] 4.3 Manual test: workflow run blocked while picker dialog open

---

## Phase 2 — Injected hover picker

### 5. Injected picker script

- [ ] 5.1 Create `backend/app/static/picker/picker.js` (hover outline, tooltip, click capture)
- [ ] 5.2 Extend `picker/enable` to accept `{ "mode": "coordinate" | "injected" }`
- [ ] 5.3 Implement inject on enable and cleanup on disable
- [ ] 5.4 Implement `GET /picker/result` polling endpoint
- [ ] 5.5 Reject injected mode when `BROWSER_HEADLESS=true` (HTTP 422)

### 6. Picker dialog Phase 2 UX

- [ ] 6.1 Add mode toggle: Click on screenshot / Pick in browser
- [ ] 6.2 Poll screenshot + picker/result in injected mode
- [ ] 6.3 Show headed-browser guidance when injected mode unavailable

### 7. Phase 2 verification

- [ ] 7.1 Manual test: injected hover highlight in headed browser
- [ ] 7.2 Manual test: picker script fully removed after disable
- [ ] 7.3 Manual test: coordinate mode still works when headless

---

## Phase 3 — Advanced (observe overlay, debug page, recording)

### 8. Observe with bounding boxes

- [ ] 8.1 Add `observe_elements_with_boxes(page)` using perception walk + `bounding_box()`
- [ ] 8.2 Implement `GET /observe-elements` on browser sessions
- [ ] 8.3 Add pick-by-index path on pick-element (optional `{ "index": number }` from observe list)

### 9. Observe overlay in picker dialog

- [ ] 9.1 Add **Element list** mode to `ElementPickerDialog`
- [ ] 9.2 Render SVG/HTML overlays aligned to bounding boxes
- [ ] 9.3 Sync list selection with overlay selection

### 10. Standalone Selector Debug page

- [ ] 10.1 Add route `/selector-debug` and nav link
- [ ] 10.2 Build `SelectorDebugPage.tsx` (session, URL, overlay, test console, pick history)
- [ ] 10.3 Persist pick history in component state (last 10 picks)

### 11. Recording integration

- [ ] 11.1 Extend recording init script capture to resolve element handle for selector_builder
- [ ] 11.2 Store `selector_candidates` on click/fill events in recording payload
- [ ] 11.3 Add candidate display + Copy selector on `RecordingDetailPage.tsx`
- [ ] 11.4 Add Use in workflow action (chat prefill or node target picker)

### 12. Selector cache optional hook

- [ ] 12.1 Add optional Save to selector cache checkbox on picker Apply (saved workflows only)
- [ ] 12.2 Wire to existing selector cache write API

### 13. Phase 3 verification

- [ ] 13.1 Manual test: observe overlay selects correct invoice Download Summary button
- [ ] 13.2 Manual test: recording event shows selector_candidates
- [ ] 13.3 Manual test: Selector Debug page test console

---

## Documentation

- [ ] 14.1 Add `openspec/changes/ui-element-selector/README.md` or update demo README with Pick Element usage for Acme portal workflow authoring
