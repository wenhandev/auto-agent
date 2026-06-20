## depends_on

- `auto-agent-mvp` — `NodeType` literal, executor dispatch, condition/edge semantics.
- `expanded-node-library` — the discriminated per-type params/output pattern, `app/nodes/<type>.py` layout, `http_request`/file/parse nodes, `foreach`/`subworkflow`.
- `vision-action-mode` — `file_download` and goal-driven blocks lean on the vision agent/perception.
- `node-context-variables` (soft) — `text_prompt` output and `validation` results feed downstream via `{{nodes...}}`.

No dependency on triggers/HITL/self-healing.

## Why

`expanded-node-library` added the non-browser staples (`http_request`, file I/O, email, parse, `foreach`, `subworkflow`). Comparing against Skyvern's **17+ block types**, several high-value blocks are still missing: `validation` (assert + control flow), `text_prompt` (LLM call, no browser), `while_loop`, `print_page` (page→PDF), `file_upload`, `file_download` (browser-driven), and `goto_url` (a thin deterministic navigate). This change closes the block-catalogue gap so any Skyvern workflow has a one-to-one node here.

## What Changes

- **New node types** on the `NodeType` literal:
  - `validation`: assert a typed predicate (reuses the `condition` operator whitelist) over context variables; on failure either `fail_run`, `continue`, or follow an `on_error` edge (composes with `node-error-handling`). Output `{passed: bool, checked, reason?}`. Skyvern's `validation` block analog.
  - `text_prompt`: a text-only LLM call (no browser). Params `{prompt, schema?, system?}`; uses `get_adk_model_cached()`; output is the model text or schema-validated JSON. Skyvern's `text_prompt` block.
  - `while_loop`: repeat a one-node-deep body while a typed predicate holds, capped at `max_iterations` (default 100, hard ceiling 1000). Complements `foreach` (count-bounded vs. condition-bounded).
  - `print_page`: render the current page to a PDF, stored as a `download`/`print` artifact (via `run-artifacts-observability` when present, else a temp file). Skyvern's `print_page`.
  - `file_upload`: upload a file to a page file input. Params `{target?, file: path|{{params...}}|artifact_ref}`; resolves the file from the sandboxed workspace or a workflow `file`-typed parameter; uses the vision agent to find the input when no selector is given.
  - `file_download`: trigger and capture a browser download as a `download` artifact (deterministic selector or vision-driven), returning `{filename, artifact_id, bytes}`.
  - `goto_url`: deterministic direct navigation (`page.goto(url)`), distinct from goal-driven `vision_navigate`. Skyvern's `goto_url`.
- **Per-type params/output models** registered through the existing discriminator; one module per type under `app/nodes/<type>.py` (the layout `expanded-node-library` mandated to avoid a monolith).
- **Editor/planner prompts**: extended catalogue entries (params + output + one example each).
- **UI**: NodeInspector type-specific forms; canvas icons; RunLog rendering for `validation` pass/fail and `text_prompt` output.

## Capabilities

### New Capabilities

- `validation-and-prompt-nodes`: `validation` (assert + control flow) and `text_prompt` (browserless LLM call, optional schema).
- `loop-and-navigation-nodes`: `while_loop` (condition-bounded), `goto_url` (deterministic navigate).
- `file-transfer-nodes`: `print_page` (page→PDF), `file_upload`, `file_download`, integrated with the artifact store and the sandbox.

### Modified Capabilities

- `workflow-schema` (from `auto-agent-mvp`): `NodeType` grows by seven literals.
- `hybrid-executor` (from `auto-agent-mvp`): dispatch table grows; `while_loop` reuses the inline sub-executor pattern from `foreach`.
- `non-browser-action-nodes` / `composite-flow-nodes` (from `expanded-node-library`): the catalogue and the `app/nodes/` layout grow with the new modules.
- `run-history` (from `auto-agent-platform`): new event entries (`while_iteration_started/completed`, `validation_failed`); `print_page`/`file_download` produce artifacts.
- `chat-authoring` / `nl-workflow-planner`: prompts grow by the new catalogue entries.

## Impact

- **Backend**: 7 new node modules under `app/nodes/` (~30–120 LOC each), executor dispatch additions, sandbox reuse for file paths, artifact integration for `print_page`/`file_download`. New event-type literals. Tests per node + a `while_loop` cap test + a `validation` control-flow test.
- **Frontend**: 7 per-type forms, 7 icons, RunLog variants. ~500 LOC.
- **Runtime**: `text_prompt` is one LLM call; `print_page` uses `page.pdf()` (Chromium headless or `--headless=new`); `while_loop` is bounded; file nodes are cheap. `file_upload`/`file_download` vision-find adds a short bounded vision sub-flow when no selector.
- **Migration**: additive node types; no DB migration. File paths confined to the existing sandbox dir.
- **Out of scope**: `code` node (Python `exec` — refused on the same security grounds as `expanded-node-library`); `download_to_s3` / `upload_to_s3` / cloud storage (separate `cloud-storage-nodes` change — object storage is out of the local POC scope, mirroring `run-artifacts-observability`'s local-disk-only stance); `file_url_parser` for Excel beyond what `parse_csv`/`parse_json` cover (Excel parsing is a future `office-doc-parsing` change).
