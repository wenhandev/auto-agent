## ADDED Requirements

### Requirement: Artifact store and index

The system SHALL persist run artifacts as files under a per-run directory and index each with a `RunArtifact` row recording kind, path, content type, size, and optional node/step linkage.

#### Scenario: Screenshot artifact stored per step

- **WHEN** a node or vision step produces a screenshot during a run
- **THEN** a file is written under `backend/data/artifacts/{run_id}/...` and a `RunArtifact` row of `kind=screenshot` is created linked to the node/step
- **AND** the corresponding event references the artifact by `artifact_id`

#### Scenario: Identical consecutive frames deduped

- **WHEN** two consecutive screenshots are byte-identical
- **THEN** the bytes are stored once and referenced by both steps

### Requirement: Download capture

The system SHALL capture files downloaded by the browser or by file nodes as `download` artifacts available for re-download.

#### Scenario: Browser download captured

- **WHEN** a page triggers a file download during a run
- **THEN** the file is stored as a `download` artifact and listed on the run detail page

#### Scenario: Oversize download not inlined

- **WHEN** a download exceeds `MAX_ARTIFACT_BYTES`
- **THEN** the artifact row is created with a note that the file was too large to inline and a path reference is kept

### Requirement: Artifact API

The system SHALL expose endpoints to list a run's artifacts (filterable by kind/node), stream an artifact's bytes, and fetch an image thumbnail.

#### Scenario: List and fetch

- **WHEN** a client requests `GET /api/runs/{id}/artifacts?kind=screenshot`
- **THEN** it receives the screenshot artifact index for the run
- **AND** `GET /api/runs/{id}/artifacts/{artifact_id}` streams the bytes with the correct content type

### Requirement: Retention reaper

The system SHALL delete artifact files older than `ARTIFACT_RETENTION_DAYS` while tombstoning their index rows so run history stays coherent.

#### Scenario: Old artifacts reaped

- **WHEN** an artifact is older than the retention window
- **THEN** its file is deleted and its `RunArtifact.deleted_at` is set
- **AND** the run detail shows a "产物已过期清理" placeholder instead of a broken link
