## Context

`RunEvent` rows already capture the control-flow story as JSON. What's missing is the *evidence*: pixels, prompts, files. Skyvern attaches all of these to every run. We add a durable artifact store and link artifacts to the existing event/step model rather than inflating `RunEvent.payload_json` with blobs.

## Goals / Non-Goals

**Goals:**
- Durable, inspectable evidence per run: screenshots, LLM traces, downloads, optional recording + HAR.
- Cheap-by-default: traces always (small), screenshots per step, recording opt-in.
- Reproducibility: an LLM trace lets you see exactly what the model was asked and answered.

**Non-Goals:**
- Cloud object storage (local disk only here).
- Cross-run analytics/search over traces.
- Cost aggregation (that's `run-cost-tracking`, which reads the same trace token counts).

## Decisions

### Decision 1: Artifacts are files + an index row, not DB blobs
Bytes live under `backend/data/artifacts/{run_id}/{kind}/{seq}.<ext>`; a `RunArtifact` row indexes them.
- **Why**: SQLite is a poor blob store; files stream efficiently and are easy to reap.
- **Alternative rejected**: base64 in `RunEvent.payload_json` (bloats the event stream that `browser-livestream` deliberately kept lean).

### Decision 2: Screenshot reference indirection
Events carry an `artifact_id`, not bytes. `vision-action-mode`'s transient `screenshot_ref` resolves to a `RunArtifact` once this change lands.
- **Why**: keeps the WS event stream small; the UI lazy-loads images.

### Decision 3: LLM traces always on, masked
Every per-run LLM call writes a trace `{model, system, messages, response, tokens, latency_ms}`, with credential values masked via the existing masker before persistence.
- **Why**: traces are small and are the single most useful debugging artifact for vision runs. Masking prevents secret leakage into the trace file.
- **Alternative rejected**: trace only on failure (you usually need the *successful-but-wrong* trace too).

### Decision 4: Recording is opt-in, ffmpeg-optional
`LlmConfig.record_runs` gates recording. With ffmpeg present, screencast frames are muxed to MP4 at run end; without it, a frame manifest is stored and the client plays it back as a timed image sequence.
- **Why**: recording is disk-heavy; many users only want screenshots. ffmpeg may be absent on a dev box.

### Decision 5: Content-addressed dedupe within a run
Identical consecutive screenshots (hash-equal) are stored once and referenced N times.
- **Why**: a vision loop that "waits" produces identical frames; dedupe saves disk.

### Decision 6: Retention reaper, tombstoned rows
`ARTIFACT_RETENTION_DAYS` reaper deletes files past the window and marks `RunArtifact.deleted_at`; rows survive so run history stays coherent ("产物已过期清理").
- **Why**: bounded disk without breaking historical run views.

## Risks / Trade-offs

- [Disk growth] → per-step screenshots + retention reaper + dedupe + opt-in recording.
- [Secret leakage into traces] → mandatory masking pass before write; unit-tested.
- [ffmpeg absent] → frame-manifest fallback; no hard dependency.
- [Large downloads as artifacts] → a `MAX_ARTIFACT_BYTES` cap; oversize downloads are linked by path with a "过大未内联" note.

## Migration Plan

- `create_all` makes `run_artifact`. `LlmConfig` gains `record_runs`, `record_network` (additive, default false).
- New `backend/data/artifacts/` (gitignored). New settings `ARTIFACT_RETENTION_DAYS=30`, `MAX_ARTIFACT_BYTES`.
- Existing runs have no artifacts; UI shows "无产物（此运行早于产物功能）".

## Open Questions

- Mux recording live (during run) vs. at end from stored frames? (Lean: at end, from `browser-livestream` frames, to avoid double CPU during the run.)
- Should planner (authoring-time) LLM calls also get traces? (v1: run-time only; authoring traces are a future editor-observability concern.)
