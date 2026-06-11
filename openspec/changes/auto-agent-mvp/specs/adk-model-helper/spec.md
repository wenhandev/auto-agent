## ADDED Requirements

### Requirement: Single Model Helper

The backend SHALL expose a single function `get_adk_model()` in `app/agents/model.py` that returns the ADK model object (Gemini model id string or `LiteLlm` instance) appropriate for the configured provider.

#### Scenario: OpenAI provider

- **WHEN** `.env` contains `LLM_PROVIDER=openai` and `OPENAI_MODEL=gpt-4o`
- **THEN** `get_adk_model()` SHALL return a `LiteLlm` instance configured with `model="openai/gpt-4o"`.

#### Scenario: Google provider

- **WHEN** `.env` contains `LLM_PROVIDER=google` and `GOOGLE_MODEL=gemini-2.0-flash`
- **THEN** `get_adk_model()` SHALL return the string `"gemini-2.0-flash"`, which ADK accepts directly as a Gemini model id.

#### Scenario: Unknown provider

- **WHEN** `.env` contains `LLM_PROVIDER=anthropic`
- **THEN** `get_adk_model()` SHALL raise `ValueError` mentioning the unsupported provider.

### Requirement: No Custom Model Layer

The codebase SHALL NOT contain any `app/llm/` directory, custom `LLMAdapter` ABC, or `AdapterBackedLlm` subclass. All model abstraction SHALL be provided by ADK's existing `BaseLlm` / `Gemini` / `LiteLlm` classes.

#### Scenario: No adapter directory

- **WHEN** the backend is built
- **THEN** `backend/app/llm/` SHALL NOT exist; the only LLM-related backend module SHALL be `app/agents/model.py` plus the planner and fuzzy agents.

### Requirement: API Keys From Environment

The model helper SHALL rely on the standard provider environment variables (`OPENAI_API_KEY`, `GOOGLE_API_KEY`) read by `pydantic-settings` and passed through to ADK / LiteLLM without re-implementation.

#### Scenario: Missing OpenAI key

- **WHEN** `LLM_PROVIDER=openai` and `OPENAI_API_KEY` is unset and the planner is invoked
- **THEN** the error surfaced to the caller SHALL clearly identify the missing key (originating from ADK or LiteLLM); the helper itself SHALL NOT re-wrap or hide that error.
