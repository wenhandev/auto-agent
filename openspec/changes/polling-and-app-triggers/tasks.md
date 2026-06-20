## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Extend `Trigger`: add `poll`/`app` to `type`; add poll-state fields (`poll_app/resource/operation`, `poll_dedup_path`, `poll_cursor`, `last_seen_key`, `poll_mode`, `on_first_poll`, `min_poll_interval_s`) and app fields (`app_name`, `subscription_id`, `subscription_secret`). Migration adds nullable columns.
- [x] 1.2 `[shared-contract]` Add `TriggerDescriptor` + `VerificationSpec` to the integration descriptor schema; loader validates referenced operations exist.
- [x] 1.3 `[shared-contract]` Add a bounded `processed_events` store (SQLite table with TTL sweep) for idempotency.
- [x] 1.4 `[shared-contract]` Extend `triggered_by.kind` with `poll`/`app`; realise `{{run.context.*}}` / `{{trigger.*}}` resolution in `variable_interpolation` (replacing the reserved-prefix error).
- [ ] 1.5 `[shared-contract]` API + TS mirrors for poll/app trigger CRUD and the app callback; smoke-check migration + `tsc --noEmit`.

## 2. Poll runner (Sibling A — `[backend-triggers]`)

- [x] 2.1 `app/services/poll_runner.py`: register poll jobs with the existing scheduler; reconcile on CRUD; enforce `min_poll_interval_s`.
- [x] 2.2 Call the integration list operation (with cursor); diff against `last_seen_key`/cursor/seen-set; enqueue per-record or batched via `create_queued_run`; persist state after enqueue.
- [x] 2.3 `on_first_poll` backfill modes (`fire_none`/`fire_latest`/`fire_all`).
- [x] 2.4 Tests `backend/tests/test_poll_runner.py`: only-new fires; no-new fires nothing; per-record vs batched; first-poll modes; interval enforced; run.context resolves.

## 3. App webhook triggers (Sibling B — `[backend-triggers]`)

- [x] 3.1 Subscription lifecycle: subscribe on enable (callback URL + generated secret), store `subscription_id`; unsubscribe on disable/delete.
- [x] 3.2 `POST /api/triggers/app/{trigger_id}`: URL-challenge handshake; signature verification (HMAC/shared-secret/custom hook); reject on failure.
- [x] 3.3 Event normalization via `event_item_path`; enqueue via `create_queued_run` with `triggered_by.kind="app"`.
- [x] 3.4 Idempotent delivery using `processed_events` + retention window.
- [x] 3.5 Tests `backend/tests/test_app_triggers.py`: subscribe/unsubscribe; challenge echo; valid/invalid signature; event→run; provider-retry dedup.

## 4. Descriptor triggers + prompts (parent worker)

- [x] 4.1 Wire descriptor `triggers[]` loading + validation into the integration registry.
- [x] 4.2 Add `triggers[]` to the `core-app-integrations` apps where applicable (e.g. Slack message events, Notion DB poll, Sheets poll) — as a fast-follow stub if those apps land separately.
- [ ] 4.3 Planner/editor prompt note: app triggers are workflow entry points; substring regression test.

## 5. Frontend (Sibling C — `[frontend]`)

- [x] 5.1 "触发器" tab: poll editor (pick app/resource/operation, dedup path, mode, first-poll, interval).
- [x] 5.2 App trigger editor: "Connect & subscribe" with subscription status; show callback URL.
- [ ] 5.3 Run-history pills show `poll`/`app` kind + source record/event summary.
- [ ] 5.4 Smoke-check: `npm run build`; configure a poll trigger against a fixture app and observe a fired run.

## 6. Verification (parent worker)

- [x] 6.1 `[verification]` Poll: against a fixture list op, confirm only new records fire, exactly once, with backfill suppressed on first poll.
- [x] 6.2 `[verification]` App: subscribe, echo a challenge, deliver a signed event → run; deliver an invalid signature → rejected; re-deliver same id → deduped.
- [x] 6.3 `[verification]` `{{run.context...}}` and `{{trigger.kind}}` resolve in a triggered run; existing cron/webhook triggers still work.
- [ ] 6.4 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

### Sibling A — Poll runner `[backend-triggers]`
**Owns.** `app/services/poll_runner.py`, poll-state persistence, scheduler reconciliation for poll jobs, poll tests.
**Must NOT touch.** App-webhook callback internals, frontend.

### Sibling B — App webhook triggers `[backend-triggers]`
**Owns.** Subscription lifecycle, `POST /api/triggers/app/{id}`, verification + challenge, idempotency, app tests.
**Must NOT touch.** Poll runner internals (share the `processed_events` store + `create_queued_run` only), frontend.

### Sibling C — Frontend `[frontend]`
**Owns.** Poll + app trigger editors, subscription status, run-history pills, TS mirrors.
**Must NOT touch.** Backend.

**Shared contract deps (§1).** `Trigger` extensions + migration, `TriggerDescriptor`/`VerificationSpec`, `processed_events` store, `triggered_by` + `{{run/trigger}}` resolution, API contracts. Both backend siblings build on `triggers-and-scheduling`'s `create_queued_run` and scheduler.
