## ADDED Requirements

### Requirement: TypeScript client surface

The system SHALL provide a TypeScript SDK exposing `new AutoAgent({ baseUrl, apiKey })` with `runTask`, `runWorkflow`, `getRun`, `cancelRun`, and `waitForRun`, shipped as a typed ESM package.

#### Scenario: Run a task

- **WHEN** a developer calls `await client.runTask({ prompt, url })`
- **THEN** the SDK POSTs to `/api/v1/run-task` with the bearer key and returns a typed run handle

#### Scenario: Wait for completion

- **WHEN** a developer calls `await client.waitForRun(runId)`
- **THEN** the SDK polls to a terminal status and returns the final run

### Requirement: Typed package

The TypeScript SDK SHALL ship type declarations for all public methods and models.

#### Scenario: Types resolve

- **WHEN** the package is imported in a TypeScript project
- **THEN** method signatures and model types resolve without `any`
