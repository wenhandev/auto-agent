## ADDED Requirements

### Requirement: Generate ranked selector candidates from a DOM element

The system SHALL provide a `selector_builder` module that accepts a Playwright `ElementHandle` or DOM node descriptor and returns an ordered list of selector candidates for use in workflow `click` / `fill` nodes.

Each candidate SHALL include:

- `selector` — string usable by `page.locator(selector)` or documented Playwright prefix (`text=`, `role=`)
- `strategy` — one of `id`, `data-testid`, `name`, `aria-label`, `text`, `css-path`
- `confidence` — float in `[0.0, 1.0]` reflecting stability
- `match_count` — integer count of elements matched on the current page

Candidates SHALL be ordered by stability: `id` > `data-testid` > `name` > `aria-label` > `text` > `css-path`.

#### Scenario: Element with data-testid

- **WHEN** the target element has `data-testid="login-submit"`
- **THEN** the first candidate SHALL use strategy `data-testid` with selector `[data-testid="login-submit"]`
- **AND** `confidence` SHALL be `>= 0.9`

#### Scenario: Element with only generated classes

- **WHEN** the target element has no id, testid, name, or aria-label
- **THEN** the builder SHALL produce a `css-path` candidate with maximum depth 4
- **AND** `confidence` SHALL be `< 0.6`

#### Scenario: Non-unique id excluded

- **WHEN** multiple elements share the same `id` attribute
- **THEN** the builder SHALL NOT emit an `id` strategy candidate for that id
- **AND** SHALL fall back to the next applicable strategy

### Requirement: Resolve element at viewport coordinates

The system SHALL resolve the topmost DOM element at viewport coordinates `(x, y)` using `document.elementFromPoint`, with optional 8px-radius search for nearest interactive ancestor if the hit target is a non-interactive wrapper (e.g. `span` inside `button`).

#### Scenario: Click on button text node

- **WHEN** coordinates hit a `span` inside a `button`
- **THEN** the builder SHALL resolve to the enclosing interactive element (`button` or `[role=button]`) when one exists within 3 ancestor levels

#### Scenario: Coordinates outside viewport

- **WHEN** `(x, y)` is outside the page viewport
- **THEN** the builder SHALL return an empty candidate list and a descriptive error

### Requirement: Selector builder is deterministic and side-effect free

The selector builder SHALL NOT invoke LLM services. Given the same DOM state and target element, it SHALL return the same candidate ordering.

#### Scenario: Repeated pick on unchanged page

- **WHEN** pick-element is called twice at the same coordinates without DOM changes
- **THEN** both responses SHALL return identical candidate lists
