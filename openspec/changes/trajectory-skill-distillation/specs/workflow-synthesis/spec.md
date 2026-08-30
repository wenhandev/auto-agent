## MODIFIED Requirements

### Requirement: Synthesise a draft workflow

The system SHALL synthesise a valid draft `Workflow` from a recorded action trace, using deterministic nodes where targets are unambiguous and vision nodes where actions are goal-shaped. When distillation runs, the system SHALL also emit route skill proposals for each URL-scoped segment.

#### Scenario: Trace becomes a workflow

- **WHEN** synthesis runs on a recorded trace
- **THEN** it produces a schema-valid `Workflow` with nodes mapped from the recorded actions

#### Scenario: Goal-shaped step becomes vision node

- **WHEN** a recorded action is better expressed as an intent (e.g. search then pick a result)
- **THEN** synthesis emits a `vision_act`/`vision_navigate` node rather than a brittle selector node

#### Scenario: Generate also distills route proposals

- **WHEN** the client generates a workflow from a stopped recording
- **THEN** the system persists route skill proposals alongside the workflow draft

### Requirement: Reviewable draft, no auto-run

The system SHALL open the synthesised workflow as an editable draft with per-node screenshots and a seeded chat, without executing it. Route skill proposals SHALL remain separate until the operator adopts them.

#### Scenario: Draft opens for review

- **WHEN** synthesis completes
- **THEN** the draft opens in the editor with screenshots attached and a seeded refinement chat, and no run starts automatically

#### Scenario: Proposals visible before adopt

- **WHEN** synthesis completes with route skill proposals
- **THEN** the recording detail UI lists pending proposals without modifying route skills
