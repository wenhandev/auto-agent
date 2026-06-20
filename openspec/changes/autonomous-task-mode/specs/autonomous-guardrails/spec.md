## Description

Hard guardrails enforced by the loop (not the LLM): a navigation domain allowlist, mandatory step/time budgets, a destructive-action confirmation gate via `human-in-the-loop`, and a no-progress/loop detector that aborts with a diagnostic.

## User stories

- **As an operator**, I want the agent confined to domains I approve so it cannot wander off-site.
- **As an operator**, I want the agent to pause before doing something destructive (purchase, delete) when I require confirmation.
- **As an operator**, I want a stuck agent to abort with a clear diagnostic, not loop forever burning budget.

## ADDED Requirements

### Requirement: Domain Allowlist

When `allowed_domains` is provided, any navigation or `http_request` whose target host is not in the allowlist SHALL fail the step with `"navigation to <host> blocked (not in allowed_domains)"`, and the agent SHALL be required to choose another action or finish.

#### Scenario: Off-allowlist navigation blocked

- **WHEN** `allowed_domains = ["example.com"]` and the agent attempts to navigate to `https://evil.test`
- **THEN** the step SHALL fail with the blocked message AND no navigation SHALL occur.

### Requirement: Mandatory Budgets Enforced By The Loop

`max_steps` and `max_seconds` SHALL be enforced by the loop independently of the LLM. Exceeding either SHALL terminate the run with a budget-exhausted result.

#### Scenario: Time budget enforced

- **WHEN** `max_seconds` elapses mid-step-sequence
- **THEN** the loop SHALL stop at the next cycle boundary with a budget-exhausted result.

### Requirement: Destructive-Action Confirmation Gate

When `require_confirmation` is set, an action classified as destructive (submitting forms matching purchase/delete/payment heuristics, or any `integration` write) SHALL pause the run via `human-in-the-loop` and resume only upon approval; rejection SHALL skip the action.

#### Scenario: Purchase submission pauses

- **WHEN** `require_confirmation` is true and the agent is about to submit a checkout/payment form
- **THEN** the run SHALL pause for human confirmation before submitting.

#### Scenario: Integration write always gates under confirmation

- **WHEN** `require_confirmation` is true and the agent invokes an `integration` write operation
- **THEN** the run SHALL pause for confirmation regardless of the form heuristics.

### Requirement: No-Progress / Loop Detection

If M consecutive steps produce no observable state change (same URL, same element-map hash, no new extracted data), the loop SHALL abort with a diagnostic naming the repeated action.

#### Scenario: Repeated no-op aborts

- **WHEN** the agent clicks the same element M times with no page-state change
- **THEN** the run SHALL abort with a diagnostic identifying the repeated action and the unchanged state.

## Out of Scope

- CAPTCHA solving (`captcha-antibot-proxy`).
- Per-action cost budgets (step/time budgets only in v1; cost is tracked by `run-cost-tracking`).
