# macOS Computer Use Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship macOS Computer Use (AX + screenshot, app allowlist, autonomous tools + desktop_* workflow nodes) aligned with `docs/superpowers/specs/2026-07-18-macos-computer-use-design.md`.

**Architecture:** `DesktopComputerUseBackend` protocol with Fake (tests) + macOS Foreground driver; `desktop_perception` mirrors browser `perception`; tools/nodes call the same backend; Tauri settings later for TCC UX.

**Tech Stack:** Python 3.11+, optional pyobjc (Cocoa/Quartz/ApplicationServices), existing autonomous/vision/executor patterns, FastAPI desktop sidecar, React desktop settings.

## Global Constraints

- macOS only in v1; non-macOS raises clear unavailable error
- v1 foreground input; Backend protocol must allow BackgroundCursorDriver later
- Hard-deny: Terminal, Auto Agent itself, system permission dialogs
- App auth: Allow once / Always allow / Deny; Always allow local-only
- Prefer element index over coordinates
- Do not break existing browser vision / Playwright computer_use fallback

---

## Task 1: Backend protocol + app auth + FakeBackend

**Files:**
- Create `backend/app/services/desktop_computer_use/__init__.py`
- Create `backend/app/services/desktop_computer_use/protocol.py`
- Create `backend/app/services/desktop_computer_use/auth.py`
- Create `backend/app/services/desktop_computer_use/forbidden.py`
- Create `backend/app/services/desktop_computer_use/fake.py`
- Create `backend/app/services/desktop_computer_use/factory.py`
- Create `backend/tests/test_desktop_computer_use_auth.py`
- Create `backend/tests/test_desktop_computer_use_fake.py`

- [ ] Write failing tests for allowlist + forbidden apps + FakeBackend get_app_state/click/type
- [ ] Implement modules until tests pass

## Task 2: desktop_perception + DesktopAgent loop

**Files:**
- Create `backend/app/services/desktop_perception.py`
- Create `backend/app/agents/desktop.py`
- Create `backend/tests/test_desktop_agent.py`

- [ ] Indexed observation from FakeBackend state
- [ ] `run_act` / `run_navigate` emitting `desktop_step` via emit callback

## Task 3: Wire autonomous tools

**Files:**
- Modify `backend/app/schemas_tasks.py`
- Modify `backend/app/agents/autonomous.py`
- Modify `backend/app/agents/autonomous_llm.py`
- Create `backend/tests/test_desktop_autonomous_tools.py`

- [ ] Add DESKTOP_TOOLS to defaults (or opt-in when platform supports)
- [ ] tool_schemas + _build_tools + _execute_tool

## Task 4: Workflow desktop_* nodes

**Files:**
- Modify `backend/app/schemas.py`
- Modify `backend/app/executor.py`
- Modify `backend/app/exec/scheduler.py` (classification)
- Modify planner/chat/distiller prompts lightly
- Create `backend/tests/test_desktop_nodes.py`
- Modify `frontend/src/types.ts` + NodeParamsEditor + palette as needed

- [ ] Add node types and executor dispatch
- [ ] Minimal frontend type/params support

## Task 5: macOS driver + optional deps + settings API stub

**Files:**
- Create `backend/app/services/desktop_computer_use/macos.py`
- Modify `backend/pyproject.toml` optional `desktop-macos`
- Modify desktop sidecar settings endpoints + Desktop Settings Card (permissions + allowlist)

- [ ] Real list_apps/open/get_app_state/click/type when pyobjc present
- [ ] Settings list/revoke always-allowed apps

## Task 6: Verification

- [ ] Run targeted pytest suite for desktop_* tests
- [ ] Smoke: FakeBackend path through autonomous tool execution
