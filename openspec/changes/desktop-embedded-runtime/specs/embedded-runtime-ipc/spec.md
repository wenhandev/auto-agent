## ADDED Requirements

### Requirement: UI runtime access uses Tauri commands only in release

In production desktop builds, the WebView SHALL NOT perform HTTP or WebSocket requests to loopback addresses for runtime operations. All runtime operations SHALL go through Tauri `invoke` commands or Tauri-emitted events.

#### Scenario: Release build blocks loopback runtime HTTP

- **WHEN** the desktop app is built with a baked-in remote cloud URL
- **THEN** runtime REST and stream access from the WebView uses Tauri invoke/event relay only

#### Scenario: Dev build may use TCP bridge

- **WHEN** the desktop app runs in development mode
- **THEN** the runtime MAY be reached via TCP `127.0.0.1:3921` through the Rust bridge for debugging

### Requirement: Structured runtime message protocol

The Rust parent and Python runtime host SHALL communicate using a versioned structured message envelope (JSON or equivalent), not HTTP, for release desktop IPC.

#### Scenario: Health check over message channel

- **WHEN** the Tauri shell starts the embedded runtime host in release mode
- **THEN** health and status are obtained by sending a typed request message and receiving a typed response without an HTTP server listening on TCP or UDS

### Requirement: Run events and live stream over Tauri events

Local run log events and live browser frames SHALL be delivered to the WebView exclusively via Tauri events after Phase 4B completion.

#### Scenario: Run console subscribes without EventSource

- **WHEN** the user opens the run console for an active local run
- **THEN** the UI subscribes through Tauri invoke and receives `runtime-run-event` and `runtime-stream-frame` events without opening loopback SSE or WebSocket URLs in the WebView

### Requirement: Python desktop API layer

Runtime business logic currently in FastAPI route handlers SHALL be callable from a non-HTTP host entrypoint (`desktop_api` module) so the same code serves CLI, dev HTTP, and release message IPC.

#### Scenario: Session save via shared API

- **WHEN** login completes and session tokens are persisted
- **THEN** the same function used by `POST /session` in dev HTTP mode is invoked by the message host in release mode

### Requirement: Incremental migration with fallback

During Phase 4B implementation, the system SHALL support falling back to the HTTP bridge when the message host is unavailable, controlled by build or runtime configuration, until parity is verified on all target platforms.

#### Scenario: HTTP fallback in dev

- **WHEN** `debug_assertions` is enabled and message IPC is not configured
- **THEN** the existing HTTP runtime bridge continues to work for all runtime endpoints
