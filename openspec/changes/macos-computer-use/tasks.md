## 0. Specs

- [x] 0.1 Expand proposal capabilities into four specs (computer-use, authorization, perception, action-primitives)
- [x] 0.2 Cover macOS + Windows, routing, concurrency, settings, tools/nodes, `desktop_step`

## 1. Core backend

- [x] 1.1 Implement protocol, forbidden list, app auth store, FakeBackend, factory
- [x] 1.2 Unit tests for auth, forbidden, FakeBackend round-trip

## 2. Agent loop

- [x] 2.1 Implement `desktop_perception` observation builder
- [x] 2.2 Implement `DesktopAgent` (`run_act` / `run_navigate`) emitting `desktop_step`
- [x] 2.3 Tests with FakeBackend

## 3. Autonomous tools

- [x] 3.1 Add DESKTOP_TOOLS to schemas_tasks and wire tool_schemas / LLM tools / _execute_tool
- [x] 3.2 Tests for tool dispatch

## 4. Workflow nodes

- [x] 4.1 Add NodeType literals and executor/scheduler dispatch
- [x] 4.2 Update planner/chat/distiller prompts
- [x] 4.3 Frontend types + params editor for desktop nodes
- [x] 4.4 Node tests with FakeBackend

## 5. macOS driver + settings

- [x] 5.1 Optional pyobjc extras + macOS ForegroundInputDriver
- [x] 5.2 Sidecar/settings API for always-allowed apps + Desktop Settings Card

## 6. Windows driver

- [x] 6.1 Optional pywinauto/Pillow extras + Windows UIA Foreground driver
- [x] 6.2 Factory platform gate for win32; hard-deny cmd/PowerShell/Windows Terminal
- [x] 6.3 Settings hint + unit tests for Windows resolution path

## 7. Spec gap closure

- [x] 7.1 Same-app concurrency lock (`hold_desktop_app` / `DesktopAppBusyError`)
- [x] 7.2 Interactive session / lock-screen diagnostic (`require_interactive_session`)
- [x] 7.3 Desktop tool destructive classification + ConfirmationGate
- [x] 7.4 RunLog / Run Console / Autonomous replay render `desktop_step`

## 8. Verification

- [x] 8.1 Run desktop-related pytest suite and fix failures
