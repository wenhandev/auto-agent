## depends_on

- `auto-agent-platform` — `Run` / `RunEvent` tables, `services.runs`, run-detail UI.
- `vision-action-mode` (soft) — `vision_step` events reference `screenshot_ref`s that this change makes durable. Ships without it (browser action nodes still produce screenshots), but the two are designed together.

Soft synergy with `browser-livestream` (the same JPEG frames can be muxed into the session recording).

## Why

Today a run leaves behind a `RunEvent` stream of JSON — useful, but you cannot *see* what happened. Skyvern's observability is the gold standard: per-step **screenshots**, a step-by-step **action log**, full **session recordings** (video), downloaded-file **artifacts**, and **LLM diagnostic traces** (the exact prompt/response per decision). When a run goes wrong, you open the run and look at the pixels and the prompt, not just the text.

This change adds a durable **artifact store** and the run-detail surfaces to make every run fully inspectable and reproducible.

## What Changes

- **Artifact store** `app/services/artifacts.py`: a content-addressed file store under `backend/data/artifacts/{run_id}/...` with a `RunArtifact` index row (`id`, `run_id`, `node_id?`, `step_index?`, `kind`, `path`, `content_type`, `bytes`, `created_at`). `kind ∈ {screenshot, recording, dom_snapshot, llm_trace, download, har}`.
- **Per-step screenshots**: the executor writes a screenshot artifact for each node start/end and each `vision_step`, replacing the transient `screenshot_ref` with a durable artifact id.
- **LLM diagnostic traces**: every LLM call made during a run (planner is excluded; per-run agent calls included) writes an `llm_trace` artifact `{model, system, messages, response, tokens, latency_ms}` linked to the node/step. Secrets in the prompt are masked using the credential masker.
- **Session recording**: optionally mux the livestream/screencast JPEG frames into an MP4 (or store a frame manifest + lazy client-side playback when ffmpeg is absent). Toggle `LlmConfig.record_runs` (default off to save disk).
- **Download capture**: files downloaded by the browser (`page.on("download")`) and by `file_download` nodes are stored as `download` artifacts and surfaced for re-download.
- **HAR (optional)**: when `record_network` is on, the context records a HAR, stored as an artifact.
- **API**: `GET /api/runs/{id}/artifacts` (list, filterable by kind/node), `GET /api/runs/{id}/artifacts/{artifact_id}` (stream bytes), `GET /api/runs/{id}/artifacts/{artifact_id}/thumbnail`.
- **UI**: the run-detail page gains a **timeline** view interleaving events + screenshots; a per-step inspector showing the screenshot, the action, and (expandable) the LLM trace; a "下载产物" list; and a recording player when a recording exists.
- **Retention**: a configurable `ARTIFACT_RETENTION_DAYS` reaper deletes old artifacts; the `RunArtifact` rows are tombstoned, not removed, so the run history stays consistent.

## Capabilities

### New Capabilities

- `run-artifacts`: the artifact store, the `RunArtifact` index, per-step screenshot capture, download capture, HAR, retention reaper, and the artifact API.
- `llm-diagnostic-traces`: per-call masked LLM trace artifacts linked to node/step, and the trace inspector UI.
- `session-recording`: optional MP4/frame-manifest recording gated by a config toggle, plus the recording player.

### Modified Capabilities

- `run-history` (from `auto-agent-platform`): run-detail grows the timeline + artifact surfaces; `RunOut` includes artifact counts by kind. The `RunEvent` stream is unchanged; artifacts are referenced by id.
- `runtime-llm-config` (from `auto-agent-platform`): `LlmConfig` gains `record_runs: bool` and `record_network: bool`.
- `live-event-stream` (from `auto-agent-mvp`): `vision_step` / node events carry a durable `artifact_id` for their screenshot instead of a transient ref.

## Impact

- **Backend**: new service + one model + one router. Optional `ffmpeg` dependency (degrades to frame-manifest playback when absent). Screenshot writes add ~50–200 KB per step to disk. Masking reuses the credential masker.
- **Frontend**: a substantial run-detail upgrade (timeline, step inspector, trace viewer, downloads, recording player). New API client methods.
- **Runtime**: per-step screenshot + trace writes add small I/O per node; recording adds CPU only when enabled. Retention reaper bounds disk.
- **Migration**: `create_all` makes `run_artifact`; `LlmConfig` columns added (additive). New `backend/data/artifacts/` dir (gitignored). New settings `ARTIFACT_RETENTION_DAYS=30`.
- **Out of scope**: object-storage backends (S3/Azure) for artifacts (local disk only; `download_to_s3` block is separate); a global cross-run search over traces; PII redaction beyond credential masking.
