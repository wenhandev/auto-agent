# References & Prior-Art Mapping

This document maps open-source projects we read to specific decisions in the six in-flight OpenSpec changes (`triggers-and-scheduling`, `node-context-variables`, `node-error-handling`, `human-in-the-loop`, `self-healing-selectors`, `expanded-node-library`). Each per-change section names the closest analog, calls out concrete file paths whose pattern we'd lean on, lists patterns we explicitly reject, and surfaces edge cases the analog handles that our spec does not yet.

The intent is decision-oriented, not survey-oriented. Skip projects whose pattern we are already comfortable with; lean on projects whose pattern would change something we have already decided. Citations are GitHub URLs to files we actually fetched. One listed project — `magnitudedev/magnitude` — has since pivoted from an E2E test framework to a coding-agent harness; we mark its self-healing surface as no longer citable in the current repo rather than fabricate file paths. Tier-3 chat / autonomous frameworks (AutoGen, OpenHands, OpenAdapt) inform a possible future "autonomous mode" and one HITL pattern below, but do not change the six in-flight specs in meaningful ways.

## Per-change reference matrix

### 1. `triggers-and-scheduling`

- **Closest analog**: **Skyvern**. Single-process scheduler reading a per-row `Trigger` table, croniter-based parsing, per-trigger webhook endpoint.
- **Borrow**:
  - [`skyvern/forge/sdk/workflow/schedules.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/forge/sdk/workflow/schedules.py): wraps `croniter` with `MIN_CRON_INTERVAL_SECONDS = 5*60` and exposes `compute_next_run`/`compute_previous_fire_time`. We have no minimum guard; the next-fire helper is the exact backend for a `GET /api/triggers/{id}/next-fires?n=5` UI preview that Decision 5's "下次触发" surface needs.
  - [`skyvern/services/webhook_service.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/services/webhook_service.py): `_validate_target_url` + `BlockedHost` SSRF guard. Irrelevant for our inbound webhook today, mandatory the moment `services.notifications.emit(...)` graduates to a real outbound POST.
  - Skyvern's `generate_skyvern_webhook_signature` (same file) is the HMAC pattern our `Trigger.auth_mode = "hmac"` enum reserves but does not yet implement.
  - **Prefect**'s [`flow.serve(cron=...)`](https://github.com/PrefectHQ/prefect) is the declarative-in-code alternative — concise but uneditable from a UI. Worth naming in `Alternatives considered`; we chose DB-row CRUD for that exact reason.
- **Reject**:
  - **Apache Airflow**'s missed-tick catchup ([`apache/airflow`](https://github.com/apache/airflow)). Operationally heavy; single-user POC drops missed ticks per spec Goal.
  - Skyvern's strict 5-minute minimum interval: too strict for short e-commerce polling tasks. A 60 s floor is the right relax.
- **Edge cases missing in our spec**:
  - No minimum-interval enforcement. Patch: `MIN_CRON_INTERVAL_SECONDS = 60` validator on `Trigger.schedule_or_path`.
  - No `next_fires` API for the editor UI preview. Patch: backed by `compute_next_run`.
  - No `validate_timezone_name` style hard-fail on unknown IANA names; spec leaves this to APScheduler's runtime error.

### 2. `node-context-variables`

