## ADDED Requirements

### Requirement: CAPTCHA detection

The system SHALL detect likely CAPTCHA challenges during perception and emit a `captcha_detected` event with the kind and a screenshot artifact.

#### Scenario: reCAPTCHA detected

- **WHEN** a page presents a reCAPTCHA/hCaptcha/Turnstile challenge
- **THEN** perception flags `captcha: {present: true, kind}` and a `captcha_detected` event is emitted

### Requirement: Manual solve fallback

When no external solver is configured, the system SHALL pause the run on a detected CAPTCHA and surface it for human solving over the live view, resuming after the human proceeds.

#### Scenario: Human solves in the live view

- **WHEN** a CAPTCHA is detected and the solver is `manual`
- **THEN** the run pauses, a banner is shown over the livestream, and the run resumes once the human signals completion

### Requirement: External solver

When an external solver is configured, the system SHALL request a token and inject it to clear the challenge.

#### Scenario: Token injected

- **WHEN** a CAPTCHA is detected and an `external` solver is configured
- **THEN** the system requests a solution token and injects it into the page
- **AND** emits `captcha_solved` on success or `captcha_unsolved` on failure
