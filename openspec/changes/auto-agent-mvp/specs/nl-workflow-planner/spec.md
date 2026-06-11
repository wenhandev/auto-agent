## ADDED Requirements

### Requirement: Natural-Language Generation Endpoint

The backend SHALL expose `POST /api/workflow/generate` that accepts `{ "description": string }` and returns a valid `Workflow` JSON.

#### Scenario: Valid description produces workflow

- **WHEN** the client POSTs a short Chinese or English description of a browser task
- **THEN** the response body SHALL deserialize into the `Workflow` schema with a non-empty `nodes` list, a non-empty `edges` list, a populated `start_id`, and every edge SHALL reference existing node ids.

#### Scenario: Missing API key returns a clear error

- **WHEN** `LLM_PROVIDER=openai` and `OPENAI_API_KEY` is unset and the client calls the endpoint
- **THEN** the server SHALL return an HTTP 400 (or 503) with a body explaining that an LLM API key is required, and SHALL NOT crash.

### Requirement: ADK Structured Output

The planner SHALL be implemented as an ADK `LlmAgent` with `output_schema=Workflow` (or the equivalent kwarg name in the installed ADK version) so the model is forced to emit JSON matching the pydantic schema.

#### Scenario: Planner uses ADK LlmAgent

- **WHEN** the planner is constructed
- **THEN** the implementation SHALL instantiate `LlmAgent(model=get_adk_model(), output_schema=Workflow, instruction=<system prompt>)`.

#### Scenario: Structured output fallback

- **WHEN** structured output through `LiteLlm` returns text that does not validate against `Workflow`
- **THEN** the planner SHALL retry once with a JSON-mode prompt and parse the result with `Workflow.model_validate_json`, raising a clean error if both attempts fail.

### Requirement: Vocabulary-Faithful Labels

The system prompt SHALL instruct the model to write each node's `label` in the same language and vocabulary as the user's description, NOT in CSS selectors or raw URLs.

#### Scenario: Label uses user vocabulary

- **WHEN** the user describes "搜索 iPhone 16"
- **THEN** the produced node label SHALL be `"搜索 'iPhone 16'"` (or close), not `"fill input[name=q]"`.

### Requirement: One Node Per User-Perceivable Step

The system prompt SHALL instruct the model to emit exactly one node per user-perceivable step, preferring deterministic node types when the description is precise and `fuzzy_action` only when the description is ambiguous.

#### Scenario: Precise URL becomes navigate node

- **WHEN** the description contains an explicit URL
- **THEN** the corresponding step SHALL be a `navigate` node rather than a `fuzzy_action`.

### Requirement: Few-Shot Exemplars

The system prompt SHALL include at least two in-prompt few-shot examples that demonstrate both a deterministic-only workflow and a mixed deterministic + `fuzzy_action` workflow.
