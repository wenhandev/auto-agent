## ADDED Requirements

### Requirement: ADK-Backed Fuzzy Agent

The FuzzyAgent SHALL be implemented as an ADK `LlmAgent` whose `model` is the object returned by `get_adk_model()` (either a Gemini model-id string or a `LiteLlm` instance).

#### Scenario: Model selection through helper

- **WHEN** the FuzzyAgent is constructed
- **THEN** the implementation SHALL call `get_adk_model()` exactly once and pass the result as the `model=` argument to `LlmAgent`; it SHALL NOT instantiate provider SDKs directly.

### Requirement: Tool Registry

The FuzzyAgent SHALL register the following Playwright actions as ADK `FunctionTool`s: `click_text`, `click_selector`, `fill_field`, `scroll`, `screenshot`, `done`.

#### Scenario: Tools available to model

- **WHEN** the agent is constructed
- **THEN** the model context SHALL contain function declarations for all six tools above with names matching exactly.

### Requirement: Bounded Loop With Vision Input

The fuzzy loop SHALL run for at most `FUZZY_MAX_STEPS` (default 5) iterations; each iteration SHALL pass a fresh page screenshot (PNG, base64) as an image content part along with the `instruction` to the model.

#### Scenario: Loop terminates on done

- **WHEN** the model calls the `done` tool
- **THEN** the loop SHALL exit before reaching `FUZZY_MAX_STEPS`.

#### Scenario: Loop terminates on max steps

- **WHEN** the model never calls `done`
- **THEN** the loop SHALL stop after `FUZZY_MAX_STEPS` iterations and return a structured result indicating the limit was reached.

### Requirement: Per-Step Progress Callback

Before each tool execution, the FuzzyAgent SHALL invoke the injected `on_progress` async callback with a short Chinese-or-English summary of the chosen tool call (truncated, never raw argument blobs).

#### Scenario: Progress before action

- **WHEN** the agent decides to call `click_text("登录")`
- **THEN** `on_progress` SHALL be awaited with a message like `"调用 click_text(\"登录\")"` BEFORE the click is executed on the page.

### Requirement: Shared Playwright Page

The FuzzyAgent SHALL operate on the same Playwright `Page` instance used by the deterministic executor, NOT spawn a new browser context.

#### Scenario: Same tab

- **WHEN** a `fuzzy_action` node runs immediately after a `navigate` node
- **THEN** the FuzzyAgent's tools SHALL see the page already at the navigated URL.
