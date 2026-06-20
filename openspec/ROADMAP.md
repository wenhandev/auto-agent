# Auto-Agent Roadmap

This roadmap tracks iterations on top of the three shipped changes (`auto-agent-mvp`, `auto-agent-platform`, `per-workflow-credentials`). Each iteration is a single OpenSpec change folder under `openspec/changes/` and is sized to land as one reviewable PR.

**Last housekeeping:** 2026-06-15 — backend **516 tests passing** (`backend/.venv/bin/python -m pytest -q`), frontend **`npm run build` clean**. **35/35** OpenSpec changes pass `openspec validate`. All waves below are **implementation-complete** (backend + core frontend); remaining work is polish, SDK/docs, and manual verification.

## Completion snapshot

| Wave | Status |
| --- | --- |
| **Platform #1–6** (original roadmap) | **Complete** — triggers, context vars, error handling, approvals, expanded nodes, self-healing all land in pytest + core UI |
| **Skyvern parity** (18 changes) | **Complete** — tiers 1–6 backend solid; tier-specific UI polish deferred (see gaps) |
| **n8n engine** (Phase 0–2, 8 changes) | **Complete** — items model, expressions, DAG scheduler, transform nodes, integrations, poll/app triggers, autonomous loop all in pytest |

**Fully complete (tasks 100%):** `browser-sessions-profiles`, `browser-livestream`, `public-api-and-auth`, `outbound-webhooks-hmac`, `record-and-generate`.

**OpenSpec validate:** **35/35** changes pass `openspec validate`.

## Recommended order (all shipped)

The six original platform iterations and all follow-on waves have landed. Order below is historical reference only.

| # | Change id | Status |
| --- | --- | --- |
| 1 | `triggers-and-scheduling` | **Done** — cron/webhook backend + triggers UI; run-list `triggered_by` pills deferred |
| 2 | `node-context-variables` | **Done** — backend + inspector tab |
| 3 | `node-error-handling` | **Done** — backend + canvas on_error edges + status pills; RunLog retry nesting deferred |
| 4 | `human-in-the-loop` | **Done** — backend + ApprovalBanner + run-list pills; replay compression deferred |
| 5 | `expanded-node-library` | **Done** — backend actions; per-type inspector forms deferred |
| 6 | `self-healing-selectors` | **Done** — backend + Settings toggles; adopt-selector button + per-node `auto_heal` deferred |

## Skyvern parity wave (complete — see `SKYVERN_PARITY.md`)

All 18 parity changes are implemented at the backend layer with core frontend surfaces. Coverage matrix and build order live in `openspec/SKYVERN_PARITY.md`.

| Tier | Changes | Status |
| --- | --- | --- |
| 1 — core identity | `vision-action-mode`, `browser-sessions-profiles`, `browser-livestream`, `run-artifacts-observability` | **Complete** |
| 2 — auth & secrets | `totp-2fa-automation`, `login-block`, `credential-backends-strategy` | **Complete** (external vault adapters + typed credential UI deferred) |
| 3 — programmatic surface | `public-api-and-auth`, `sdk-and-mcp`, `outbound-webhooks-hmac` | **Complete** (CLI/TS SDK deferred) |
| 4 — workflow expressiveness | `workflow-input-parameters`, `vision-and-utility-blocks` | **Complete** (declare-tab + utility-node inspector deferred) |
| 5 — scale & robustness | `concurrent-runs-browser-pool`, `captcha-antibot-proxy`, `run-cost-tracking`, `selector-cache-learning` | **Complete** (cost/cache/captcha/proxy UIs deferred) |
| 6 — collaboration & advanced | `multi-user-orgs`, `record-and-generate` | **Complete** (org switcher + visibility UI deferred) |

## n8n-level engine wave (complete)

All eight changes validate clean and are implemented under `openspec/changes/`.

| Phase | Change id | Status |
| --- | --- | --- |
| 0 — data/flow foundation | `items-data-model`, `expression-engine`, `dag-executor-merge` | **Complete** |
| 1 — node families | `data-transform-nodes`, `integration-node-framework`, `core-app-integrations` | **Complete** |
| 2 — entry points & autonomy | `polling-and-app-triggers`, `autonomous-task-mode` | **Complete** |

Build order rationale lives in the unified plan `n8n-level_nodes`.

## Truly remaining gaps

These are the only meaningful work left — everything else in `tasks.md` is manual `[verification]`, README, or smoke-check items.

### Frontend polish

1. **Run history & triggers** — `triggered_by` kind pills (manual/cron/webhook/poll/app); poll/app source summary on hover
2. **RunLog / replay** — nested `node_retry` rows with chevron collapse; compress retry/approval waits in replay; self-heal wand rows + "采用新选择器" adopt button
3. **Inspector forms** — `http_request` / `foreach` / `subworkflow` / `login` / vision / utility blocks; switch/merge params; per-node `auto_heal` toggle; workflow parameters declare tab
4. **Expression UX** — `fx` chip on `{{= }}` token fields (preview endpoint exists; field-level chip mode deferred)
5. **Integration UX** — typed credential forms, OAuth2 "Connect" flow, app icon map in planner
6. **Cost & cache surfaces** — run-list cost column, selector-cache panel, captcha/proxy settings section, concurrency queue position

### Backend / SDK / infra

7. **`sdk-and-mcp`** — CLI entry points, SDK READMEs, example scripts
8. **`credential-backends-strategy`** — Bitwarden/1Password/Azure Key Vault adapters + settings mount UI
9. **`run-artifacts-observability`** — HAR/download capture, recording mux, timeline player
10. **`auto-agent-platform`** — dedicated unit tests for patch/credentials/crypto/llm_settings services

### Docs & verification

11. **README updates** — platform, triggers, error handling, approvals, self-healing sections across changes
12. **Manual verification** — `[verification]` blocks in each `tasks.md` (not automated)

## Features explicitly deferred (future changes)

- Outbound notifications (email/Slack on run transitions)
- Selector cache learning UI (backend cache exists)
- Cron calendar exclusions
- Database query / OS command nodes
- Multi-approver workflows and approval timeouts
- Distributed scheduler (Redis-backed)
- Workflow version revert UI

## Effort tags

- **S**: ~5 days, single sibling worker.
- **M**: ~5–10 days, 2 sibling workers reasonable (typically backend + frontend).
- **L**: ~10–15 days, 3 sibling workers reasonable (backend + frontend + spec/QA scaffolding).
