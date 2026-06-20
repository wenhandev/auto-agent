## ADDED Requirements

### Requirement: Recorded events include selector candidates

For `click` and `fill` recording events, the system SHALL store `selector_candidates` produced by `selector_builder` when the target element is resolvable at capture time.

#### Scenario: Click event enriched with candidates

- **WHEN** a click is recorded on an element with `aria-label="Continue"`
- **THEN** the persisted event JSON includes `selector_candidates` with at least one aria-label or equivalent strategy entry

#### Scenario: Sensitive fields unchanged

- **WHEN** a fill is recorded on a password field
- **THEN** sensitive input protection rules remain unchanged
- **AND** `selector_candidates` MAY still be stored without the typed value
