## Context

Browser vision (`perception.py` + `VisionAgent`) already provides observe→act with indexed elements. Native desktop needs a parallel stack using macOS Accessibility (AX) / Windows UI Automation (UIA) + screenshots, matching Codex Computer Use. Full design: `docs/superpowers/specs/2026-07-18-macos-computer-use-design.md`.

## Goals / Non-Goals

**Goals:** macOS AX + Windows UIA Computer Use; app allowlist; autonomous tools + `desktop_*` nodes; v1 foreground input; testable FakeBackend.

**Non-Goals:** Linux; background virtual cursor; Locked use; Terminal/cmd/PowerShell/self automation; brittle hand-authored selectors.

## Spec map

| Capability | Spec path | Covers |
|------------|-----------|--------|
| `desktop-computer-use` | `specs/desktop-computer-use/spec.md` | Protocol, platforms, drivers, routing, concurrency |
| `desktop-app-authorization` | `specs/desktop-app-authorization/spec.md` | TCC/hints, Always allow, hard-deny, settings |
| `desktop-perception` | `specs/desktop-perception/spec.md` | Screenshot + indexed AX/UIA → Observation |
| `desktop-action-primitives` | `specs/desktop-action-primitives/spec.md` | Tools, nodes, DesktopAgent, `desktop_step` |

## Decisions

1. **Protocol + drivers** — `DesktopComputerUseBackend` with platform foreground drivers (v1) and later swappable background driver.
2. **AX/UIA + screenshot** — element index preferred; coordinates fallback only.
3. **Auth** — system TCC (macOS) separate from product App allowlist stored locally; Windows uses Always-allow + keep app visible.
4. **Optional extras** — `desktop-macos` (pyobjc) / `desktop-windows` (pywinauto); CI uses FakeBackend.
5. **Browser routing** — existing Playwright session still preferred for web; desktop tools for native apps.

## Risks / Trade-offs

- TCC may require actions from the `.app` process → may need Tauri bridge later.
- Foreground input interrupts the user (accepted for v1).
- AX quality varies for custom-drawn UIs → screenshot fallback.

## Migration

No breaking API changes. New node types and tools are additive. Desktop-only features unavailable on web show clear errors.
