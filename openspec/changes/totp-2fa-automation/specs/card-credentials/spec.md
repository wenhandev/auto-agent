## ADDED Requirements

### Requirement: Credit-card credential kind

The system SHALL support a `credit_card` credential kind storing card fields encrypted at rest, returning masked values on all read paths.

#### Scenario: Create a card credential

- **WHEN** a client creates a credential of kind `credit_card` with number/exp/cvc
- **THEN** all fields are stored Fernet-encrypted
- **AND** reads return the number masked to last-4 and the cvc fully masked

### Requirement: Card interpolation token

The system SHALL resolve `{{card.<name>.<field>}}` to the requested card field at action time, subject to per-workflow credential-link enforcement.

#### Scenario: Card number filled into checkout

- **WHEN** a fill node contains `{{card.my-visa.number}}` during a run whose workflow links `my-visa`
- **THEN** the token resolves to the full number only for the page fill, masked everywhere else

#### Scenario: Card never leaked to traces

- **WHEN** a run with a card token writes an LLM trace or run event
- **THEN** the persisted content shows the masked card, never the full number or cvc
