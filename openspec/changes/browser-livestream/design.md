## Context

The executor drives a single Playwright page. Playwright exposes a raw CDP session via `page.context.new_cdp_session(page)`, which gives access to `Page.startScreencast` / `Page.screencastFrame` / `Page.stopScreencast` — Chrome's native viewport streaming used by DevTools' "Cast" and by Skyvern's livestream. Frames arrive as base64 JPEG/PNG with metadata and must be acknowledged (`Page.screencastFrameAck`) to keep them flowing.

## Goals / Non-Goals

**Goals:**
- Real-time view of the active page during a run, headed or headless.
- Zero cost when nobody is watching.
- Never let image bytes stall the control event stream.

**Non-Goals:**
- Human takeover / input forwarding (v1 is view-only).
- WebRTC / H.264 transport.
- Recording (the same frames *can* feed `run-artifacts-observability`, but recording is that change's concern).

## Decisions

### Decision 1: CDP screencast, not periodic `page.screenshot()`
Use `Page.startScreencast({format:"jpeg", quality, maxWidth, maxHeight, everyNthFrame})`.
- **Why**: screencast pushes frames only when the page actually changes and is far cheaper/smoother than polling `screenshot()` on a timer. It is the same mechanism Skyvern and DevTools use.
- **Alternative rejected**: `setInterval(page.screenshot)` — high CPU, fixed cost even on a static page, no change-driven cadence.

### Decision 2: Separate `/ws/stream/{run_id}` socket
Image frames travel on their own WebSocket, distinct from `/ws/run`.
- **Why**: a slow viewer must never apply backpressure to control events (node_started/failed). Different data rates, different drop policies.

### Decision 3: Latest-wins backpressure, never queue
Each viewer has a single "pending frame" slot; a newer frame overwrites an unsent one. Acks to CDP are sent as frames are received, not gated on viewer delivery.
- **Why**: bounded memory; a lagging tab shows the latest frame, not a growing backlog. Real-time beats completeness for a live view.

### Decision 4: On-demand start/stop
Screencast starts on the first `/ws/stream/{run_id}` connect for a *running* run and stops on the last disconnect.
- **Why**: idle runs cost nothing; matches "watch in real-time" semantics without always-on capture.

### Decision 5: One producer, N viewers
A `LivestreamHub` keyed by `run_id` fans one CDP frame stream out to all viewers of that run.
- **Why**: multiple browser tabs / the operator + a teammate can watch one run without N screencasts.

## Risks / Trade-offs

- [Bandwidth with many viewers / high FPS] → `STREAM_FPS` (default 8) + `STREAM_JPEG_QUALITY` (default 60) + `maxWidth/Height` clamp.
- [Run finishes while viewing] → hub emits a terminal "stream_ended" control message; UI shows "画面已结束".
- [Headless still streams] → confirmed: CDP screencast does not require a visible window; servers get the view.
- [Frame ordering] → `seq` header lets the client drop out-of-order/stale frames.

## Migration Plan

- No DB/schema change. New settings `STREAM_FPS`, `STREAM_JPEG_QUALITY`, `STREAM_MAX_WIDTH`.
- New WS route registered alongside `/ws/run`.

## Open Questions

- Should the stream survive a `vision_navigate` opening a new tab/page? (v1: follow the executor's "active page"; multi-page is future.)
- Expose a still-frame fallback for clients that can't hold a WS? (Defer; a `GET /api/runs/{id}/last-frame` could back a poster image.)
