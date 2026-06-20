## ADDED Requirements

### Requirement: Relayed screencast source

For worker-mode runs, live viewport frames SHALL originate from worker-uploaded JPEG frames ingested by the cloud livestream hub instead of in-process CDP screencast.

#### Scenario: Viewer cannot distinguish source

- **WHEN** a client connects to `/ws/stream/{run_id}` for a worker-mode run
- **THEN** frames are delivered with the same `{ts, seq, width, height}` envelope as in-process runs

#### Scenario: In-process path unchanged

- **WHEN** a cloud-mode run executes
- **THEN** livestream behavior remains identical to the original browser-livestream spec
