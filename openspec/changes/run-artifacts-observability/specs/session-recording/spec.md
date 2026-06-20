## ADDED Requirements

### Requirement: Optional session recording

The system SHALL optionally record a run's browser session as a playable recording, gated by a configuration toggle, defaulting to off.

#### Scenario: Recording disabled by default

- **WHEN** `LlmConfig.record_runs` is false
- **THEN** no recording artifact is produced for runs

#### Scenario: Recording produced when enabled

- **WHEN** `record_runs` is true and a run executes
- **THEN** a `recording` artifact is produced at run end (MP4 when ffmpeg is available, otherwise a frame manifest)

### Requirement: Recording playback

The run-detail UI SHALL play a run's recording when one exists.

#### Scenario: Play MP4 recording

- **WHEN** a run has an MP4 recording artifact
- **THEN** the run-detail page renders a video player for it

#### Scenario: Frame-manifest fallback playback

- **WHEN** a run has a frame-manifest recording (no ffmpeg)
- **THEN** the UI plays the frames back as a timed image sequence
