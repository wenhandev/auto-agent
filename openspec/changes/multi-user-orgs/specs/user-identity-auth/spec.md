## ADDED Requirements

### Requirement: Users and organisations

The system SHALL model users, organisations, and memberships with roles `owner`/`admin`/`member`/`viewer`.

#### Scenario: User belongs to an org with a role

- **WHEN** a user is a member of an organisation
- **THEN** their membership carries a role that governs their permissions in that org

### Requirement: Authentication

The system SHALL authenticate UI users via email+password issuing a session token, and integrations via org-scoped API keys.

#### Scenario: UI login

- **WHEN** a user logs in with valid credentials
- **THEN** an httpOnly session token is issued and subsequent UI requests are authenticated

#### Scenario: Invalid login rejected and rate-limited

- **WHEN** repeated invalid login attempts occur
- **THEN** they are rejected and rate-limited

#### Scenario: Org-scoped API key

- **WHEN** an integration calls `/api/v1` with an org-scoped key
- **THEN** requests are authorised within that key's organisation only

### Requirement: Bootstrap admin, never open

The system SHALL create a default organisation and an administrator on first boot and require authentication on all routes thereafter.

#### Scenario: Seeded admin on first boot

- **WHEN** the platform boots for the first time with multi-user enabled
- **THEN** a default org and an admin user are created (from env or a printed one-time password)
- **AND** unauthenticated access to protected routes is denied
