## ADDED Requirements

### Requirement: URL route skill matching

The system SHALL support route skills that match the current page URL using normalized URL patterns and apply enabled skills by priority.

#### Scenario: Route skill matches normalized URL

- **WHEN** the current page URL normalizes to a configured route skill pattern
- **THEN** the system applies that enabled route skill to the current autonomous or hybrid primitive step

#### Scenario: Disabled route skill ignored

- **WHEN** a matching route skill is disabled
- **THEN** the system does not apply its prompt constraints or tool restrictions

### Requirement: Route prompt constraints

The system SHALL merge matched route skill prompt constraints into the agent context for the current step without replacing task-level objectives or safety instructions.

#### Scenario: Route prompt included in trace

- **WHEN** a route skill contributes prompt constraints to an LLM decision
- **THEN** the LLM trace records the route skill identifier and effective route prompt
- **AND** the original task objective remains present in the prompt/context

#### Scenario: Multiple route skills apply by priority

- **WHEN** multiple enabled route skills match the current URL
- **THEN** the system applies them in deterministic priority order
- **AND** records the ordered route skill identifiers in the run timeline or LLM trace

### Requirement: Route tool gating

The system SHALL allow route skills to narrow the tool surface for an autonomous or hybrid step, while never expanding task-level allowed tools.

#### Scenario: Route skill narrows allowed tools

- **WHEN** a task allows tools `A`, `B`, and `C` and a matching route skill allows only `A` and `B`
- **THEN** the effective tool set for that step is `A` and `B`

#### Scenario: Route skill cannot expand allowed tools

- **WHEN** a task allows only tool `A` and a matching route skill allows `A` and `B`
- **THEN** the effective tool set for that step remains only `A`
