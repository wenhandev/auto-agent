# Auto-Agent Roadmap

This roadmap tracks the next six iterations on top of the three shipped changes (`auto-agent-mvp`, `auto-agent-platform`, `per-workflow-credentials`). Each iteration is a single OpenSpec change folder under `openspec/changes/` and is sized to land as one reviewable PR.

## Recommended order

The order below is recommended (not enforced). Numbers 1, 2, and 6 are fully independent of each other and can ship in any order. Numbers 3, 4, and 5 each pick up at least one earlier change and benefit from landing after it.

| # | Change id | One-line description | Depends on | Effort |
| --- | --- | --- | --- | --- |
| 1 | `triggers-and-scheduling` | Cron and webhook triggers that enqueue runs through the existing run queue. | `auto-agent-platform` (Run table, queue, lifespan). | M |
| 2 | `node-context-variables` | `{{nodes.<id>.output[.path]}}` interpolation so later nodes can reference earlier ones. | `auto-agent-platform` (executor, credential interpolation). | M |
| 3 | `node-error-handling` | Per-node retry, on-error branch edges, configurable failure policy. | `auto-agent-platform`; soft-uses `node-context-variables` for `{{nodes.<id>.error}}` references. | M |
| 4 | `human-in-the-loop` | New `approval` node type that pauses a run and waits for a UI decision. | `auto-agent-platform`; `node-context-variables` for `{{nodes.<approval>.output.inputs.X}}`. | M |
| 5 | `expanded-node-library` | Non-browser node types: `http_request`, file I/O, email, JSON/CSV parsing, `foreach`, `subworkflow`. | `auto-agent-platform`; `node-context-variables` (iteration variables, response bodies); complements `node-error-handling`. | L |
| 6 | `self-healing-selectors` | Vision-based recovery when `click`/`fill` selectors miss. | `auto-agent-platform` (executor, `runtime-llm-config` for the heal model). | M |

## Parallelisation guidance

- 1, 2, 6 can be picked up by three independent worker streams without coordination.
- 3 should ideally land after 2 so the on-error branch examples can reference `{{nodes.<id>.error.message}}`. Implementable without 2 by using a literal `error` field exposed on the node-level inspector.
- 4 should land after 2 so the approval node's collected inputs are available through the canonical `{{nodes.<id>.output...}}` pathway.
- 5 sits at the bottom because it expands the node catalogue and the most interesting new nodes (`http_request`, `parse_json`, `foreach`) are dramatically more useful once both 2 (context vars) and 3 (error handling, retries) exist.

## Features explicitly deferred

These came up while scoping the six changes above and are intentionally NOT iteration #7. Each is a candidate for a future change:

- **Outbound notifications** (email / Slack / generic webhook on run state transitions and approval requests). Surfaces as a hook point inside #4. A dedicated `notifications` change should consume that hook and add an `event_bus` table plus per-workflow subscription config.
- **Selector cache learning** — persist self-healed selectors per workflow + page URL so the second run skips the vision call. Mentioned as future work inside #5.
- **Cron calendar exclusions** (skip holidays, business-hours windows). Mentioned in #1.
- **Database query node** (`sql` against a configured datasource). Mentioned in #6 out-of-scope.
- **OS command execution node** (`shell` / `run_process`). Mentioned in #6 out-of-scope; security boundary issues.
- **Multi-approver workflows** and **approval timeouts**. Mentioned in #4 out-of-scope.
- **Distributed scheduler** (Redis-backed APScheduler, multi-process). Mentioned in #1 out-of-scope.
- **Run cost tracking surface**. #5 logs heal-cost intent; a future "run cost" change is needed to render it.
- **Workflow version revert UI** — the platform change already added the read endpoint; the UI is deferred.

## Effort tags

- **S**: ~5 days, single sibling worker.
- **M**: ~5–10 days, 2 sibling workers reasonable (typically backend + frontend).
- **L**: ~10–15 days, 3 sibling workers reasonable (backend + frontend + spec/QA scaffolding).
