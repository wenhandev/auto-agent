## Description

A `poll` trigger runs an integration list operation on the scheduler tick, detects new records since the last poll via a dedup key (and provider cursor when available), and enqueues runs for the new records, carrying each record as `run.context`. Poll state is persisted; `on_first_poll` controls backfill behaviour; `min_poll_interval_s` bounds call volume.

## User stories

- **As a workflow author**, I want my workflow to run whenever a new row appears in a Google Sheet or a new Notion DB item is created.
- **As an operator**, I want each new record to trigger exactly one run, not re-fire on every poll.
- **As an operator**, I do not want enabling a poll trigger to fire runs for the entire existing backlog.

## ADDED Requirements

### Requirement: Poll Trigger Type And State

`Trigger.type` SHALL accept `poll`. A poll trigger SHALL store `poll_app`/`poll_resource`/`poll_operation`, `poll_dedup_path`, `poll_cursor`, `last_seen_key`, `poll_mode`, `on_first_poll`, and `min_poll_interval_s`. The poll runner SHALL be registered with the existing scheduler and reconciled on trigger CRUD.

#### Scenario: Poll trigger registered on enable

- **WHEN** a `poll` trigger is created enabled
- **THEN** the scheduler SHALL register a poll job for it AND it SHALL be removed when the trigger is disabled or deleted.

### Requirement: New-Record Detection And Exactly-Once Firing

On each poll, the runner SHALL call the configured list operation, identify records that are new relative to `last_seen_key` (and/or the cursor / recently-seen set), and enqueue runs only for the new records. A record that has already fired SHALL NOT fire again on a subsequent poll.

#### Scenario: Only new records fire

- **WHEN** poll 1 sees records `[A, B]` and poll 2 sees `[A, B, C]`
- **THEN** poll 1 SHALL fire for `A` and `B`, and poll 2 SHALL fire only for `C`.

#### Scenario: No new records fires nothing

- **WHEN** a poll returns only already-seen records
- **THEN** no run SHALL be enqueued.

### Requirement: Per-Record Vs Batched Enqueue

When `poll_mode == "per_record"` the runner SHALL enqueue one run per new record (each with that record as `run.context`). When `poll_mode == "batched"` it SHALL enqueue a single run whose `run.context` contains all new records as items.

#### Scenario: Per-record mode

- **WHEN** two new records are found with `poll_mode="per_record"`
- **THEN** two runs SHALL be enqueued, one per record.

#### Scenario: Batched mode

- **WHEN** two new records are found with `poll_mode="batched"`
- **THEN** one run SHALL be enqueued carrying both records as items.

### Requirement: First-Poll Backfill Control

On the first poll after enable, `on_first_poll` SHALL govern behaviour: `fire_none` (default) records the current state without firing; `fire_latest` fires only the most recent record; `fire_all` fires for every existing record.

#### Scenario: Default first poll fires nothing

- **WHEN** a poll trigger with `on_first_poll="fire_none"` is enabled and the first poll sees 50 existing records
- **THEN** no run SHALL be enqueued AND `last_seen_key` SHALL be set so subsequent new records fire.

### Requirement: Minimum Poll Interval

The runner SHALL NOT poll a trigger more often than `min_poll_interval_s` regardless of the scheduler tick frequency.

#### Scenario: Interval enforced

- **WHEN** the scheduler ticks more frequently than `min_poll_interval_s`
- **THEN** the trigger SHALL be polled at most once per `min_poll_interval_s`.

### Requirement: Triggered Run Carries Record Context

An enqueued poll run SHALL go through the existing `create_queued_run` path with `triggered_by.kind == "poll"` (plus `trigger_id` and a record summary) and `run.context` set to the record(s); `{{run.context.<path>}}` SHALL resolve in downstream nodes.

#### Scenario: run.context resolves

- **WHEN** a poll run fires for a record `{"id": 7, "name": "x"}` and a node references `{{run.context.name}}`
- **THEN** the node SHALL receive `"x"`.

## Out of Scope

- Distributed/multi-process polling.
- Detecting deletions/updates between polls (new-record detection only in v1).
- Streaming provider connections.
