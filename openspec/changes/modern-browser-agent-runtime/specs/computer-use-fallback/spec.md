## ADDED Requirements

### Requirement: Provider-neutral Computer Use controller

The system SHALL define a provider-neutral Computer Use controller that can execute screenshot and coordinate-based UI actions through a configured local or external provider.

#### Scenario: Controller exposes coordinate actions

- **WHEN** a Computer Use controller is configured
- **THEN** it supports screenshot, click-at, type-text, scroll, keypress, drag, and wait actions through a common interface

#### Scenario: Provider unavailable reports clear error

- **WHEN** Computer Use fallback is requested but no compatible provider is configured
- **THEN** the system returns a clear provider-unavailable error
- **AND** does not silently continue with an unsafe or unconfigured fallback

### Requirement: Fallback-only execution

The system SHALL use Computer Use as a fallback path, not as the default browser action path.

#### Scenario: Structured action succeeds

- **WHEN** cache, selector, ref, DOM, or perception-based action execution succeeds
- **THEN** the system does not invoke Computer Use for that step

#### Scenario: Structured action unsuitable

- **WHEN** structured action execution fails or the page area is unsuitable for structural targeting, such as canvas-only UI or inaccessible iframe content
- **THEN** the system may invoke Computer Use if enabled by configuration and allowed by guardrails

### Requirement: Computer Use safety and audit

The system SHALL apply existing safety controls and artifact logging to every Computer Use fallback action.

#### Scenario: Fallback action records audit artifacts

- **WHEN** Computer Use executes an action
- **THEN** the system records the provider, reason for fallback, screenshot artifact, action payload, result, and current URL in the run timeline

#### Scenario: High-risk fallback respects confirmation

- **WHEN** a Computer Use action is classified as destructive or high-impact under existing confirmation rules
- **THEN** the system pauses for human approval before executing the action

#### Scenario: Fallback respects domain constraints

- **WHEN** a Computer Use action would navigate or cause navigation outside allowed domains
- **THEN** the system blocks or fails the action according to the existing domain guardrail
