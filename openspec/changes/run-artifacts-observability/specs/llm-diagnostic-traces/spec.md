## ADDED Requirements

### Requirement: Per-call LLM trace

The system SHALL write an `llm_trace` artifact for every per-run LLM call, capturing model, system prompt, messages, response, token counts, and latency, linked to the originating node/step.

#### Scenario: Trace written for a vision step

- **WHEN** the vision agent makes an LLM call during a run
- **THEN** an `llm_trace` artifact is created with `{model, system, messages, response, tokens, latency_ms}` linked to that step

#### Scenario: Trace captured on success and failure

- **WHEN** an LLM call returns a successful but incorrect decision
- **THEN** the trace is still written (tracing is not gated on node failure)

### Requirement: Secret masking in traces

The system SHALL mask credential values in trace content before persistence using the credential masker.

#### Scenario: Credential not leaked into trace

- **WHEN** a prompt contains an interpolated credential value
- **THEN** the persisted trace shows the masked form, never the plaintext secret

### Requirement: Trace inspector

The run-detail UI SHALL let the operator expand any step to view its LLM trace.

#### Scenario: Expand a step's trace

- **WHEN** the operator expands a step in the run timeline
- **THEN** the masked system prompt, messages, response, and token/latency stats are shown
