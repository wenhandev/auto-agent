## 1. Schema & dispatch

- [x] 1.1 Add `validation`, `text_prompt`, `while_loop`, `print_page`, `file_upload`, `file_download`, `goto_url` to `NodeType`
- [x] 1.2 Per-type params/output models via the existing discriminator
- [x] 1.3 One module per type under `app/nodes/<type>.py`

## 2. Validation & prompt

- [x] 2.1 `validation` reusing the `condition` operator whitelist + control-flow (`fail_run`/`continue`/`on_error` edge)
- [x] 2.2 `text_prompt` browserless LLM call via `get_adk_model_cached()` + optional schema (one repair retry)
- [x] 2.3 Emit `validation_failed` event

## 3. Loop & navigation

- [x] 3.1 `while_loop` reusing the `foreach` inline sub-executor; `max_iterations` + hard ceiling 1000
- [x] 3.2 `while_iteration_started/completed` events
- [x] 3.3 `goto_url` deterministic `page.goto`

## 4. File transfer

- [x] 4.1 `print_page` via `page.pdf()` / CDP `printToPDF`; store as artifact
- [x] 4.2 `file_upload` from sandbox / `file` param; selector-or-vision input find; sandbox path checks
- [x] 4.3 `file_download` capture as `download` artifact; selector-or-vision trigger

## 5. Prompts & frontend

- [ ] 5.1 Planner + editor catalogue entries (params/output/example) for the 7 nodes
- [ ] 5.2 NodeInspector forms + canvas icons for the 7 nodes
- [ ] 5.3 RunLog: validation pass/fail, text_prompt output, file outputs

## 6. Tests

- [x] 6.1 validation control-flow (fail_run/continue/branch)
- [x] 6.2 while_loop cap + iteration events
- [x] 6.3 text_prompt schema repair
- [x] 6.4 file_upload sandbox traversal rejection; file_download artifact capture; print_page PDF
