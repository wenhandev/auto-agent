## 1. Data model

- [x] 1.1 Add `BrowserProfile` SQLModel (encrypted `storage_state_path`, name unique)
- [x] 1.2 Add `BrowserSession` SQLModel (`status`, `expires_at`, `last_activity_at`, nullable `profile_id`)
- [x] 1.3 Add `Run.browser_session_id` / `Run.browser_profile_id` (additive, default NULL)
- [x] 1.4 Create `backend/data/browser_profiles/` in lifespan; add to `.gitignore` — uses `backend/data/profiles/`
- [x] 1.5 Add `SESSION_IDLE_MINUTES=30`, `MAX_LIVE_SESSIONS=5` to settings + `.env.example`

## 2. Session manager

- [x] 2.1 Create `app/services/browser_sessions.py` holding `session_id → BrowserContext`
- [x] 2.2 Implement `acquire(session_id|profile_id|None)` and `release(session_id, keep_alive)`
- [x] 2.3 Implement profile encryption/decryption via the Fernet key (capture + seed)
- [x] 2.4 Implement the 24h TTL + idle-eviction reaper in the FastAPI lifespan
- [x] 2.5 On startup, mark all previously-live sessions `expired`
- [x] 2.6 Enforce `MAX_LIVE_SESSIONS` (429 on overflow)

## 3. API

- [x] 3.1 CRUD router `app/routers/browser_profiles.py`
- [x] 3.2 `POST /api/browser-profiles/{id}/capture-from-run/{run_id}`
- [x] 3.3 Router `app/routers/browser_sessions.py` (create/list/get/close/keep-alive)
- [x] 3.4 `POST /api/runs` accepts optional `browser_session_id` / `browser_profile_id`
- [x] 3.5 `RunOut` exposes the session/profile binding

## 4. Executor wiring

- [x] 4.1 Executor acquires a context via the session manager based on the run's binding — profile via `begin_run`
- [x] 4.2 On run end, release with `keep_alive=true` for session-bound runs — N/A until sessions

## 5. Frontend

- [x] 5.1 "浏览器会话" sidebar page: live sessions (expiry countdown + close) and saved profiles
- [x] 5.2 Run-Now dialog: session/profile selector
- [x] 5.3 "保存为配置档" button at run end (capture-from-run)
- [x] 5.4 Run detail shows which session/profile the run used
- [x] 5.5 API client methods for profiles + sessions

## 6. Tests

- [x] 6.1 Profile capture→seed round-trip reuses cookies
- [x] 6.2 Session TTL/idle eviction; restart marks expired
- [x] 6.3 `MAX_LIVE_SESSIONS` 429
