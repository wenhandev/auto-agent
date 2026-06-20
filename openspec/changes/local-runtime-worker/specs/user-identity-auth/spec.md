## ADDED Requirements

### Requirement: Worker login endpoint

The system SHALL expose `POST /api/v1/workers/login` accepting `{cloud_url implicit, email, password, machine_id?, display_name?, tags?}` that reuses the same credential validation as UI login and returns a worker-scoped session.

#### Scenario: Same password as web UI

- **WHEN** a user logs into the worker with credentials that work on the web login page
- **THEN** worker login succeeds with the same org membership

#### Scenario: Rate limiting

- **WHEN** repeated failed worker login attempts occur
- **THEN** the endpoint applies the same rate limits as UI login
