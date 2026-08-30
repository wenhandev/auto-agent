## depends_on

- `record-and-generate` — recording sessions, action traces, and rule-based workflow synthesis.
- `modern-browser-agent-runtime` (soft) — route skills inject prompt constraints at runtime; this change populates them from trajectories.

## Why

Recorded and autonomous browser trajectories already capture intent-bearing actions, but synthesis today is **rule-based only** (`trace_to_graph`) and **route skills are hand-authored**. Browser-BC-style **atomize → classify → bucket → distill** turns repeated demonstrations into reusable prompt knowledge. auto_agent already executes via prompt-shaped nodes (`vision_act`) and route skills; the missing piece is an automated distillation pipeline from trajectories into **draft workflows** and **route skill proposals** the operator can adopt.

## What Changes

- **Trajectory distillation pipeline** (pure Python, rule-based default; optional LLM when configured): atomize a trace into URL-scoped segments, classify each segment into a capability slug, distill segment prompts, and emit route skill proposals.
- **Route skill proposals**: persisted proposals linked to a recording (later: task runs) with `pending` / `adopted` / `dismissed` status; adopt merges into an existing matching route skill or creates a new one.
- **Recording distill API**: `POST /api/recordings/{id}/distill` runs the pipeline; `POST /api/recordings/{id}/generate` also creates proposals alongside the workflow draft.
- **Proposal management API**: list, adopt, dismiss route skill proposals.
- **UI**: recording detail shows distilled route skill proposals with adopt/dismiss actions.
- **Optional LLM workflow distillation**: when an LLM is configured, workflow synthesis may use a distiller agent; otherwise falls back to the existing rule-based graph.

## Capabilities

### New Capabilities

- `trajectory-distillation`: atomize, classify, and distill browser action traces into structured outputs (workflow graph + route prompts).
- `route-skill-proposals`: persisted proposals, adopt/dismiss flow, and merge-into-existing route skill on adopt.

### Modified Capabilities

- `workflow-synthesis` (from `record-and-generate`): generate/distill also emits route skill proposals; optional LLM distillation path for workflow graphs.

## Impact

- **Backend**: `app/services/trajectory_distillation.py`, `RouteSkillProposal` model, `route_skill_proposals` router, recording router updates, optional `app/agents/distiller.py`, tests.
- **Frontend**: recording detail proposals panel, API client types, i18n strings.
- **Runtime**: distill is on-demand (stop recording → distill/generate); no change to execution loop except richer route skills after adopt.
- **Migration**: `create_all` adds `route_skill_proposal`; no breaking API changes.
