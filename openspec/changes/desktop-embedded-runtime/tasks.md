## 1. Phase 4A — Product shell (parallel track)

- [x] 1.1 Production startup gate waits on runtime only (`RuntimeStatusContext`)
- [x] 1.2 Friendly preflight labels (`deviceStatus.ts`, Overview copy)
- [x] 1.3 Sidebar branding "Auto Agent" + online indicator
- [x] 1.4 Add **Home** page at `/` with quick actions (Workflows, Runs, device summary)
- [x] 1.5 Move technical Overview to `/device`; link from Settings
- [x] 1.6 Reorder nav: Home, Workflows, Runs, Settings; group Advanced (Recordings, Autonomous task)
- [x] 1.7 Production login copy — no "register as worker" jargon
- [x] 1.8 Settings copy — "This device" / LLM for local runs
- [ ] 1.9 Rebuild release DMG and smoke-test Home + OAuth flow

## 2. Phase 4B — Embedded runtime IPC

- [x] 2.1 Create `app/worker/desktop_api.py` — extract session, status, runs, drafts, LLM from `daemon.py`
- [x] 2.2 Define message envelope schema (version, method, payload, error) + Rust types
- [x] 2.3 Python `desktop-host` entry: asyncio message loop (Unix socket or stdin/stdout)
- [x] 2.4 Rust `runtime_host.rs`: spawn host, send/receive frames, map to existing Tauri commands
- [x] 2.5 Port `runtime_health`, `runtime_invoke` for `/status`, `/session` over message IPC
- [ ] 2.6 Port run start/abort/list + event stream push over message IPC
- [ ] 2.7 Port drafts, LLM settings, cloud proxy helpers
- [ ] 2.8 Feature flag: release uses message host; dev HTTP fallback until parity
- [ ] 2.9 Remove uvicorn/FastAPI from release worker spawn (`serve` dev-only)
- [ ] 2.10 Integration tests: Rust ↔ Python message round-trip; run console E2E

## 3. Phase 4C — Single process (optional)

- [ ] 3.1 Spike: PyO3 embed vs subprocess message host (macOS arm64)
- [ ] 3.2 Decision doc update based on spike (crash isolation, bundle size, Playwright)
- [ ] 3.3 If approved: embed Python runtime thread in Tauri; drop separate worker PID

## 4. Docs

- [x] 4.1 OpenSpec change `desktop-embedded-runtime` (proposal, design, specs)
- [ ] 4.2 Update `client/README.md` — Phase 4 architecture, deprecate HTTP sidecar table for release
- [ ] 4.3 Update `openspec/changes/desktop-monolith/tasks.md` — link to Phase 4 successor

## 5. Verification

- [ ] 5.1 Production DMG: no TCP 3921 listener; no HTTP on UDS after 4B.9
- [ ] 5.2 Home → Runs → local workflow E2E on installed `.app`
- [ ] 5.3 `cargo check` + `backend/tests/test_daemon.py` after `desktop_api` extraction
- [ ] 5.4 Windows/Linux message transport (named pipe / UDS) before declaring 4B complete
