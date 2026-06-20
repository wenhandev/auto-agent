## Description

An integration app is a declarative descriptor: `{app, version, credentials[], resources[{operations[{fields, request, response}]}]}`. Descriptors are loaded from `app/integrations/` into a validated registry at startup. The request template references field and credential values; the response map declares how to turn the HTTP response into output items, optionally with pagination.

## User stories

- **As an integration author**, I want to add an app by writing a descriptor (data), not a bespoke node and frontend form.
- **As the planner**, I want a catalogue of available apps/resources/operations to pick from.
- **As an operator**, I want a malformed descriptor to fail at startup with a precise error, not at run time.

## ADDED Requirements

### Requirement: Descriptor Schema

A descriptor SHALL declare `app`, `version`, `credentials: list[str]` (credential-type names), and `resources`. A resource SHALL declare `name`, `label`, and `operations`. An operation SHALL declare `name`, `label`, `fields: list[Field]`, a `request: RequestTemplate` (method, url template, query, headers, body, body_type), and a `response: ResponseMap` (item_path / root_path / optional pagination).

#### Scenario: Well-formed descriptor loads

- **WHEN** a descriptor with one resource and one GET operation (with a valid `item_path`) is present under `app/integrations/`
- **THEN** the registry SHALL contain the app and expose its resource and operation.

#### Scenario: Operation references its fields in the request

- **WHEN** an operation field `channel` is referenced as `{{$fields.channel}}` in the request body template
- **THEN** the descriptor SHALL be considered valid (the reference resolves against the operation's declared fields).

### Requirement: Registry Loading And Validation At Startup

The backend SHALL load all descriptors at startup into a `registry` keyed by `app`. A descriptor that fails schema validation, references an unknown credential type, or has an operation referencing an undeclared field SHALL fail loading with an error naming the app, the operation, and the problem.

#### Scenario: Unknown credential type rejected

- **WHEN** a descriptor lists a credential type not present in the credential-type registry
- **THEN** startup loading SHALL fail with an error naming the app and the missing credential type.

#### Scenario: Reference to undeclared field rejected

- **WHEN** an operation's request template references `{{$fields.nonexistent}}` not in its `fields`
- **THEN** loading SHALL fail with an error naming the operation and the unknown field.

### Requirement: Catalogue Endpoints

The backend SHALL expose `GET /api/integrations` (list of `{app, version, resources: [{name, operations: [name]}]}`) and `GET /api/integrations/{app}` (the full descriptor minus any executor hooks).

#### Scenario: Catalogue lists apps

- **WHEN** two apps are registered
- **THEN** `GET /api/integrations` SHALL return both with their resources and operation names.

## Out of Scope

- Shipping specific app descriptors (`core-app-integrations`).
- A user-facing visual descriptor builder.
- GraphQL/SOAP request templates (REST/JSON first).
