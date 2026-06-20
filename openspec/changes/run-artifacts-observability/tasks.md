## 1. Artifact store

- [x] 1.1 Add `RunArtifact` SQLModel (`kind`, `path`, `content_type`, `bytes`, `node_id?`, `step_index?`, `deleted_at?`)
- [x] 1.2 Create `app/services/artifacts.py` content-addressed store under `backend/data/artifacts/{run_id}/`
- [x] 1.3 Within-run dedupe of byte-identical artifacts
- [x] 1.4 Add settings `ARTIFACT_RETENTION_DAYS=30`, `MAX_ARTIFACT_BYTES`; create dir in lifespan; gitignore
- [x] 1.5 Retention reaper (delete files, tombstone rows) in lifespan

## 2. Capture wiring

- [x] 2.1 Executor writes node start/end screenshots as artifacts; events carry `artifact_id`
- [x] 2.2 Resolve `vision_step.screenshot_ref` to a durable artifact
- [ ] 2.3 Capture browser downloads (`page.on("download")`) and `file_download` outputs as `download` artifacts
- [ ] 2.4 Optional HAR capture when `record_network` is on

## 3. LLM traces

- [x] 3.1 Wrap per-run LLM calls to emit `llm_trace` artifacts `{model, system, messages, response, tokens, latency_ms}`
- [x] 3.2 Mask credential values via the existing masker before persistence
- [x] 3.3 Link traces to node/step

## 4. Recording

- [ ] 4.1 Add `LlmConfig.record_runs` / `record_network` (additive)
- [ ] 4.2 Mux `browser-livestream` frames to MP4 at run end when ffmpeg present
- [ ] 4.3 Frame-manifest fallback when ffmpeg absent

## 5. API

- [x] 5.1 `GET /api/runs/{id}/artifacts` (filter by kind/node)
- [x] 5.2 `GET /api/runs/{id}/artifacts/{artifact_id}` stream bytes
- [x] 5.3 `GET /api/runs/{id}/artifacts/{artifact_id}/thumbnail`
- [x] 5.4 `RunOut` includes artifact counts by kind

## 6. Frontend

- [ ] 6.1 Run-detail timeline interleaving events + screenshots
- [ ] 6.2 Per-step inspector: screenshot + action + expandable LLM trace
- [x] 6.3 "下载产物" list with re-download
- [ ] 6.4 Recording player (MP4 + frame-manifest fallback)
- [ ] 6.5 API client methods

## 7. Tests

- [x] 7.1 Screenshot artifact + event `artifact_id` linkage; dedupe
- [x] 7.2 Trace masking never leaks secrets
- [x] 7.3 Retention reaper tombstones rows + deletes files
