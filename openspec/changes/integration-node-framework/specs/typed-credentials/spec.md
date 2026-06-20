## Description

Credentials gain a typed model: a credential *type* declares fields (some `secret`) and an auth-injection strategy (`api_key_header`, `api_key_query`, `bearer`, `basic`, `oauth2`, `none`). The framework injects auth into rendered requests from the encrypted vault. OAuth2 supports an authorization-code connect flow and lazy token refresh. Existing untyped credentials map to a `generic` type.

## User stories

- **As an operator**, I want to store a Slack OAuth2 credential and have the framework attach the right header automatically.
- **As an operator**, I want an API-key credential to inject as a header or query param per the app's needs, without editing request templates.
- **As an existing user**, I want my current key-value credentials to keep working.

## ADDED Requirements

### Requirement: Typed Credential Types And Fields

A credential type SHALL declare `type`, `fields: list[Field]` (secret fields flagged), and an `auth: AuthSpec`. A stored credential instance SHALL carry its `type`; secret field values SHALL remain in the existing encrypted vault. An existing untyped credential SHALL be treated as type `generic` with `auth.strategy = "none"`.

#### Scenario: Generic backward compatibility

- **WHEN** a pre-existing untyped key-value credential is referenced via `{{cred.<name>.<field>}}`
- **THEN** it SHALL resolve exactly as before AND no auto-injection SHALL occur.

### Requirement: Auth Injection Strategies

At request time the framework SHALL inject auth per the credential type's `strategy`: `api_key_header` adds a named header; `api_key_query` adds a named query param; `bearer` adds `Authorization: Bearer <token>`; `basic` adds HTTP Basic; `none` injects nothing. Injection SHALL read decrypted values from the vault and SHALL be redacted in events.

#### Scenario: API key as header

- **WHEN** a credential type uses `api_key_header` with header `X-Api-Key` and the instance's key field is `"abc"`
- **THEN** the rendered request SHALL include `X-Api-Key: abc` AND the event SHALL show `X-Api-Key: ***`.

#### Scenario: Basic auth

- **WHEN** a `basic` credential has user `u` and pass `p`
- **THEN** the request SHALL include a correct `Authorization: Basic <base64(u:p)>` header.

### Requirement: OAuth2 Connect And Lazy Refresh

For `oauth2` credentials the backend SHALL provide an authorization-code connect flow (`/api/oauth2/{app}/connect` → provider authorize → `/callback` exchanges the code for tokens stored in the vault) with a signed `state` validated on callback. Before injecting a bearer token whose `expires_at` is within the skew window, the framework SHALL refresh it using the refresh token and update the vault.

#### Scenario: Connect stores tokens

- **WHEN** a user completes the OAuth2 connect flow for an app
- **THEN** the credential instance SHALL hold `access_token`, `refresh_token`, and `expires_at` in the encrypted vault.

#### Scenario: Expired token refreshed before use

- **WHEN** an operation runs and the stored `access_token` is expired but a refresh token is present
- **THEN** the framework SHALL refresh the token before the call AND persist the new token.

#### Scenario: Callback rejects bad state

- **WHEN** the OAuth2 callback arrives with a `state` that fails signature validation
- **THEN** the callback SHALL reject the exchange with an error and SHALL NOT store any token.

### Requirement: Descriptor-Driven Credential UI

Credential forms SHALL be generated from the credential type's `fields`; OAuth2 types SHALL render a "Connect <app>" action that drives the connect flow.

#### Scenario: Form generated from fields

- **WHEN** a credential type declares fields `[api_key (secret), workspace (string)]`
- **THEN** the credential form SHALL render a masked input for `api_key` and a text input for `workspace` with no per-app frontend code.

## Out of Scope

- OAuth1 / mTLS / request-signing schemes (REST + the five listed strategies first).
- Per-user (multi-tenant) credential isolation beyond what `per-workflow-credentials` provides.
