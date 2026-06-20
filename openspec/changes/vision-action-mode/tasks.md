## 1. Schema & settings

- [x] 1.1 Add `vision_navigate`, `vision_act`, `vision_extract` to the `NodeType` literal in `app/schemas.py`
- [x] 1.2 Add per-type params models (`VisionNavigateParams`, `VisionActParams`, `VisionExtractParams`) with pydantic validation
- [x] 1.3 Add `VISION_MAX_STEPS` (default 8) to `app/settings.py` and `.env.example`
- [x] 1.4 Map deserialised `fuzzy_action` nodes to the `vision_navigate` dispatch path

## 2. Perception layer

- [x] 2.1 Create `app/services/perception.py`: capture screenshot + `page.accessibility.snapshot()`
- [x] 2.2 Build the indexed interactive-element map (index, role, name, handle signature)
- [x] 2.3 Implement index→handle resolution with a11y-signature re-resolve and single re-perceive on miss
- [x] 2.4 Build the compact, token-bounded observation payload
- [x] 2.5 Unit tests: map numbering determinism, blank-page case, re-resolve after mutation

## 3. Vision agent & tools

- [x] 3.1 Create `app/agents/vision.py` (ADK `LlmAgent` via `get_adk_model_cached()`) with the system prompt
- [x] 3.2 Implement the vision tool surface (`click_element`, `type_text`, `select_option`, `scroll`, `go_back`, `wait`, `extract`, `done`)
- [x] 3.3 Implement the bounded observe-decide-act loop with `max_steps` and the non-crashing `max_steps_reached` contract
- [x] 3.4 Implement `extract(schema)` with JSON-Schema validation + one repair retry
- [x] 3.5 Preserve the keyless 3-step demo stub behind a no-key check

## 4. Executor integration

- [x] 4.1 Route `vision_navigate` / `vision_act` / `vision_extract` in the executor dispatch
- [x] 4.2 `vision_act` caps the loop at one action; `vision_extract` runs perception once
- [x] 4.3 Emit `vision_step` events per step with `screenshot_ref`
- [x] 4.4 Add `vision_step` to the `RunEvent` event-type literal and persist it
- [x] 4.5 Integration test: a 2-step vision_navigate against a local fixture page

## 5. Prompts

- [x] 5.1 Update the planner system prompt to prefer vision primitives; selectors optional
- [x] 5.2 Update the chat editor system prompt with one example per new node type

## 6. Frontend

- [ ] 6.1 NodeInspector forms for the three new node types (goal / instruction / schema editor)
- [ ] 6.2 Canvas icon mapping for the three types on `GlowNode`
- [ ] 6.3 RunLog renders `vision_step` rows (thumbnail + thought + action)
- [ ] 6.4 API client: surface `screenshot_ref` resolution for step thumbnails
