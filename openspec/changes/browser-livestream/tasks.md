## 1. Capture service

- [x] 1.1 Create `app/services/livestream.py` with a `LivestreamHub` keyed by `run_id`
- [x] 1.2 Open a `CDPSession` on the active page and wire `Page.startScreencast` / `screencastFrame` / `screencastFrameAck` / `stopScreencast`
- [x] 1.3 Implement one-producer → N-viewer fan-out with a per-viewer latest-frame slot
- [x] 1.4 Start on first viewer, stop on last disconnect
- [x] 1.5 Add `STREAM_FPS`, `STREAM_JPEG_QUALITY`, `STREAM_MAX_WIDTH` settings + `.env.example`

## 2. Transport

- [x] 2.1 Add WS route `/ws/stream/{run_id}`
- [x] 2.2 Frame envelope `{ts, seq, width, height}` + base64 JPEG payload
- [x] 2.3 Send `stream_ended` control message on run terminal status
- [x] 2.4 Reject stream connections for non-running runs with a clear close code

## 3. Frontend

- [x] 3.1 Canvas-based `LiveView` component rendering frames with latest-wins
- [x] 3.2 WS client dropping out-of-order/stale frames by `seq`
- [x] 3.3 "实时画面" panel on the run page with FPS/latency readout + fit-to-width toggle
- [x] 3.4 "画面已结束" terminal state on `stream_ended`

## 4. Tests

- [x] 4.1 Hub starts/stops screencast on viewer connect/disconnect
- [x] 4.2 Latest-wins slot never grows unbounded under a slow consumer
- [x] 4.3 `stream_ended` emitted on terminal status
