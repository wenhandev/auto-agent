## depends_on

- `auto-agent-mvp` — the Chromium singleton, the executor, the `/ws/run` socket.
- `auto-agent-platform` — the `Run` lifecycle and the platform shell that hosts the run page.

Soft synergy with `browser-sessions-profiles` (a live session can be streamed even between runs) and `run-artifacts-observability` (the same frames feed recordings).

## Why

`auto-agent` shows *node glow* and progress text, but the operator cannot **see the actual browser**. When a vision agent makes a surprising click or a page throws an unexpected modal, the only evidence is text events. Skyvern's headline observability feature is **livestreaming**: watch the browser in real time. This is essential for trust ("is it doing the right thing?") and for debugging vision runs where the LLM's chosen action only makes sense against the pixels.

This change streams the live browser viewport to the workflow run page in real time.

## What Changes

- **Capture**: a `app/services/livestream.py` uses Chrome DevTools Protocol **screencast** (`Page.startScreencast`) via Playwright's CDP session to receive JPEG frames as the page renders, throttled to a target FPS.
- **Transport**: frames are pushed over a dedicated WebSocket `/ws/stream/{run_id}` (separate from `/ws/run` so the event stream is not blocked by image bytes). Frames are base64 JPEG with a small header `{ts, seq, width, height}`. Backpressure: if a client is slow, frames are dropped (latest-wins), never queued unbounded.
- **Lifecycle**: streaming starts when a client opens the stream socket for a running run and stops (CDP `stopScreencast`) when the last viewer disconnects, so idle runs pay nothing.
- **Interactive takeover (read-only v1)**: v1 is view-only. The design reserves the input-forwarding channel (mouse/keyboard → `Input.dispatch*`) for a future `live-takeover` change so a human can grab control mid-run.
- **UI**: the run page gains a "实时画面" panel rendering the frames onto a `<canvas>`, with FPS/latency readout, a fit-to-width toggle, and a "画面已结束" state when the run finishes.
- **Headless note**: streaming works in both headed and headless mode (CDP screencast does not require a visible window), so headless servers get a live view too.

## Capabilities

### New Capabilities

- `browser-livestream`: the CDP screencast capture service, the `/ws/stream/{run_id}` frame transport with latest-wins backpressure, on-demand start/stop, and the run-page live-view panel.

### Modified Capabilities

- `live-event-stream` (from `auto-agent-mvp`): documented split — `/ws/run` carries control/progress events, `/ws/stream/{run_id}` carries image frames. No change to the existing event schema.
- `platform-shell` (from `auto-agent-platform`): the run page gains a "实时画面" panel.

## Impact

- **Backend**: new service + new WS route. Uses the existing Playwright `CDPSession` (`page.context.new_cdp_session(page)`); no new dependency. Frame fan-out is one producer → N viewers with a per-viewer latest-frame slot.
- **Frontend**: new canvas-based viewer component; a small WS client with latest-wins rendering. No new dependency (raw `<canvas>` + `WebSocket`).
- **Runtime**: screencast at ~5–10 FPS JPEG (quality-tunable) adds modest CPU on the browser side and bandwidth proportional to viewers; capped FPS + JPEG quality settings bound it. Zero cost when no viewer is attached.
- **Migration**: none (no schema, no DB). New settings `STREAM_FPS=8`, `STREAM_JPEG_QUALITY=60`.
- **Out of scope**: interactive human takeover / input forwarding (reserved for `live-takeover`); WebRTC transport (JPEG-over-WS is enough for a single-user POC); multi-tab streaming (stream the active page only).
