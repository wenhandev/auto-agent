## ADDED Requirements

### Requirement: Page perception capture

The system SHALL provide a perception service that, given a live Playwright `page`, captures a viewport screenshot and the accessibility-tree snapshot and returns a single observation object.

#### Scenario: Capture produces screenshot and a11y tree

- **WHEN** the perception service is invoked on a loaded page
- **THEN** it returns an observation containing a PNG screenshot reference and a serialised accessibility snapshot
- **AND** the observation includes the current page URL and title

#### Scenario: Capture on a blank page

- **WHEN** the perception service is invoked before any navigation (`about:blank`)
- **THEN** it returns an observation with an empty interactive-element list and does not raise

### Requirement: Indexed interactive-element map

The perception service SHALL build a stable, zero-based indexed list of interactive elements (links, buttons, inputs, selects, and ARIA-interactive roles), each entry carrying its index, role, accessible name, and a resolvable handle signature.

#### Scenario: Elements are numbered

- **WHEN** a page exposes three interactive elements
- **THEN** the observation lists them as indices `0`, `1`, `2` with role and accessible name
- **AND** each index can be resolved back to a concrete element handle at action time

#### Scenario: Index resolution after minor DOM mutation

- **WHEN** the agent requests an action on index `N` and the DOM mutated since capture
- **THEN** the service re-resolves index `N` by its captured a11y signature
- **AND** IF resolution fails THEN the service re-perceives the page once before reporting the element as unavailable

### Requirement: Compact observation payload

The perception service SHALL package the observation into a token-bounded payload suitable for an LLM, including the indexed element list and the screenshot, omitting non-interactive boilerplate.

#### Scenario: Payload omits non-interactive noise

- **WHEN** a page contains large blocks of static text and scripts
- **THEN** the compact payload includes interactive elements and a truncated text summary, not the full DOM
