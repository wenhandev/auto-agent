## Why

Today the desktop app requires **three manual terminals** in dev: cloud backend (`8001`), Python sidecar (`3921`), and Tauri. Users expect **one click** — open the app and everything runs. The gap between developer workflow and product expectation blocks onboarding and demo flows.

## What Changes

- Tauri parent process **auto-spawns** local cloud (`127.0.0.1:8001`) and runtime sidecar (`127.0.0.1:3921`) on launch.
- Desktop UI **RuntimeGate** waits for both services before showing login.
- Login form defaults to `http://127.0.0.1:8001` (already present; messaging updated).
- Release builds will bundle PyInstaller binaries for cloud + sidecar inside `.app` / installer (stub + docs in v1).

## Goals

- Single app launch starts cloud + sidecar without manual terminals.
- Dev and release share the same spawn lifecycle (source venv in dev, bundled binaries when present).
- Clean shutdown: quitting the app stops child processes.

## Non-Goals

- Replacing cloud with fully offline mode.
- Bundling PyInstaller cloud binary in this change (documented future step).
- Auto-update installer or store distribution.

## depends_on

- `desktop-app` — Tauri shell, sidecar daemon, SidecarGate baseline.
