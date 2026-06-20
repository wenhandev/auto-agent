## ADDED Requirements

### Requirement: First-boot migration of existing data

The system SHALL, on first boot after enabling multi-user, create a default organisation and admin and idempotently assign all existing resources to them.

#### Scenario: Existing rows assigned to default org

- **WHEN** an existing single-user install boots with multi-user enabled
- **THEN** all existing workflows/credentials/runs/etc. are assigned to the default org and admin
- **AND** the install continues to work as a one-account organisation

#### Scenario: Backfill runs once

- **WHEN** the backfill has already run (marker present)
- **THEN** it does not run again on subsequent boots

### Requirement: Single-user mode preserves local UX

The system SHALL provide a single-user mode that auto-authenticates the seeded admin to preserve the friction-free local experience.

#### Scenario: Local auto-auth

- **WHEN** `SINGLE_USER_MODE` is enabled
- **THEN** the seeded admin is authenticated automatically and no login screen is required locally
