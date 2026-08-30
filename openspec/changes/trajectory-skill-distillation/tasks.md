## 1. Backend — distillation core

- [x] 1.1 Add `RouteSkillProposal` model and schemas
- [x] 1.2 Implement `app/services/trajectory_distillation.py` (atomize, classify, distill prompt, persist proposals)
- [x] 1.3 Add optional `app/agents/distiller.py` LLM workflow path with rule-based fallback
- [x] 1.4 Wire distillation into `synthesize_from_recording` and recording generate flow

## 2. Backend — APIs

- [x] 2.1 Add `POST /api/recordings/{id}/distill` endpoint
- [x] 2.2 Add `/api/route-skill-proposals` router (list, adopt, dismiss)
- [x] 2.3 Register router in `main.py`

## 3. Tests

- [x] 3.1 Add `test_trajectory_distillation.py` (atomize, classify, distill, adopt merge, API)
- [x] 3.2 Extend recording tests for distill/generate proposals

## 4. Frontend

- [x] 4.1 Add API types and client methods for distill + proposals
- [x] 4.2 Show proposals panel on recording detail with adopt/dismiss
## 6. Phase 3 — merge preview, buckets, desktop

- [x] 6.1 `GET /api/route-skill-proposals/{id}/adopt-preview` merge preview
- [x] 6.2 `GET /api/route-skills/buckets` site/capability bucket view
- [x] 6.3 Adopt dialog showing merged prompt when skill exists
- [x] 6.4 Settings Route Skills tab: list + by-site buckets
- [x] 6.5 Desktop settings embeds Route Skills management
