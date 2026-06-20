## 1. OpenSpec

- [x] 1.1 Create `openspec/changes/desktop-monolith/` (proposal, design, tasks)

## 2. Tauri auto-spawn

- [x] 2.1 Spawn local cloud on setup: `uvicorn app.main:app --host 127.0.0.1 --port 8001`
- [x] 2.2 Extend sidecar spawn (dev + release when binary exists)
- [x] 2.3 Use `resolve_python_path()` → `backend/.venv/bin/python`
- [x] 2.4 Stop cloud + sidecar on app exit
- [ ] 2.5 Release: bundle `auto-agent-cloud` PyInstaller binary (future)

## 3. Desktop UI

- [x] 3.1 Default login cloud URL `http://127.0.0.1:8001`
- [x] 3.2 Replace SidecarGate with RuntimeGate (cloud + sidecar health)
- [x] 3.3 Remove manual-start messaging from splash / error screens
- [x] 3.4 Optional: sidecar `GET /ready` checks cloud reachable

## 4. Docs

- [x] 4.1 Update `desktop/README.md` — mono architecture, one-click launch
- [x] 4.2 Document future PyInstaller cloud bundle in release checklist

## 5. Verification

- [ ] 5.1 Kill 8001/3921, `npm run tauri:dev` — both services auto-start
- [ ] 5.2 `npm run build` in `desktop/` passes
- [ ] 5.3 Backend tests if daemon touched
