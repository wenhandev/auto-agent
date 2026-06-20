## ADDED Requirements

### Requirement: Org-scoped resource access

The system SHALL scope every owned resource (workflows, credentials, runs, triggers, profiles, sessions, webhooks, API keys) to its owning organisation and deny cross-org access.

#### Scenario: List filtered to org

- **WHEN** a user lists workflows
- **THEN** only their organisation's workflows are returned

#### Scenario: Cross-org access returns 404

- **WHEN** a user requests a resource owned by another organisation
- **THEN** the response is HTTP 404 (existence not revealed)

### Requirement: Role-based permissions

The system SHALL enforce role-based permissions: viewers read, members run/edit, admins manage members, owners manage the org.

#### Scenario: Viewer cannot edit

- **WHEN** a viewer attempts to edit a workflow
- **THEN** the operation is denied

#### Scenario: Member can run

- **WHEN** a member starts a run of an org workflow
- **THEN** the run is permitted

### Requirement: Workflow visibility

The system SHALL support workflow `visibility ∈ {private, org}` controlling whether non-owner org members can see and run it.

#### Scenario: Private workflow hidden from other members

- **WHEN** a workflow is `private`
- **THEN** other org members (non-owner) do not see it in lists

#### Scenario: Org-visible workflow shared

- **WHEN** a workflow is `org`-visible
- **THEN** members of the org can see and run it per their role
