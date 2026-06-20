## ADDED Requirements

### Requirement: Print-page node

The system SHALL provide a `print_page` node that renders the current page to a PDF stored as an artifact.

#### Scenario: Page saved as PDF

- **WHEN** a `print_page` node runs on a loaded page
- **THEN** a PDF is produced and stored (as an artifact when the artifact store is present, else a temp file) and the node output references it

### Requirement: File-upload node

The system SHALL provide a `file_upload` node that uploads a sandboxed file (or a `file`-typed parameter) into a page file input, locating the input via selector or vision when none is given.

#### Scenario: Upload from sandbox

- **WHEN** a `file_upload` node references a file in the workspace sandbox
- **THEN** the file is set on the target file input and the node completes

#### Scenario: Path traversal rejected

- **WHEN** a `file_upload` source path escapes the sandbox directory
- **THEN** the node fails with a sandbox-violation error

### Requirement: File-download node

The system SHALL provide a `file_download` node that triggers and captures a browser download as a `download` artifact.

#### Scenario: Download captured

- **WHEN** a `file_download` node triggers a download (via selector or vision)
- **THEN** the file is captured and the node output is `{filename, artifact_id, bytes}`
