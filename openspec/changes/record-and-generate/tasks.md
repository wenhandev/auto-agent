## 1. Recording

- [x] 1.1 Add `Recording` SQLModel (trace + linked artifacts)
- [x] 1.2 Create `app/services/recording.py`: instrument a live session (CDP `Input` + injected DOM listeners)
- [x] 1.3 Capture actions with perception element index + accessible description + screenshot
- [x] 1.4 Detect + drop sensitive-field values (password / one-time-code)
- [x] 1.5 Routes: `POST /api/recordings` (start), stop, get trace

## 2. Synthesis

- [x] 2.1 Create `app/agents/synthesizer.py` (ADK `LlmAgent`) consuming trace + sampled screenshots
- [x] 2.2 Emit deterministic nodes where unambiguous; vision nodes where goal-shaped
- [x] 2.3 Infer `{{params.<name>}}` from non-sensitive typed values (recorded value = default)
- [x] 2.4 Convert sensitive entry to a `login` node (prompt for credential)
- [x] 2.5 Validate the synthesised `Workflow` against the schema
- [x] 2.6 Route: `POST /api/recordings/{id}/synthesize` → new draft workflow + seeded chat

## 3. Frontend

- [x] 3.1 "录制" page with livestream + record/stop control
- [x] 3.2 Live step list building during recording
- [x] 3.3 "生成工作流" button → synthesis → navigate to draft with per-node screenshots

## 4. Tests

- [x] 4.1 Trace capture fidelity on a fixture page
- [x] 4.2 Sensitive-field masking (never stored)
- [x] 4.3 Synthesis produces a valid Workflow
- [x] 4.4 Parameter inference + login-node conversion