- **Closest analog**: **n8n** expressions (`{{$json[...]}}`) and **Skyvern**'s `context_manager.py` + `_jinja.py`.
- **Borrow**:
  - [`skyvern/forge/sdk/workflow/models/_jinja.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/forge/sdk/workflow/models/_jinja.py): Jinja2 sandboxed environment. Worth recording in `Alternatives considered` because both n8n and Skyvern drifted toward Jinja-style features over time (see Anti-patterns).
  - [`skyvern/forge/sdk/workflow/models/parameter.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/forge/sdk/workflow/models/parameter.py): declares `RESERVED_PARAMETER_KEYS = ["current_item","current_value","current_index","workflow_run_outputs", ...]`. We reserve `nodes`/`cred`/`run`/`trigger` (Decision 11); adding the loop-iteration names now (instead of during `expanded-node-library`) keeps the reserved-prefix error message stable across two changes.
  - **browser-use** [`browser_use/agent/variable_detector.py`](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/variable_detector.py): scans text for variable-like substrings. Same shape we need for the chip-rendering in Decision 7.
  - **Stagehand** [`packages/core/lib/inference.ts`](https://github.com/browserbase/stagehand/blob/main/packages/core/lib/inference.ts) requires a Zod schema on `extract()`. Optional per-node `output_schema` (no-op when omitted) would give Decision 6's variable picker something to render when no successful run exists.
- **Reject**:
  - n8n's full JavaScript expression grammar (arithmetic, ternaries, `.first()`/`.last()`). Locks us into a V8-shaped runtime forever.
  - LaVague [`python_engine.py`](https://github.com/lavague-ai/LaVague/blob/main/lavague-core/lavague/core/python_engine.py) `exec()`s LLM-generated Python — more permissive than n8n; hard out.
- **Edge cases missing in our spec**:
  - n8n surfaces variable shapes from the in-authoring preview run, not just the last successful run; the "last green build" idiom in our Decision 6 lags. Defer to a future `editor-preview-runs`, but cite.
  - `{{` literal escape (`{{ {{`) is in Risks/Trade-offs only — should be a SHALL in the requirements block.
  - Skyvern's reserved `workflow_run_summary` hints at a rolling-summary surface we have no spec for. Note in Decision 11.

### 3. `node-error-handling`

- **Closest analog**: **Prefect** (`@task(retries=3, retry_delay_seconds=...)`) and **Apache Airflow** operators' `retries`/`retry_delay`/`trigger_rule="all_failed"`.
- **Borrow**:
  - Skyvern [`error_detection_service.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/services/error_detection_service.py) classifies failure kinds before deciding policy. We stop at `error_kind = type(exc).__name__`; a small classifier (network vs DOM-timeout vs validation) feeds smarter retry presets in the editor and keeps the future change additive.
  - Prefect accepts `retry_delay_seconds=[1,2,4]` (per-attempt list). Our linear `i*backoff_ms` is fine for v1; `RetryPolicy.backoff_ms: int` widens cleanly to `int | list[int]` later.
  - n8n's `continueOnFail` per-node flag = our `on_error="continue"`. Pattern convergence confirms Decision 4.
  - Airflow's `trigger_rule="all_failed"` is the source→target equivalent of our `kind="on_error"` edge — more flexible (graph-wide), more confusing to render. Our 1:1 edge is the right scale call; record in `Alternatives considered`.
- **Reject**:
  - Airflow exponential backoff with jitter (their default). Replay determinism per Decision 2.
  - Prefect per-flow retry budgets. Explicit non-goal.
- **Edge cases missing in our spec**:
  - No per-error-kind policy in v1. Already implied; name "policy keyed by error_kind is a future change" in `Non-goals`.
  - No total wall-time cap. Patch: `RetryPolicy.max_wall_ms: Optional[int]` so the operator doesn't have to sum the linear series.
  - No promoted-to-column `attempt` count: Airflow stores `try_number` on `task_instance`; we keep `attempt` in event payload only. Fine until aggregation queries appear.

### 4. `human-in-the-loop`

- **Closest analog**: **Activepieces** (Slack/Telegram approval pieces) and **n8n**'s `Wait` node. **Skyvern**'s TOTP pause (`otp_service.py`) is the same plumbing for a narrower purpose.
- **Borrow**:
  - Skyvern [`otp_service.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/services/otp_service.py) pauses with an explicit deadline + typed `OtpTimeoutError`. We chose "no timeout in v1" (Decision 4); the deadline shape is the obvious skeleton for the deferred `approval-timeouts` change wired through `services.notifications.emit("approval_requested", ...)`.
  - [`activepieces/activepieces`](https://github.com/activepieces/activepieces) ships approval as a piece with the resume URL embedded in the outbound notification. Our `POST /api/runs/{id}/approvals/{node_id}` is the same shape — internal rather than tunnelled. Decision 6 aligns.
  - n8n's `Wait` persists `wait_until` + `wait_token` on the execution row. Our `asyncio.Event` is process-memory; their token shape is the upgrade path once multi-user lands.
  - **OpenHands** ([`All-Hands-AI/OpenHands`](https://github.com/All-Hands-AI/OpenHands)) "confirmation mode": agent waits for approval before high-risk actions — policy-driven, not design-time-declared. Our approval node is the design-time variant; OpenHands' confirmation is the future "autonomous mode" pair.
- **Reject**:
  - Activepieces multi-approver flows. Explicit non-goal.
  - Activepieces / n8n persistent-resume-across-restart: useful only if Playwright state survives, which it does not. Decision 7 correctly degrades to `failed` on restart.
- **Edge cases missing in our spec**:
  - No "approval stuck > N minutes" event (feeds future `approval-timeouts`). Patch: define the event name + payload now so the future change is body-only.
  - No idempotency token on the resolve endpoint (n8n requires one). Our 409-on-not-pending races for a millisecond.
  - No `reject_reason: Optional[str]` field. Operators want a reason in history.

### 5. `self-healing-selectors`

- **Closest analog**: **Stagehand**'s self-healing claim ("auto-caching combined with self-healing... knows when to involve AI"). **Skyvern** sidesteps the problem (vision-always, no selectors at all).
- **Borrow**:
  - Stagehand [`inference.ts`](https://github.com/browserbase/stagehand/blob/main/packages/core/lib/inference.ts) + [`prompt.ts`](https://github.com/browserbase/stagehand/blob/main/packages/core/lib/prompt.ts): two-input prompt skeleton (accessibility tree + screenshot). Ours (Decision 5) is more cost-conscious (DOM-first / vision-fallback). Borrow the prompt skeleton, keep our gating.
  - Stagehand [`v3Evaluator.ts`](https://github.com/browserbase/stagehand/blob/main/packages/core/lib/v3Evaluator.ts): a separate "did the action achieve the intended outcome?" LLM call. We trust heal confidence + Playwright-success retry. A future `heal-post-evaluator` change could insert this before claiming `node_self_healed`.
  - browser-use [`views.py`](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/views.py) defines `AgentBrain` (structured per-step observation). Our `node_self_healed` payload (`original_selector`, `new_selector`, `confidence`, `mode`) is intentionally analogous.
  - Skyvern [`block.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/forge/sdk/workflow/models/block.py): 374 KB monolith — no selectors to heal because their `act()` is vision-driven from day one. The architectural alternative to our hop-in-wrapper design; recording the cost (one file, 374 KB) helps reviewers see why we don't follow.
  - LaVague [`action_engine.py`](https://github.com/lavague-ai/LaVague/blob/main/lavague-core/lavague/core/action_engine.py): compiles natural-language instructions into Selenium/Playwright code per execution. Different solution to the same brittleness; out of our roadmap.
  - **Magnitude** ([`magnitudedev/magnitude`](https://github.com/magnitudedev/magnitude)) historically positioned a two-stage heal; the current `main` branch is a coding-agent harness with no E2E test-runner code, so we cannot cite file paths for that pattern in the current repo. Pattern is recorded here from memory only; no live file reference.
- **Reject**:
  - Stagehand's auto-persist healed selectors into a workflow cache. We chose chat-prefill (Decision 8) — audit trail wins.
  - Skyvern's vision-always: cost amplification under retries is too high.
- **Edge cases missing in our spec**:
  - PII masking beyond `type="password"`. Patch: `node.params.auto_heal_mask_selectors: list[str]` for forward compat.
  - No post-heal semantic evaluator (Stagehand `v3Evaluator`). Our `post_heal_action_failed` is a Playwright outcome.
  - No per-run cost cap. LaVague's [`token_counter.py`](https://github.com/lavague-ai/LaVague/blob/main/lavague-core/lavague/core/token_counter.py) short-circuits at a budget. Under `node-error-handling` retries × heals, this matters — see recommendations.

### 6. `expanded-node-library`

- **Closest analog**: **n8n** (400+ integrations) and **Activepieces** (280+ pieces). Both implement "discriminated-by-type, per-type schema, separately importable module".
- **Borrow**:
  - [`activepieces packages/pieces/framework/src`](https://github.com/activepieces/activepieces/tree/main/packages/pieces/framework/src): every piece is its own typed module (`props`, `auth`, `run()`). Our pydantic discriminator (Decision 1) is the Python equivalent. Concrete file layout suggestion: `backend/app/nodes/<type>.py` exporting both `<Type>Params` and `def execute_<type>(...)`.
  - Skyvern [`block.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/forge/sdk/workflow/models/block.py) declares the catalogue we are adding: `HttpRequestBlock`, `SendEmailBlock`, `FileParserBlock`, `FileDownloadBlock`, `ForLoopBlock`, plus a `CodeBlock` we reject. The monolith file (374 KB) is the cautionary tale — see Anti-patterns.
  - **Prefect** subflow shape ([`PrefectHQ/prefect`](https://github.com/PrefectHQ/prefect)): parent flow run row references child runs. Our `Run.parent_run_id` (Decision 10) mirrors this.
  - n8n's `HttpRequest` returns `{statusCode, headers, body}` — same envelope as our Decision 3 `{status, headers, json, text, elapsed_ms}`. Convergence is evidence the shape is right.
  - Skyvern `parameter.py`'s `ContextParameter` pushes `current_item`/`current_index`/`current_value` for loops. Decision 6's `{{nodes.<foreach_id>.output.item}}` / `.index` is analogous; align reserved-name lists across both specs so the editor agent stays agnostic.
- **Reject**:
  - n8n `Code` node, Activepieces' "Code with NPM", Skyvern `CodeBlock`. Same supply-chain / sandbox-escape hazard.
  - Activepieces' "pieces install from npmjs.com at runtime": dynamic plugin loading is wrong for a single-machine POC.
  - Skyvern `LoopBlock` over external connections (e.g. Google Sheets pull). Our `foreach` iterates over context-resident data only; simpler validation, no per-iteration connection lifecycle.
- **Edge cases missing in our spec**:
  - Parallel `foreach` for non-browser bodies (Prefect `map()`). Defer to a future `foreach-parallel-non-browser`.
  - Per-iteration body output schema: Skyvern types `current_item` against the parent's data schema; we rely on run history. A typed iteration schema would be cleaner.
  - `subworkflow` input validation against child's declared `WorkflowParameter`. Our `input: dict[str, Any]` is permissive; Skyvern validates types at sub-call time.

## Cross-cutting themes

1. **One source of truth or pay forever.** Skyvern reads `Trigger` rows fresh per event and rebuilds APScheduler (`schedules.py`). We do the same. Every project we read picks ONE source for the schedule. Our `triggers-and-scheduling` Decision 2 is well-supported.

2. **Two-stage heal (cheap → expensive) is consensus.** Magnitude (per its historical positioning), our `self-healing-selectors` Decision 5, and Stagehand's "knows when to involve AI" all share the cost-controlled escalation shape. Outliers: Skyvern (vision-always, owns the cost), pure-DOM heals (cheap, blind on poorly-marked pages). Nobody serious is vision-only without budget gating.

3. **Cost surface is the gap.** LaVague's [`token_counter.py`](https://github.com/lavague-ai/LaVague/blob/main/lavague-core/lavague/core/token_counter.py), Skyvern's `WorkflowRunResponseBase.total_cost` (in `webhook_service.py`), browser-use's [`cloud_events.py`](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/cloud_events.py). We emit per-event `cost_hint` with no aggregation surface. After `subworkflow` and `foreach` multiply call counts, this becomes the most-asked-for feature.

4. **Design-time schemas AND runtime shapes — both.** n8n uses runtime shapes; Stagehand requires Zod schemas on `extract()`; Activepieces declares prop types at piece module level. Hybrid is the mature answer: declared shape when the author knows it, observed shape otherwise. An optional `output_schema` per node type costs nothing for nodes that omit it.

5. **Credentials are pluggable, never built-in.** Skyvern's [`parameter.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/forge/sdk/workflow/models/parameter.py) lists 8 backends (Bitwarden, 1Password, AWS Secrets, Azure Vault, ...). We have one. The next non-browser node (`send_email`, `http_request`) is the moment the single-backend assumption locks in.

## Recommended new OpenSpec changes

1. **`run-cost-tracking`** (S, ~5d). Aggregate per-event `cost_hint` into `Run.total_cost_*` columns; render in run list. Patterns: LaVague `token_counter.py` + Skyvern `total_cost`. Becomes essential post-`self-healing-selectors` + `expanded-node-library`.
2. **`webhook-hmac-signing`** (S, ~3d). Promote `Trigger.auth_mode = "hmac"` from reserved-only to implemented. Pattern: Skyvern `generate_skyvern_webhook_signature` in `services/webhook_service.py`. Body-only change; trigger schema already widened.
3. **`outbound-webhooks`** (M, ~7d). Replace `services.notifications.emit(...)` stub with a real configurable-URL POST surface plus SSRF protection (Skyvern `_validate_target_url` + `BlockedHost`). Unblocks `approval-timeouts` reminders and run-state-transition callbacks.
4. **`selector-cache-learning`** (M, ~7d). Persist `(workflow_id, page_url_pattern, original_selector) -> healed_selector` after success; skip vision on subsequent runs. Already flagged in `self-healing-selectors` Non-goals; events emitted there carry enough info — purely additive.
5. **`credential-backends-strategy`** (M, ~10d). Re-spec credentials as a strategy interface (`CredentialBackend` ABC with `Local`, `EnvVar`, `BitwardenCLI` first). Pattern: Skyvern's 8-backend `parameter.py`. Block BEFORE `expanded-node-library` lands or accept a future rewrite.

## Anti-patterns / things to be wary of

1. **Monolith-file accretion.** Skyvern's [`block.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/forge/sdk/workflow/models/block.py) is 374 KB — every block type appended over time. The spec for `expanded-node-library` should NAME the file layout (one file per type under `backend/app/nodes/<type>.py`) so we never land here.
2. **Codegen + execution in one module.** Skyvern's [`workflow_script_service.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/services/workflow_script_service.py) is 145 KB of mixed templating and execution. If we ever build workflow-to-script export, keep it strictly outside the executor.
3. **LLM-emitted code that gets `exec()`d.** LaVague [`python_engine.py`](https://github.com/lavague-ai/LaVague/blob/main/lavague-core/lavague/core/python_engine.py); Skyvern `CodeBlock`. Sandbox-escape on jailbreak. `expanded-node-library` Non-goals correctly excludes; hold the line.
4. **Expression-language drift.** n8n's `{{$json[...]}}` started literal, grew arithmetic / ternaries / `.first()` / `.map()`. Each step felt small; cumulative complexity blocks ever porting to another runtime. `node-context-variables` Decision 2 must stay dot-and-index-only forever.
5. **Tier-3 framework churn.** AutoGen ([`microsoft/autogen`](https://github.com/microsoft/autogen)) is in maintenance mode; Microsoft migrated users to Agent Framework. If the editor agent (or a future autonomous mode) leans on a Tier-3 framework, plan migration paths early.

## Open questions for the human

1. Skyvern enforces a **5-min minimum cron interval** in [`schedules.py`](https://github.com/Skyvern-AI/skyvern/blob/main/skyvern/forge/sdk/workflow/schedules.py). Our spec has no minimum. Adopt a **60 s** floor (less strict than Skyvern's, still closes the storm footgun)?
2. Skyvern signs every outbound webhook with HMAC from day one. Our `auth_mode` reserves but defers HMAC. **Promote `webhook-hmac-signing` to near-term** rather than indefinite future?
3. Stagehand requires a **Zod schema** on `extract()`. We rely on the most recent successful run. Ship an optional **`output_schema` per node** so the variable picker degrades gracefully without history?
4. LaVague (and every mature framework) has a **central cost counter**. We have per-event `cost_hint` only. **Promote `run-cost-tracking` ahead of `expanded-node-library`** so the surface exists before `subworkflow`/`foreach` multiply call counts?
5. Skyvern lists **8 credential backends**. We support one. **Re-spec the credential layer as a strategy interface BEFORE `send_email`/`http_request` lock in the single-backend assumption** — even if it slips `expanded-node-library` by one cycle?

## Skyvern parity wave

The open questions above are now answered by concrete specced changes (see `SKYVERN_PARITY.md` and `ROADMAP.md`): #2 → `outbound-webhooks-hmac`, #3 → schema-validated extraction in `vision-action-mode`, #4 → `run-cost-tracking`, #5 → `credential-backends-strategy`. A further full gap analysis against Skyvern's 2026 feature set produced 18 parity changes spanning vision-first action, browser sessions/profiles, livestreaming, run artifacts/observability, TOTP/2FA, a public API + SDK/MCP, concurrency, CAPTCHA/proxy, cost tracking, selector caching, multi-user orgs, and record-and-generate. Each change's `design.md` records its own borrow/reject decisions against the relevant prior art (Skyvern, Stagehand, browser-use, n8n, Activepieces, Prefect) in the same decision-oriented style as the per-change matrix above.
