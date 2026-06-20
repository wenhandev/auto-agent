## ADDED Requirements

### Requirement: Local draft storage

The desktop app SHALL store workflow drafts locally so the user can create and edit workflows without continuous cloud connectivity.

#### Scenario: Create draft offline

- **WHEN** the user creates a new workflow while offline
- **THEN** the draft is saved to local storage with a stable local identifier
- **AND** the draft is marked as unpublished

#### Scenario: Edit draft offline

- **WHEN** the user edits a local draft while offline
- **THEN** changes persist locally
- **AND** sync to cloud is deferred until the user is online and chooses Publish

### Requirement: Publish to cloud

The desktop app SHALL provide **Publish** to upload the current draft as a new cloud workflow version visible to the org.

#### Scenario: Successful publish

- **WHEN** the user clicks Publish while online
- **THEN** the app uploads the workflow schema to the cloud API
- **AND** records the returned cloud `workflow_id` and `version_id` on the local draft
- **AND** cloud triggers and teammates can use the published version

#### Scenario: Publish while offline

- **WHEN** the user clicks Publish while offline
- **THEN** the app shows an error that publishing requires connectivity
- **AND** does not corrupt local draft state

### Requirement: Pull from cloud

The desktop app SHALL provide **Pull** to replace or merge a local copy with the latest published cloud version.

#### Scenario: Pull latest published version

- **WHEN** the user pulls a workflow that exists on the cloud
- **THEN** the app downloads the latest published version
- **AND** prompts for confirmation before overwriting an unpublished local draft

#### Scenario: Import shared team workflow

- **WHEN** a teammate has published a workflow to the org
- **THEN** the user can pull it into local storage for editing or running on this device
