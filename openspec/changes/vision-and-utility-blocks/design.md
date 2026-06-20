## Context

`expanded-node-library` set the pattern: discriminated per-type params/output models, one module per type under `app/nodes/<type>.py`, security boundaries declared per node. This change appends the remaining Skyvern-parity blocks following that exact pattern, plus integrates with `vision-action-mode` (for selector-less file find) and `run-artifacts-observability` (for `print_page`/`file_download` outputs).

## Goals / Non-Goals

**Goals:**
- One-to-one node coverage of Skyvern's remaining common blocks.
- Reuse existing patterns: discriminator, sandbox, inline sub-executor, artifact store, operator whitelist.

**Non-Goals:**
- `code` node (security).
- Cloud storage (`*_to_s3`) — local-disk POC scope.
- Office/Excel parsing beyond CSV/JSON.

## Decisions

### Decision 1: `validation` reuses the `condition` operator whitelist
The typed predicate evaluator from `expanded-node-library`'s extended `condition` is shared; `validation` adds the assert + control-flow semantics (`fail_run`/`continue`/`on_error` edge) on top.
- **Why**: one predicate evaluator, two surfaces; composes cleanly with `node-error-handling` edges.

### Decision 2: `while_loop` reuses the `foreach` inline sub-executor
Same one-node-deep body execution, but the stop condition is a predicate re-evaluated each iteration, with a hard `max_iterations` ceiling.
- **Why**: identical execution machinery; the only difference is the loop guard. Hard ceiling prevents runaway loops.

### Decision 3: `text_prompt` is browserless and uses the active LLM
No page interaction; one `get_adk_model_cached()` call; optional `schema` validation (one repair retry, mirroring `vision_extract`).
- **Why**: Skyvern's `text_prompt` is a pure LLM step for transforming/deciding over prior outputs; aligning the schema-repair behaviour with `vision_extract` keeps the codebase consistent.

### Decision 4: `goto_url` stays deterministic, distinct from `vision_navigate`
`page.goto(url, wait_until)` only — no agent.
- **Why**: when the author knows the URL, an LLM loop is waste. Keeps the cheap path cheap; mirrors Skyvern separating `goto_url` from `navigation`.

### Decision 5: File nodes go through the sandbox + artifact store
`file_upload` resolves its source from the sandbox dir or a `file`-typed parameter; `file_download`/`print_page` write to the artifact store (or temp when artifacts change absent).
- **Why**: reuse `expanded-node-library`'s `app/tools/sandbox.py` path checks; reuse `run-artifacts-observability` for durable outputs.

### Decision 6: Selector-optional file find via vision
`file_upload`/`file_download` accept an optional selector; without one, a short bounded vision sub-flow locates the input/trigger.
- **Why**: parity with the vision-first identity; deterministic when the author supplies a selector.

## Risks / Trade-offs

- [`while_loop` runaway] → `max_iterations` default 100, hard ceiling 1000; each iteration emits an event.
- [`print_page` needs Chromium PDF] → `page.pdf()` requires headless/`--headless=new`; in headed mode, fall back to print-to-PDF via CDP `Page.printToPDF`. Documented.
- [`file_upload` path escape] → sandbox path checks reject traversal outside the workspace dir.
- [`text_prompt` cost] → one call per node; bounded; `cost_hint` emitted for `run-cost-tracking`.

## Migration Plan

- Additive node types + new `app/nodes/` modules; no DB migration.
- New event literals (`while_iteration_*`, `validation_failed`).
- File outputs route through the artifact store when present, else temp files with a degradation note.

## Open Questions

- Should `validation` support a soft "warn" mode that records but never fails/branches? (Lean: yes as `on_error="continue"` with a `passed:false` output; no new mode.)
- `file_upload` from a URL (download-then-upload) — compose `file_download` + `file_upload`, or a combined node? (Lean: compose; no combined node.)
