## ADDED Requirements

### Requirement: Best-effort anti-bot context tweaks

The system SHALL support optional context fingerprint tweaks (user agent, locale, timezone, viewport) and a stealth init-script toggle, documented as best-effort and not a bypass guarantee.

#### Scenario: Stealth masks obvious automation tells

- **WHEN** `ANTIBOT_STEALTH` is enabled
- **THEN** an init script is injected that masks the most obvious automation indicators (e.g. `navigator.webdriver`)

#### Scenario: Configurable fingerprint

- **WHEN** a run/session specifies a user agent, locale, timezone, or viewport
- **THEN** the browser context is created with those values

#### Scenario: Disabled by default

- **WHEN** no anti-bot options are configured
- **THEN** context creation is unchanged from default behaviour
