# Skyvern Parity — Gap Analysis & New-Change Plan

This document maps **Skyvern's** current (2026) feature set onto `auto-agent`'s existing OpenSpec coverage, names the gaps, and proposes a prioritised set of **new OpenSpec changes** that, once specced and implemented, bring `auto-agent` to functional parity with Skyvern.

It is the planning backbone for the "做到和 Skyvern 一样" effort. Scope of *this* document is spec-only: it identifies what to build and in what order. Each proposed change below becomes its own `openspec/changes/<id>/` folder with full `proposal / design / specs / tasks` artifacts.

Sources for the Skyvern feature surface: [skyvern.com/products](https://www.skyvern.com/products), [Core Concepts](https://docs-new.skyvern.com/docs/developers/getting-started/core-concepts), [Workflow Blocks Reference](https://www.mintlify.com/Skyvern-AI/Skyvern/workflows/workflow-blocks), [docs/skill.md](https://github.com/Skyvern-AI/skyvern/blob/main/docs/skill.md), plus the per-file mapping already recorded in `openspec/REFERENCES.md`.

## How to read the coverage table

- **Covered** — an existing shipped or in-flight change fully addresses the Skyvern capability.
- **Partial** — an existing change touches it but leaves a material gap (named in the Gap column).
- **Gap** — no existing change addresses it; a new change is proposed.

## 1. Capability coverage matrix

| # | Skyvern capability | auto-agent status | Existing change(s) | Gap / new change |
| --- | --- | --- | --- | --- |
| 1 | **Vision-first navigation** — drive pages from screenshot + a11y tree toward a goal, no brittle selectors | Partial | `fuzzy-action-agent`, `self-healing-selectors` | Selector-first by default; no top-level AI-goal `navigate` / single AI `action` primitive → **`vision-action-mode`** |
| 2 | **Autonomous Task mode** — give URL + prompt (+ optional data schema), agent figures out the steps; no predefined graph | Gap | — | **`autonomous-task-mode`** |
| 3 | **Structured data extraction** with JSON schema validation | Partial | `auto-agent-mvp` (`extract` node) | No schema-validated extraction → folded into **`vision-action-mode`** (extraction primitive) |
| 4 | **Persistent browser sessions** (live, ≤24h, shared auth/state across tasks) | Gap | — | **`browser-sessions-profiles`** |
| 5 | **Browser profiles** (saved cookie/storage snapshots, reusable for days/weeks, skip login) | Gap | — | **`browser-sessions-profiles`** |
| 6 | **Livestreaming** the browser viewport in real time | Partial | `live-event-stream` (node-glow only) | No live viewport stream → **`browser-livestream`** |
| 7 | **Run observability** — per-step screenshots, action logs, session recordings, LLM diagnostic traces | Partial | `run-history` (event stream only) | No artifacts (screenshots/recordings/traces/downloads) → **`run-artifacts-observability`** |
| 8 | **TOTP / 2FA automation** — store TOTP secret, auto-generate + auto-fill codes during login | Partial | `human-in-the-loop` (manual approval only) | No automated TOTP → **`totp-2fa-automation`** |
| 9 | **Credit-card credential type** + auto-fill | Gap | `credential-vault` (generic kinds) | No typed card credential → **`totp-2fa-automation`** (card credential type) |
| 10 | **Login block** — authenticate using a stored credential | Gap | — | **`login-block`** |
| 11 | **Credential backends** — native vault + Bitwarden / 1Password / Azure Key Vault / custom HTTP vault | Partial | `credential-vault` (single Fernet) | Single backend → **`credential-backends-strategy`** |
| 12 | **REST API** for every capability + **API-key auth** | Partial | platform routers (no auth) | No stable public API surface + no auth → **`public-api-and-auth`** |
| 13 | **Python / TypeScript SDK + MCP server + CLI** | Gap | — | **`sdk-and-mcp`** |
| 14 | **HMAC-signed outbound webhooks** on completion, with retry + replay | Gap | (`triggers` has inbound only) | **`outbound-webhooks-hmac`** |
| 15 | **Workflow input parameters** — run the same workflow with different typed params | Partial | `triggers` (`run.context_json`) | No declared typed input params → **`workflow-input-parameters`** |
| 16 | **17+ block types** — `validation`, `text_prompt` (LLM, no browser), `while_loop`, `print_page` (page→PDF), `file_upload`, `file_download`, `goto_url`, `download_to_s3` | Partial | `expanded-node-library` (http/file/email/parse/foreach/subworkflow) | Missing blocks → **`vision-and-utility-blocks`** |
| 17 | **Concurrent execution at scale** — parallel runs, browser pool | Gap | platform (one-run-at-a-time) | **`concurrent-runs-browser-pool`** |
| 18 | **CAPTCHA solving + anti-bot + proxy network** | Gap | — | **`captcha-antibot-proxy`** |
| 19 | **Run cost tracking** — aggregate token/vision cost per run | Partial | per-event `cost_hint` only | No aggregation surface → **`run-cost-tracking`** |
| 20 | **Record-and-generate** — record a manual browser session, synthesise a workflow | Gap | — | **`record-and-generate`** |
| 21 | **Code caching for repeatability** — cache the resolved action plan / selectors to skip the LLM on re-runs | Gap | self-heal flagged it as future | **`selector-cache-learning`** (+ action-plan caching) |
| 22 | **Team sharing / orgs / multi-user** | Gap | `owner_id` reserved, unused | **`multi-user-orgs`** |
| 23 | **Cron + webhook triggers / scheduling** | Covered | `triggers-and-scheduling` | — |
| 24 | **Per-node retry / on-error branching** | Covered | `node-error-handling` | — |
| 25 | **Node→node context variables** | Covered | `node-context-variables` | — |
| 26 | **Visual workflow editor + chat authoring** | Covered | `workflow-canvas`, `chat-authoring` | — |
| 27 | **Runtime LLM provider/model config** | Covered | `runtime-llm-config` | — |

## 2. Proposed new changes (prioritised)

Grouped into tiers. Within a tier, items are roughly independent. Effort tags follow `ROADMAP.md` (S ≈ 5d, M ≈ 5–10d, L ≈ 10–15d).

### Tier 1 — Core Skyvern identity (vision + sessions + observability)

These four are what make a tool "feel like Skyvern". Highest priority.

| # | Change id | One-line | Depends on | Effort |
| --- | --- | --- | --- | --- |
| T1.1 | `vision-action-mode` | AI-goal `navigate` + single AI `action` + schema-validated `extraction`, driven by screenshot + a11y tree (no required selector). Generalises today's `fuzzy_action`. | `auto-agent-mvp`, `self-healing-selectors`, `runtime-llm-config` | L |
| T1.2 | `browser-sessions-profiles` | Persistent live **sessions** (≤24h) + saved **profiles** (cookies/storage snapshots) reusable across runs; `browser_session_id` / `profile_id` on runs. | `auto-agent-platform` (Run, browser singleton) | L |
| T1.3 | `browser-livestream` | Real-time browser viewport stream (CDP screencast → WS frames) on the run page. | `live-event-stream`, `auto-agent-platform` | M |
| T1.4 | `run-artifacts-observability` | Per-step screenshots, action logs, session video recording, LLM diagnostic traces, downloaded-file artifacts; artifact store + run-detail UI. | `run-history` | L |

### Tier 2 — Authentication & secrets parity

| # | Change id | One-line | Depends on | Effort |
| --- | --- | --- | --- | --- |
| T2.1 | `totp-2fa-automation` | TOTP credential type (auto-generate + auto-fill) + credit-card credential type; `totp_identifier` on runs/login. | `credential-vault` | M |
| T2.2 | `login-block` | Dedicated `login` node that authenticates with a linked credential, driving the vision/selector login flow + TOTP. | `vision-action-mode`, `totp-2fa-automation`, `per-workflow-credentials` | M |
| T2.3 | `credential-backends-strategy` | `CredentialBackend` strategy interface: Local Fernet, EnvVar, Bitwarden, 1Password, Azure Key Vault, custom HTTP vault. | `credential-vault` | M |

### Tier 3 — Programmatic surface & integration parity

| # | Change id | One-line | Depends on | Effort |
| --- | --- | --- | --- | --- |
| T3.1 | `public-api-and-auth` | API-key auth + stable public REST surface (tasks, workflows, runs, credentials, cancellation) + OpenAPI. | `auto-agent-platform` | M |
| T3.2 | `sdk-and-mcp` | Thin Python + TypeScript SDK and an MCP server over the public API (`run_task`, `run_workflow`, `get_run`, `cancel`). | `public-api-and-auth` | M |
| T3.3 | `outbound-webhooks-hmac` | HMAC-signed outbound webhooks on run state transitions, with retry + replay + SSRF guard. | `auto-agent-platform`, `triggers-and-scheduling` | M |

### Tier 4 — Workflow expressiveness parity

| # | Change id | One-line | Depends on | Effort |
| --- | --- | --- | --- | --- |
| T4.1 | `workflow-input-parameters` | Declared typed workflow inputs supplied at run time (UI/API/trigger), referenced via `{{params.<name>}}`. | `node-context-variables`, `auto-agent-platform` | M |
| T4.2 | `vision-and-utility-blocks` | Remaining Skyvern blocks: `validation`, `text_prompt` (LLM-only), `while_loop`, `print_page` (page→PDF), `file_upload`, `file_download`, `goto_url`. | `expanded-node-library`, `vision-action-mode` | M |

### Tier 5 — Scale & robustness parity

| # | Change id | One-line | Depends on | Effort |
| --- | --- | --- | --- | --- |
| T5.1 | `concurrent-runs-browser-pool` | Lift one-run-at-a-time: a bounded browser-context pool enabling N concurrent runs. | `auto-agent-platform`, `browser-sessions-profiles` | L |
| T5.2 | `captcha-antibot-proxy` | CAPTCHA detection + pluggable solver hook, proxy configuration, basic anti-bot hardening. | `vision-action-mode` | M |
| T5.3 | `run-cost-tracking` | Aggregate per-event `cost_hint` into `Run.total_cost_*`; render in run list/detail. | `run-history`; benefits from `vision-action-mode` | S |
| T5.4 | `selector-cache-learning` | Cache resolved selectors / action plans per `(workflow, page-url)` to skip LLM on re-runs (code-caching analog). | `self-healing-selectors`, `vision-action-mode` | M |

### Tier 6 — Collaboration & advanced (lower priority for a local POC)

| # | Change id | One-line | Depends on | Effort |
| --- | --- | --- | --- | --- |
| T6.1 | `multi-user-orgs` | Activate reserved `owner_id`; orgs/teams; workflow + credential sharing; per-resource ACLs. | `public-api-and-auth` | L |
| T6.2 | `record-and-generate` | Record a manual browser session and synthesise a reusable workflow ("show once, run forever"). | `vision-action-mode`, `run-artifacts-observability` | L |

## 3. Recommended build order

1. **`vision-action-mode`** (T1.1) — unlocks the Skyvern "no brittle selectors" identity and is a dependency for login/blocks/captcha/cache.
2. **`run-artifacts-observability`** (T1.4) + **`browser-livestream`** (T1.3) — make runs debuggable, which everything else leans on.
3. **`browser-sessions-profiles`** (T1.2) — auth reuse; unblocks concurrency.
4. **`totp-2fa-automation`** (T2.1) → **`login-block`** (T2.2) → **`credential-backends-strategy`** (T2.3).
5. **`public-api-and-auth`** (T3.1) → **`sdk-and-mcp`** (T3.2); **`outbound-webhooks-hmac`** (T3.3) in parallel.
6. **`workflow-input-parameters`** (T4.1) → **`vision-and-utility-blocks`** (T4.2).
7. **`concurrent-runs-browser-pool`** (T5.1), **`captcha-antibot-proxy`** (T5.2), **`run-cost-tracking`** (T5.3), **`selector-cache-learning`** (T5.4).
8. **`multi-user-orgs`** (T6.1), **`record-and-generate`** (T6.2) — last.

## 4. Explicitly out of parity scope (for now)

- **Skyvern Cloud-only infra** (managed proxy network at scale, hosted multi-region browsers) — `auto-agent` stays single-machine local; `captcha-antibot-proxy` only adds the *config hooks*, not a managed network.
- **Anti-bot bypass as a product** — we add hooks, not a bypass service.
- **Billing / metering** — `run-cost-tracking` surfaces cost; no billing.

## 5. Status

All 18 parity changes are **specced** (full `proposal / design / specs / tasks`, `openspec validate` clean). Implementation tasks are tracked inside each change's `tasks.md` and are not yet started.

- [x] Gap analysis written (this document).
- [x] Tier 1 specced — `vision-action-mode`, `browser-sessions-profiles`, `browser-livestream`, `run-artifacts-observability`.
- [x] Tier 2 specced — `totp-2fa-automation`, `login-block`, `credential-backends-strategy`.
- [x] Tier 3 specced — `public-api-and-auth`, `sdk-and-mcp`, `outbound-webhooks-hmac`.
- [x] Tier 4 specced — `workflow-input-parameters`, `vision-and-utility-blocks`.
- [x] Tier 5 specced — `concurrent-runs-browser-pool`, `captcha-antibot-proxy`, `run-cost-tracking`, `selector-cache-learning`.
- [x] Tier 6 specced — `multi-user-orgs`, `record-and-generate`.

Next step: implement, in the build order of §3 (start with `vision-action-mode`). Run `openspec list` to see task progress per change.
