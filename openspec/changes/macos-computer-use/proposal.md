## Why

Auto Agent today automates browsers (Playwright + vision) but cannot operate native desktop apps. Users need Codex-style Computer Use on **macOS and Windows**: see the screen, click/type via accessibility APIs, and drive authorized applications from autonomous tasks and workflows.

## What Changes

- Add Computer Use backends: macOS (AX) and Windows (UIA), window screenshot, foreground input in v1
- Per-app authorization (Allow once / Always allow / Deny) with local Always-allow storage
- Autonomous tools: `list_apps`, `open_app`, `get_app_state`, `desktop_click`, `desktop_type`, `desktop_key`, `desktop_scroll`
- Workflow nodes: `desktop_open`, `desktop_act`, `desktop_navigate`, `desktop_extract` with `desktop_step` events
- Desktop Settings surface for system permissions guidance and Always-allow management
- Optional extras: `desktop-macos` (pyobjc), `desktop-windows` (pywinauto/Pillow); FakeBackend for tests

## Capabilities

### New Capabilities

- `desktop-computer-use`: platform gate, backend protocol, macOS AX / Windows UIA foreground drivers, browser-vs-desktop routing, concurrency and runtime constraints
- `desktop-app-authorization`: system-permission guidance, per-app Allow once / Always allow / Deny, local Always-allow store, hard-deny list, settings API/UI
- `desktop-perception`: window screenshot + accessibility-tree indexed element map mapped into Observation
- `desktop-action-primitives`: autonomous desktop tools, `desktop_*` workflow nodes, `DesktopAgent` loops, `desktop_step` events

### Modified Capabilities

- (none in archived `openspec/specs/`; autonomous and workflow schema changes are covered by the new capability requirements)

## Impact

- `backend/app/services/desktop_computer_use/` (incl. `macos.py`, `windows.py`), `desktop_perception.py`, `agents/desktop.py`
- `schemas.py`, `schemas_tasks.py`, `autonomous.py`, `autonomous_llm.py`, `executor.py`
- Desktop client settings + optional Tauri permission bridge
- `pyproject.toml` optional `desktop-macos` / `desktop-windows` extras
