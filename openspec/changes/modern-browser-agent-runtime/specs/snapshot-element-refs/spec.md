## ADDED Requirements

### Requirement: Snapshot element refs

The system SHALL assign short-lived refs to interactive elements in fresh page observations so agents can target elements more deterministically than by numeric index alone.

#### Scenario: Observation includes refs

- **WHEN** perception returns interactive elements
- **THEN** each actionable element includes a ref, role, label/name, index, and signature metadata
- **AND** existing numeric indices remain available for backward compatibility

#### Scenario: Refs are observation-bound

- **WHEN** a ref is produced from an observation
- **THEN** it is valid only after revalidation against the latest observation for the same run/session context
- **AND** it is not treated as a permanent selector cache key by default

### Requirement: Ref-based action targeting

The system SHALL allow click, type, select, drag, and related actions to target a current valid ref in addition to an element index.

#### Scenario: Valid ref executes action

- **WHEN** an action references a ref that resolves with sufficient confidence in the latest observation
- **THEN** the system executes the action on the resolved element
- **AND** records the ref and resolved element metadata in the run event

#### Scenario: Invalid ref falls back safely

- **WHEN** an action references a ref that cannot be resolved or fails confidence checks
- **THEN** the system does not act on stale page state
- **AND** it either falls back to current observation resolution or returns a clear ref resolution error

### Requirement: Ref cache integration

The system SHALL allow successful ref-based actions to inform selector/action cache write-through without making the ref itself the long-lived replay artifact.

#### Scenario: Successful ref action writes cacheable plan

- **WHEN** a ref-based action succeeds and the action is eligible for caching
- **THEN** the system writes a selector or action plan derived from the resolved current element
- **AND** cache eviction/miss policies continue to apply to the derived plan
