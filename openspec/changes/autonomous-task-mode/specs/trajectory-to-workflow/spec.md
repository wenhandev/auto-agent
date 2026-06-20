## Description

After a successful autonomous run, a synthesizer turns the recorded trajectory into a draft reusable workflow graph (navigate/vision/extract/data nodes), saved as an editable, schedulable workflow in "draft" status. Synthesis is best-effort and labelled as a starting point, not a guaranteed-equivalent replay.

## User stories

- **As a user**, after the agent accomplishes a task once, I want a reusable workflow I can edit and schedule, so the next run is deterministic and cheap.
- **As a user**, I want the draft to prefer vision nodes where the agent relied on reasoning, so it survives page changes.

## ADDED Requirements

### Requirement: Synthesize Draft Workflow From Trajectory

On a successful autonomous run, the system SHALL be able to synthesize a draft workflow graph approximating the trajectory: navigations become `navigate`/`vision_navigate` nodes, actions become `vision_act`/`click`/`fill` nodes, extractions become `extract`/data nodes, connected start→…→end. The draft SHALL be saved as a workflow with `status="draft"`.

#### Scenario: Successful run yields a draft workflow

- **WHEN** an autonomous run finishes successfully and synthesis is requested
- **THEN** a workflow SHALL be created in `status="draft"` whose nodes approximate the trajectory AND `task_finished.synthesized_workflow_id` SHALL reference it.

#### Scenario: Unstable selectors prefer vision nodes

- **WHEN** a trajectory step relied on vision reasoning rather than a stable selector
- **THEN** the synthesized node for that step SHALL be a vision node (`vision_act`/`vision_navigate`), not a brittle selector-based `click`/`fill`.

### Requirement: Synthesis Is Best-Effort And Labelled

The synthesized workflow SHALL be labelled as a draft starting point and SHALL NOT be presented as a guaranteed-equivalent replay; the user SHALL be expected to test before scheduling.

#### Scenario: Draft is clearly marked

- **WHEN** a synthesized workflow is opened
- **THEN** it SHALL be marked as an autonomously-synthesized draft requiring review before scheduling.

## Out of Scope

- Guaranteeing the synthesized graph reproduces the run on a changed page.
- Automatic scheduling of the synthesized workflow without user review.
- Learning/merging multiple trajectories into one optimized workflow.
